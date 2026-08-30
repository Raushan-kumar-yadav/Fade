 
import { useEffect, useRef } from 'react';

function base(): string {
  return `http://127.0.0.1:${(window as any).__FADE_PORT__ ?? 8000}`;
}

 
const SCOPE_TO_EVENTS: Record<string, string[]> = {
  library:  ['fade:library-changed'],
  webcomps: ['fade:webcomps-changed'],
  comps: ['fade:comps-changed'],
  
  timeline: ['fade:timeline-changed', 'fade:tracks-changed'],
  effects:  ['fade:effects-changed'],
  masks: ['fade:masks-changed'],
  transitions: ['fade:transition-changed'],
  render:   ['fade:render-now'],     // fired by notify("render") after text/style changes
 
  agent_resume: ['fade:agent-resume'],
  // 'project' is fired on load/new  
  project:  ['fade:library-changed', 'fade:webcomps-changed', 'fade:comps-changed',
             'fade:tracks-changed', 'fade:timeline-changed'],
  // 'all' fires every scope
  all: ['fade:library-changed', 'fade:webcomps-changed', 'fade:comps-changed',
             'fade:timeline-changed', 'fade:tracks-changed',
             'fade:effects-changed', 'fade:masks-changed', 'fade:transition-changed'],
};

export function useLibrarySSE(): void {
  const esRef = useRef<EventSource | null>(null);
  const retryMs = useRef(500);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    let dead = false;

    function connect() {
      if (dead) return;
      const url = `${base()}/events`;
      const es = new EventSource(url);
      esRef.current = es;

      es.addEventListener('connected', () => {
        retryMs.current = 500;
      });

      // Listen for every named  
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
          window.dispatchEvent(new CustomEvent('fade:agent-resume', { detail: data }));
        } catch {   }
      });

 
      // update individual job cards  
      es.addEventListener('job', (e: Event) => {
        try {
          const msg = e as MessageEvent;
          const data = JSON.parse(msg.data);
          window.dispatchEvent(new CustomEvent('fade:job-update', { detail: data }));
        } catch {  }
      });

      es.onerror = () => {
        es.close();
        esRef.current = null;
        if (!dead) {
          const delay = retryMs.current;
          retryMs.current = Math.min(delay * 2, 15_000); // cap at 15 s
          timer.current = setTimeout(connect, delay);
        }
      };
    }

    // Wait for port to be known before connecting
    if ((window as any).__FADE_PORT__) {
      connect();
    } else {
      const onPort = () => connect();
      window.addEventListener('fade:port', onPort, { once: true });
      return () => {
        dead = true;
        window.removeEventListener('fade:port', onPort);
        esRef.current?.close();
        if (timer.current) clearTimeout(timer.current);
      };
    }

    return () => {
      dead = true;
      esRef.current?.close();
      esRef.current = null;
      if (timer.current) clearTimeout(timer.current);
    };
  }, []);
}
