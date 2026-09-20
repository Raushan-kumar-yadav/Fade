import React, { memo, useCallback, useRef } from 'react';
import { useTimeline, frameToTimecode } from './TimelineContext';
import { HEADER_WIDTH, RULER_HEIGHT } from './types';
import { playbackSeek } from '../../api/useApi';

interface Props {
   scrollLeft: number;
  contentLeft: number;   
}

 
const Playhead = memo(function Playhead({ scrollLeft, contentLeft }: Props) {
  const { state, dispatch } = useTimeline();
  const { currentFrame, zoomX, fps, totalFrames } = state;
  const lastSeekFrame = useRef<number>(-1);

   const physicalX = currentFrame * zoomX - scrollLeft; 

  // Hide if outside  
  const isVisible = physicalX >= 0 && physicalX <= window.innerWidth;

  //   Drag handler  
  const onMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();

    const startX = e.clientX;
    const startFrame = currentFrame;

    
    window.dispatchEvent(new CustomEvent('Fade:audio-pause'));

    const onMove = (ev: MouseEvent) => {
      const dx = ev.clientX - startX;
      const newFrame = Math.max(0, Math.min(totalFrames, Math.round(startFrame + dx / zoomX)));
      if (newFrame !== lastSeekFrame.current) {
        lastSeekFrame.current = newFrame;
        dispatch({ type: 'SEEK', frame: newFrame });
        // engine.seek() on the backend already calls pipeline.notify_seek() which
        // notifies the C++ compositor — no need for a separate renderSeek() IPC.
        playbackSeek(newFrame).catch(() => {});
      }
    };
    const onUp = () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
      // Wait for backend to confirm the seek before repositioning audio,
      // so audio never jumps to a frame Python hasn't committed to yet.
      const finalFrame = lastSeekFrame.current >= 0 ? lastSeekFrame.current : startFrame;
      playbackSeek(finalFrame)
        .then(() => {
          window.dispatchEvent(new CustomEvent('Fade:audio-seek', { detail: finalFrame }));
        })
        .catch(() => {
          // Backend unreachable — seek audio optimistically so UI isn't frozen
          window.dispatchEvent(new CustomEvent('Fade:audio-seek', { detail: finalFrame }));
        });
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
