import React, { memo, useCallback } from 'react';
import { useTimeline, frameToTimecode } from './TimelineContext';
import { HEADER_WIDTH, RULER_HEIGHT } from './types';

interface Props {
   scrollLeft: number;
  contentLeft: number;   
}

 
const Playhead = memo(function Playhead({ scrollLeft, contentLeft }: Props) {
  const { state, dispatch } = useTimeline();
  const { currentFrame, zoomX, fps, totalFrames } = state;

   const physicalX = currentFrame * zoomX - scrollLeft;

  // Hide if outside  
  const isVisible = physicalX >= 0 && physicalX <= window.innerWidth;

  //   Drag handler  
  const onMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();

    const startX = e.clientX;
    const startFrame = currentFrame;

    const onMove = (ev: MouseEvent) => {
      const dx = ev.clientX - startX;
      const newFrame = Math.max(0, Math.min(totalFrames, Math.round(startFrame + dx / zoomX)));
      dispatch({ type: 'SEEK', frame: newFrame });
    };
    const onUp = () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
  }, [currentFrame, zoomX, totalFrames, dispatch]);

  if (!isVisible) return null;

  return (
    <div
      className="tl-playhead"
      style={{ left: HEADER_WIDTH + physicalX }}
      aria-label={`Playhead at ${frameToTimecode(currentFrame, fps)}`}
    >
      {/* Triangle head */}
      <div className="tl-playhead__head" onMouseDown={onMouseDown} />
      {/* Vertical line */}
      <div className="tl-playhead__line" />
    </div>
  );
});

export default Playhead;
