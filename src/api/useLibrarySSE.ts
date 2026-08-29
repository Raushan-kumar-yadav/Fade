 
import { useEffect, useRef } from 'react';

function base(): string {
  return `http://127.0.0.1:${(window as any).__FADE_PORT__ ?? 8000}`;
}

// Map SSE scope → window event name
const SCOPE_TO_EVENT: Record<string, string> = {
  library:  'fade:library-changed',
  webcomps: 'fade:webcomps-changed',
  comps: 'fade:comps-changed',
  timeline: 'fade:timeline-changed',
  all: 'fade:all-changed',
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

      // Listen for every named scope event
      const scopes = ['library', 'webcomps', 'comps', 'timeline', 'all'];
      for (const scope of scopes) {
        es.addEventListener(scope, () => {
          const eventName = SCOPE_TO_EVENT[scope];
          if (eventName) window.dispatchEvent(new CustomEvent(eventName));
          // "all" also fires every individual scope
          if (scope === 'all') {
            for (const s of scopes.filter(s => s !== 'all')) {
              const n = SCOPE_TO_EVENT[s];
              if (n) window.dispatchEvent(new CustomEvent(n));
            }
          }
        });
      }

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
