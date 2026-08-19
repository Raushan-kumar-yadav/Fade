import React, { memo, useCallback } from 'react';
import { useTimeline, frameToTimecode } from './TimelineContext';
import { RULER_HEIGHT } from './types';

interface Props {
   scrollLeft: number;
  totalWidthPx: number;
  onSeek: (frame: number) => void;
}

 
const TimelineRuler = memo(function TimelineRuler({ scrollLeft, totalWidthPx, onSeek }: Props) {
  const { state } = useTimeline();
  const { zoomX, fps } = state;

   const framesPerTick = Math.max(1, Math.round(80 / zoomX / fps) * fps);
  const tickCount = Math.ceil(totalWidthPx / (framesPerTick * zoomX)) + 1;

  const handleClick = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const clickedPx = e.clientX - rect.left + scrollLeft;
    const frame = Math.max(0, Math.round(clickedPx / zoomX));
    onSeek(frame);
  }, [scrollLeft, zoomX, onSeek]);

  return (
    <div
      className="tl-ruler"
      style={{ height: RULER_HEIGHT, overflow: 'hidden', position: 'relative', cursor: 'pointer' }}
      onClick={handleClick}
    >
      {/* Translate inner content */}
      <div
        className="tl-ruler__inner"
        style={{ transform: `translateX(-${scrollLeft}px)`, width: totalWidthPx, height: '100%', position: 'relative' }}
      >
        {Array.from({ length: tickCount }, (_, i) => {
          const frame = i * framesPerTick;
          const x = frame * zoomX;
          const label = frameToTimecode(frame, fps);
          // Sub-ticks  
          const showSub = (framesPerTick * zoomX) > 40;
          const subX = x + (framesPerTick / 2) * zoomX;

          return (
            <React.Fragment key={frame}>
              {/* Major tick */}
              <div className="tl-tick tl-tick--major" style={{ left: x }}>
                <span className="tl-tick__label">{label}</span>
              </div>
              {/* Sub-tick */}
              {showSub && (
                <div className="tl-tick tl-tick--minor" style={{ left: subX }} />
              )}
            </React.Fragment>
          );
        })}
      </div>
    </div>
  );
});

export default TimelineRuler;
