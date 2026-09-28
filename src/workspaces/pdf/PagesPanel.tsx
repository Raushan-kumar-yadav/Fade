 
import React, { useCallback, useEffect, useRef, useState } from 'react';
import './PagesPanel.css';

//   Types  

export interface PdfPage {
  index:  number;
  pageId: string;
  compId: string;
  name: string;
}

interface PagesPanelProps {
  docId: string;
  activePageId: string | null;
  onSelectPage: (page: PdfPage) => void;
}

//   Thumbnail cache  

const thumbCache = new Map<string, string>();   // compId → object-url
const THUMB_W = 240;
const THUMB_H = 320;   // A4 portrait ratio ≈ 1 : 1.414

async function fetchThumb(compId: string, port: number, bust = false): Promise<string> {
  if (!bust && thumbCache.has(compId)) return thumbCache.get(compId)!;
  try {
    const res = await fetch(
      `http://127.0.0.1:${port}/comps/${compId}/thumbnail?w=${THUMB_W}&h=${THUMB_H}&t=${bust ? Date.now() : ''}`,
      { method: 'GET' }
    );
    if (!res.ok) return '';
    const blob = await res.blob();
    if (blob.size < 50) return '';         
    const old = thumbCache.get(compId);
    if (old) URL.revokeObjectURL(old);
    const url = URL.createObjectURL(blob);
    thumbCache.set(compId, url);
    return url;
  } catch {
    return '';
  }
}

//   Component  

export default function PagesPanel({ docId, activePageId, onSelectPage }: PagesPanelProps) {
  const [pages, setPages] = useState<PdfPage[]>([]);
  const [loading, setLoading] = useState(false);
  const [thumbs, setThumbs] = useState<Record<string, string>>({});
  const [loadingIds, setLoadingIds] = useState<Set<string>>(new Set());
  const [dragOverIdx, setDragOverIdx] = useState<number | null>(null);
  const dragIdxRef  = useRef<number | null>(null);
  const pollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const port = (window as any).__FADE_PORT__ ?? 8000;

  // Fetch page list  
  const fetchPages = useCallback(async (): Promise<PdfPage[]> => {
    if (!docId) return [];
    try {
      const r = await fetch(`http://127.0.0.1:${port}/pdf-docs/${docId}/pages`);
      if (!r.ok) return [];
      const data = await r.json();
      return (data.pages ?? []).map((p: any) => ({
        index:  p.index,
        pageId: p.pageId,
        compId: p.compId,
        name: p.name,
      }));
    } catch {
      return [];
    }
  }, [docId, port]);

  //   Load one thumbnail  
  const loadThumb = useCallback(async (compId: string, bust = false) => {
    setLoadingIds(s => new Set(s).add(compId));
    const url = await fetchThumb(compId, port, bust);
    setLoadingIds(s => { const n = new Set(s); n.delete(compId); return n; });
    if (url) setThumbs(prev => ({ ...prev, [compId]: url }));
  }, [port]);

  //   Initial load  
  useEffect(() => {
    setLoading(true);
    fetchPages().then(ps => {
      setPages(ps);
      setLoading(false);
 
      ps.forEach(p => loadThumb(p.compId));
    });
  }, [docId]); 

  //   Poll active page thumbnail  
  useEffect(() => {
    if (pollTimerRef.current) clearTimeout(pollTimerRef.current);
    if (!activePageId) return;

    const schedule = () => {
      pollTimerRef.current = setTimeout(async () => {
        await loadThumb(activePageId, true);   // bust cache
        schedule();
      }, 1800);
    };
    schedule();
    return () => { if (pollTimerRef.current) clearTimeout(pollTimerRef.current); };
  }, [activePageId]);  

  // Add page 
  const addPage = async () => {
    const r = await fetch(`http://127.0.0.1:${port}/pdf-docs/${docId}/pages`, { method: 'POST' });
    if (!r.ok) return;
    const newPage: any = await r.json();
    const ps = await fetchPages();
    setPages(ps);
    const found = ps.find(p => p.pageId === newPage.pageId);
    if (found) {
      onSelectPage(found);
      loadThumb(found.compId);
    }
  };

  //   Delete page  
  const deletePage = async (e: React.MouseEvent, pageId: string) => {
    e.stopPropagation();
    if (pages.length <= 1) return;
    await fetch(`http://127.0.0.1:${port}/pdf-docs/${docId}/pages/${pageId}`, { method: 'DELETE' });
    const ps = await fetchPages();
    setPages(ps);
    if (pageId === activePageId && ps.length > 0) onSelectPage(ps[0]);
  };

  //   Drag reorder  
  const onDragStart  = (idx: number) => { dragIdxRef.current = idx; };
  const onDragOver = (e: React.DragEvent, idx: number) => { e.preventDefault(); setDragOverIdx(idx); };
  const onDragEnd = () => setDragOverIdx(null);
  const onDrop = async (idx: number) => {
    const from = dragIdxRef.current;
    if (from === null || from === idx) { setDragOverIdx(null); return; }
    const reordered = [...pages];
    const [moved]   = reordered.splice(from, 1);
    reordered.splice(idx, 0, moved);
    setPages(reordered);
    setDragOverIdx(null);
    await fetch(`http://127.0.0.1:${port}/pdf-docs/${docId}/pages/reorder`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ page_ids: reordered.map(p => p.pageId) }),
    });
  };

  //   Render  
  return (
    <div className="pages-panel">
      <div className="pages-panel__header">
        <span className="pages-panel__title">Pages</span>
        <span className="pages-panel__count">{pages.length}</span>
      </div>

      <div className="pages-panel__list">
        {loading && pages.length === 0 && (
          <>
            {[0, 1].map(i => (
              <div key={i} className="pages-panel__page pages-panel__page--skeleton">
                <div className="pages-panel__thumb-wrap pages-panel__thumb--shimmer" />
              </div>
            ))}
          </>
        )}

        {pages.map((page, idx) => {
          const isActive = page.pageId === activePageId;
          const thumb = thumbs[page.compId];
          const isLoading = loadingIds.has(page.compId);
          return (
            <div
              key={page.pageId}
              className={[
                'pages-panel__page',
                isActive       ? 'pages-panel__page--active'    : '',
                dragOverIdx === idx ? 'pages-panel__page--drag-over' : '',
              ].join(' ')}
              draggable
              onDragStart={() => onDragStart(idx)}
              onDragOver={e  => onDragOver(e, idx)}
              onDrop={()     => onDrop(idx)}
              onDragEnd={onDragEnd}
              onClick={() => onSelectPage(page)}
              title={page.name}
            >
              {/* Page number badge */}
              <div className="pages-panel__page-number">{idx + 1}</div>

              {/* Thumbnail */}
              <div className={`pages-panel__thumb-wrap${isLoading && !thumb ? ' pages-panel__thumb--shimmer' : ''}`}>
                {thumb ? (
                  <img
                    className={`pages-panel__thumb${isLoading ? ' pages-panel__thumb--refreshing' : ''}`}
                    src={thumb}
                    alt={`Page ${idx + 1}`}
                  />
                ) : isLoading ? null : (
                  <div className="pages-panel__thumb-placeholder">
                    <svg viewBox="0 0 48 64" width={32} height={42} fill="none">
                      <rect x="4" y="4" width="40" height="56" rx="3" stroke="rgba(255,255,255,0.15)" strokeWidth="1.5"/>
                      <line x1="10" y1="18" x2="38" y2="18" stroke="rgba(255,255,255,0.1)" strokeWidth="2" strokeLinecap="round"/>
                      <line x1="10" y1="26" x2="38" y2="26" stroke="rgba(255,255,255,0.08)" strokeWidth="2" strokeLinecap="round"/>
                      <line x1="10" y1="34" x2="28" y2="34" stroke="rgba(255,255,255,0.08)" strokeWidth="2" strokeLinecap="round"/>
                    </svg>
                    <span className="pages-panel__thumb-num">{idx + 1}</span>
                  </div>
                )}
              </div>

              {/* Page name below thumbnail */}
              <div className="pages-panel__page-label">{page.name || `Page ${idx + 1}`}</div>

              {/* Delete (hover) */}
              {pages.length > 1 && (
                <button
                  className="pages-panel__delete"
                  onClick={e => deletePage(e, page.pageId)}
                  title="Delete page"
                >✕</button>
              )}
            </div>
          );
        })}
      </div>

      <button className="pages-panel__add-btn" onClick={addPage}>
        <span>+</span> Add page
      </button>
    </div>
  );
}
