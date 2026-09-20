 
import { useEffect, useRef } from 'react';

function base(): string {
  return `http://127.0.0.1:${(window as any).__Fade_PORT__ ?? 8000}`;
}

 
const SCOPE_TO_EVENTS: Record<string, string[]> = {
  library:  ['Fade:library-changed'],
  webcomps: ['Fade:webcomps-changed'],
  comps: ['Fade:comps-changed'],
  
  timeline: ['Fade:timeline-changed', 'Fade:tracks-changed'],
  effects:  ['Fade:effects-changed'],
  masks: ['Fade:masks-changed'],
  transitions: ['Fade:transition-changed'],
  render:   ['Fade:render-now'],     // fired by notify("render") after text/style changes
 
  agent_resume: ['Fade:agent-resume'],
  // 'project' is fired on load/new  
  project:  ['Fade:library-changed', 'Fade:webcomps-changed', 'Fade:comps-changed',
             'Fade:tracks-changed', 'Fade:timeline-changed'],
  // 'all' fires every scope
  all: ['Fade:library-changed', 'Fade:webcomps-changed', 'Fade:comps-changed',
             'Fade:timeline-changed', 'Fade:tracks-changed',
             'Fade:effects-changed', 'Fade:masks-changed', 'Fade:transition-changed'],
};

export function useLibrarySSE(): void {
  const esRef = useRef<EventSource | null>(null);
  const retryMs = useRef(500);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const deadRef = useRef(false);

  useEffect(() => {
    deadRef.current = false;

    function connect() {
      if (deadRef.current) return;
      // Close any existing connection before reconnecting
      if (esRef.current) {
        esRef.current.close();
        esRef.current = null;
      }
      const url = `${base()}/events`;
      const es = new EventSource(url);
      esRef.current = es;

      es.addEventListener('connected', () => {
        retryMs.current = 500;
      });

      // Listen for every named scope
      const scopes = Object.keys(SCOPE_TO_EVENTS);
      for (const scope of scopes) {
        if (scope === 'agent_resume') continue;  
        es.addEventListener(scope, () => {
          for (const eventName of SCOPE_TO_EVENTS[scope]) {
            window.dispatchEvent(new CustomEvent(eventName));
          }
        });
      }

      // agent_resume carries a JSON payload  
      es.addEventListener('agent_resume', (e: Event) => {
        try {
          const msg = e as MessageEvent;
          const data = JSON.parse(msg.data);
          window.dispatchEvent(new CustomEvent('Fade:agent-resume', { detail: data }));
        } catch {   }
      });

      // update individual job cards  
      es.addEventListener('job', (e: Event) => {
        try {
          const msg = e as MessageEvent;
          const data = JSON.parse(msg.data);
          window.dispatchEvent(new CustomEvent('Fade:job-update', { detail: data }));
        } catch {  }
      });

      es.onerror = () => {
        es.close();
        esRef.current = null;
        if (!deadRef.current) {
          const delay = retryMs.current;
          retryMs.current = Math.min(delay * 2, 15_000); // cap at 15 s
          timer.current = setTimeout(connect, delay);
        }
      };
    }

    // Connect immediately if port is already known
    if ((window as any).__Fade_PORT__) {
      connect();
    }

    // Also connect (or reconnect) when port is received — covers the race
    // where port arrives after this effect runs
    const onPort = () => {
      if (timer.current) { clearTimeout(timer.current); timer.current = null; }
      retryMs.current = 500;   // reset backoff
      connect();
    };
    window.addEventListener('Fade:port', onPort);

    // Reconnect when tab becomes visible again after being hidden
    const onVisible = () => {
      if (!deadRef.current && !esRef.current && (window as any).__Fade_PORT__) {
        connect();
      }
    };
    document.addEventListener('visibilitychange', onVisible);

    return () => {
      deadRef.current = true;
      window.removeEventListener('Fade:port', onPort);
      document.removeEventListener('visibilitychange', onVisible);
      esRef.current?.close();
      esRef.current = null;
      if (timer.current) clearTimeout(timer.current);
    };
  }, []);
}
