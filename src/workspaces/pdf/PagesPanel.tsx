/**
 * PagesPanel.tsx
 *
 * Canva-style vertical pages sidebar for the PDF workspace.
 * - Shows thumbnail for each page (fetched from /render/frame)
 * - Click to select → ENTER_COMP for that page's imageComp
 * - "+" to add a page, "×" to delete a page
 * - Drag-to-reorder support via HTML5 drag events
 */
import React, { useEffect, useState, useCallback, useRef } from 'react';
import { useTimeline } from '../timeline/TimelineContext';
import './PagesPanel.css';

// ─── Types ────────────────────────────────────────────────────────────────────

export interface PdfPage {
  index: number;
  pageId: string;
  compId: string;
  name: string;
  thumbnailUrl?: string;
}

interface PagesPanelProps {
  docId: string;
  activePageId: string | null;
  onSelectPage: (page: PdfPage) => void;
}

// ─── Thumbnail fetcher ────────────────────────────────────────────────────────

const THUMB_W = 160;
const THUMB_H = 90;
const thumbCache = new Map<string, string>(); // compId → data-url

async function fetchThumb(compId: string, port: number): Promise<string> {
  if (thumbCache.has(compId)) return thumbCache.get(compId)!;
  try {
    // Activate the comp temporarily for a frame render
    const res = await fetch(
      `http://127.0.0.1:${port}/render/frame?compId=${compId}&frame=0&width=${THUMB_W}&height=${THUMB_H}`,
      { method: 'GET' }
    );
    if (!res.ok) return '';
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    thumbCache.set(compId, url);
    return url;
  } catch {
    return '';
  }
}

// ─── Component ────────────────────────────────────────────────────────────────

export default function PagesPanel({ docId, activePageId, onSelectPage }: PagesPanelProps) {
  const { dispatch } = useTimeline();
  const [pages, setPages] = useState<PdfPage[]>([]);
  const [loading, setLoading] = useState(false);
  const [thumbs, setThumbs] = useState<Record<string, string>>({});
  const [dragOverIdx, setDragOverIdx] = useState<number | null>(null);
  const dragIdxRef = useRef<number | null>(null);
  const port = (window as any).__FADE_PORT__ ?? 8000;

  // ── Fetch page list ─────────────────────────────────────────────────────────
  const fetchPages = useCallback(async () => {
    if (!docId) return;
    try {
      const r = await fetch(`http://127.0.0.1:${port}/pdf-docs/${docId}/pages`);
      if (!r.ok) return;
      const data = await r.json();
      const ps: PdfPage[] = (data.pages ?? []).map((p: any) => ({
        index: p.index,
        pageId: p.pageId,
        compId: p.compId,
        name: p.name,
      }));
      setPages(ps);
      return ps;
    } catch {
      return [];
    }
  }, [docId, port]);

  // ── Load thumbnails lazily ──────────────────────────────────────────────────
  const loadThumbs = useCallback(async (ps: PdfPage[]) => {
    for (const p of ps) {
      if (thumbs[p.compId]) continue;
      const url = await fetchThumb(p.compId, port);
      if (url) setThumbs(prev => ({ ...prev, [p.compId]: url }));
    }
  }, [port, thumbs]);

  useEffect(() => {
    setLoading(true);
    fetchPages()
      .then(ps => { if (ps) loadThumbs(ps); })
      .finally(() => setLoading(false));
  }, [docId]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Invalidate thumb when active page changes (user edited) ────────────────
  useEffect(() => {
    if (!activePageId) return;
    // Slight delay so the render has time to update
    const t = setTimeout(async () => {
      thumbCache.delete(activePageId);
      const url = await fetchThumb(activePageId, port);
      if (url) setThumbs(prev => ({ ...prev, [activePageId]: url }));
    }, 800);
    return () => clearTimeout(t);
  }, [activePageId, port]);

  // ── Add page ────────────────────────────────────────────────────────────────
  const addPage = async () => {
    const r = await fetch(`http://127.0.0.1:${port}/pdf-docs/${docId}/pages`, { method: 'POST' });
    if (!r.ok) return;
    const newPage: PdfPage = await r.json();
    const updated = await fetchPages();
    if (updated) {
      const found = updated.find(p => p.pageId === newPage.pageId);
      if (found) onSelectPage(found);
    }
  };

  // ── Delete page ─────────────────────────────────────────────────────────────
  const deletePage = async (e: React.MouseEvent, pageId: string) => {
    e.stopPropagation();
    if (pages.length <= 1) return;
    await fetch(`http://127.0.0.1:${port}/pdf-docs/${docId}/pages/${pageId}`, { method: 'DELETE' });
    const updated = await fetchPages() ?? [];
    // Select adjacent page after deletion
    const wasActive = pageId === activePageId;
    if (wasActive && updated.length > 0) {
      onSelectPage(updated[0]);
    }
  };

  // ── Drag reorder ────────────────────────────────────────────────────────────
  const onDragStart = (idx: number) => { dragIdxRef.current = idx; };
  const onDragOver = (e: React.DragEvent, idx: number) => {
    e.preventDefault();
    setDragOverIdx(idx);
  };
  const onDrop = async (idx: number) => {
    const from = dragIdxRef.current;
    if (from === null || from === idx) { setDragOverIdx(null); return; }
    const reordered = [...pages];
    const [moved] = reordered.splice(from, 1);
    reordered.splice(idx, 0, moved);
    setPages(reordered);
    setDragOverIdx(null);
    await fetch(`http://127.0.0.1:${port}/pdf-docs/${docId}/pages/reorder`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ page_ids: reordered.map(p => p.pageId) }),
    });
  };

  return (
    <div className="pages-panel">
      <div className="pages-panel__header">
        <span className="pages-panel__title">Pages</span>
        <span className="pages-panel__count">{pages.length}</span>
      </div>

      <div className="pages-panel__list">
        {loading && pages.length === 0 && (
          <div className="pages-panel__loading">Loading…</div>
        )}

        {pages.map((page, idx) => {
          const isActive = page.pageId === activePageId;
          const thumb = thumbs[page.compId];
          return (
            <div
              key={page.pageId}
              className={[
                'pages-panel__page',
                isActive ? 'pages-panel__page--active' : '',
                dragOverIdx === idx ? 'pages-panel__page--drag-over' : '',
              ].join(' ')}
              draggable
              onDragStart={() => onDragStart(idx)}
              onDragOver={e => onDragOver(e, idx)}
              onDrop={() => onDrop(idx)}
              onDragEnd={() => setDragOverIdx(null)}
              onClick={() => onSelectPage(page)}
              title={page.name}
            >
              <div className="pages-panel__page-number">{idx + 1}</div>

              <div className="pages-panel__thumb-wrap">
                {thumb
                  ? <img className="pages-panel__thumb" src={thumb} alt={`Page ${idx + 1}`} />
                  : <div className="pages-panel__thumb-placeholder">
                      <span>{idx + 1}</span>
                    </div>
                }
              </div>

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

      <button className="pages-panel__add-btn" onClick={addPage} title="Add page">
        <span>+</span> Add page
      </button>
    </div>
  );
}
