 
import { useEffect, useRef } from 'react';

function base(): string {
  return `http://127.0.0.1:${(window as any).__FADE_PORT__ ?? 8000}`;
}

// Map SSE scope → window event name(s)
// Each scope can map to one or more frontend CustomEvents
const SCOPE_TO_EVENTS: Record<string, string[]> = {
  library:  ['fade:library-changed'],
  webcomps: ['fade:webcomps-changed'],
  comps:    ['fade:comps-changed'],
  // 'timeline' fires both the SSE-specific event AND the one TimelineContext actually uses
  timeline: ['fade:timeline-changed', 'fade:tracks-changed'],
  effects:  ['fade:effects-changed'],
  masks:    ['fade:masks-changed'],
  transitions: ['fade:transition-changed'],
  // 'project' is fired on load/new — refreshes everything
  project:  ['fade:library-changed', 'fade:webcomps-changed', 'fade:comps-changed',
             'fade:tracks-changed', 'fade:timeline-changed'],
  // 'all' fires every scope
  all:      ['fade:library-changed', 'fade:webcomps-changed', 'fade:comps-changed',
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

      // Listen for every named scope and fire its mapped frontend events
      const scopes = Object.keys(SCOPE_TO_EVENTS);
      for (const scope of scopes) {
        es.addEventListener(scope, () => {
          for (const eventName of SCOPE_TO_EVENTS[scope]) {
            window.dispatchEvent(new CustomEvent(eventName));
          }
        });
      }

 
      // update individual job cards  
      es.addEventListener('job', (e: Event) => {
        try {
          const msg = e as MessageEvent;
          const data = JSON.parse(msg.data);
          window.dispatchEvent(new CustomEvent('fade:job-update', { detail: data }));
        } catch { /* ignore parse errors */ }
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
