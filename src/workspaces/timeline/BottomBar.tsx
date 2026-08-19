import React, { memo, useCallback, useRef, useState } from 'react';
import { useTimeline, totalWidth } from './TimelineContext';

interface Props {
  contentRef: React.RefObject<HTMLDivElement | null>;
  viewWidth: number;
}

 
const BottomBar = memo(function BottomBar({ contentRef, viewWidth }: Props) {
  const { state, dispatch } = useTimeline();
  const total = totalWidth(state);

  const barRef = useRef<HTMLDivElement>(null);
  const dragMode = useRef<'pan' | 'zoomLeft' | 'zoomRight' | null>(null);
  const dragStartX = useRef(0);
  const dragStartScroll = useRef(0);
  const dragStartZoom   = useRef(state.zoomX);

  // Thumb metrics ( 
  const thumbW = Math.max(16, (viewWidth / total) * viewWidth);
  const maxScroll = Math.max(0, total - viewWidth);
  const scrollLeft = contentRef.current?.scrollLeft ?? 0;
  const thumbX = maxScroll > 0 ? (scrollLeft / maxScroll) * (viewWidth - thumbW) : 0;

  const EDGE = 8;  

  const onThumbMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    const localX = e.clientX - e.currentTarget.getBoundingClientRect().left;
    const tW = e.currentTarget.getBoundingClientRect().width;

    dragMode.current = localX < EDGE ? 'zoomLeft' : localX > tW - EDGE ? 'zoomRight' : 'pan';
    dragStartX.current = e.clientX;
    dragStartScroll.current = contentRef.current?.scrollLeft ?? 0;
    dragStartZoom.current   = state.zoomX;

    const onMove = (ev: MouseEvent) => {
      const dx   = ev.clientX - dragStartX.current;
      const barW = barRef.current?.clientWidth ?? viewWidth;

      if (dragMode.current === 'pan') {
        const newScroll = dragStartScroll.current + dx * (maxScroll / (barW - thumbW));
        if (contentRef.current) contentRef.current.scrollLeft = Math.max(0, Math.min(maxScroll, newScroll));

      } else if (dragMode.current === 'zoomLeft' || dragMode.current === 'zoomRight') {
        // Dragging an edge changes zoom
        const factor = 1 + (dx / barW) * 2 * (dragMode.current === 'zoomLeft' ? -1 : 1);
        const newZoom = Math.max(0.3, Math.min(60, dragStartZoom.current * factor));
        dispatch({ type: 'ZOOM_X', newZoom });
      }
    };
    const onUp = () => {
      dragMode.current = null;
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
  }, [state.zoomX, viewWidth, thumbW, maxScroll, contentRef, dispatch]);

  return (
    <div ref={barRef} className="tl-bottom-bar" style={{ position: 'relative' }}>
      {/* Track line */}
      <div className="tl-bottom-bar__track" />

      {/* Thumb */}
      <div
        className="tl-bottom-bar__thumb"
        style={{ left: thumbX, width: thumbW }}
        onMouseDown={onThumbMouseDown}
        role="scrollbar"
        aria-valuenow={Math.round(scrollLeft)}
        aria-label="Timeline horizontal scroll"
      >
        {/* Edge grips */}
        <div className="tl-bottom-bar__grip tl-bottom-bar__grip--left" />
        <div className="tl-bottom-bar__grip tl-bottom-bar__grip--right" />
      </div>
    </div>
  );
});

export default BottomBar;
