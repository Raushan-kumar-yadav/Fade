import React, { useState, useCallback, useRef } from 'react';
import './ViewportWidget.css';

//   Timecode helper  
function framesToTimecode(frame: number, fps = 30): string {
  const f  = Math.floor(frame);
  const mm = Math.floor(f / (fps * 60));
  const ss = Math.floor((f / fps) % 60);
  const fr = f % fps;
  return [mm, ss, fr].map(n => String(n).padStart(2, '0')).join(':');
}

//   Icon SVGs  
const IconPrev = () => (
  <svg width="12" height="12" viewBox="0 0 12 12" fill="currentColor">
    <rect x="0" y="1" width="2" height="10" rx="1"/>
    <path d="M10 1 L3 6 L10 11 Z"/>
  </svg>
);
const IconNext = () => (
  <svg width="12" height="12" viewBox="0 0 12 12" fill="currentColor">
    <rect x="10" y="1" width="2" height="10" rx="1"/>
    <path d="M2 1 L9 6 L2 11 Z"/>
  </svg>
);
const IconPlay = () => (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
    <path d="M4 2 L14 8 L4 14 Z"/>
  </svg>
);
const IconPause = () => (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
    <rect x="3" y="2" width="4" height="12" rx="1.5"/>
    <rect x="9" y="2" width="4" height="12" rx="1.5"/>
  </svg>
);
const IconFullscreen = () => (
  <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
    <path d="M1 5V1h4M9 1h4v4M13 9v4H9M5 13H1V9"/>
  </svg>
);
//   Main Component  
export default function ViewportWidget({ onPopOut }: ViewportWidgetProps) {
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentFrame, setCurrentFrame] = useState(0);
  const [isFullscreen, setIsFullscreen] = useState(false);

  const totalFrames = 1800; // 60 s @ 30 fps
  const fps = 30;

  const rafRef  = useRef<ReturnType<typeof requestAnimationFrame>>();
  const lastRef = useRef<number>();

  //   Playback loop  
  const startPlayback = useCallback(() => {
    const tick = (now: number) => {
      const delta = lastRef.current ? (now - lastRef.current) / 1000 : 0;
      lastRef.current = now;
      setCurrentFrame(prev => {
        const next = prev + delta * fps;
        if (next >= totalFrames) {
          setIsPlaying(false);
          return 0;
        }
        return next;
      });
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
  }, [fps, totalFrames]);

  const stopPlayback = useCallback(() => {
    if (rafRef.current) cancelAnimationFrame(rafRef.current);
    lastRef.current = undefined;
  }, []);

  const togglePlay = useCallback(() => {
    setIsPlaying(p => {
      if (p) { stopPlayback(); return false; }
      startPlayback(); return true;
    });
  }, [startPlayback, stopPlayback]);

  const stepFrame = useCallback((dir: 1 | -1) => {
    stopPlayback();
    setIsPlaying(false);
    setCurrentFrame(f => Math.max(0, Math.min(totalFrames, Math.floor(f) + dir)));
  }, [stopPlayback, totalFrames]);

  const timecode = framesToTimecode(currentFrame, fps);

  return (
    <div className={`vw-root${isFullscreen ? ' vw-root--fullscreen' : ''}`} aria-label="Preview Viewport">

      {/*   Viewport canvas   */}
      <div className="vw-canvas" aria-label="Video preview area">
        <div className="vw-canvas__empty">
          <div className="vw-canvas__icon">◈</div>
          <p className="vw-canvas__hint">Drop video or select from Library</p>
        </div>
         <div className="vw-canvas__tc-overlay" aria-label="Timecode overlay">
          {timecode}
        </div>
      </div>

      {/*   Playback Controls   */}
      <div className="vw-controls">
        {/* Timecode display */}
        <div className="vw-controls__tc" aria-label="Current timecode" role="timer">
          {timecode}
        </div>

        {/* Centre transport buttons */}
        <div className="vw-controls__transport">
          <button
            id="vw-prev-frame"
            className="vw-btn"
            title="Previous frame (← Arrow)"
            onClick={() => stepFrame(-1)}
          >
            <IconPrev />
          </button>

          <button
            id="vw-play-pause"
            className="vw-btn vw-btn--play"
            title={isPlaying ? 'Pause (Space)' : 'Play (Space)'}
            onClick={togglePlay}
          >
            {isPlaying ? <IconPause /> : <IconPlay />}
          </button>

          <button
            id="vw-next-frame"
            className="vw-btn"
            title="Next frame (→ Arrow)"
            onClick={() => stepFrame(1)}
          >
            <IconNext />
          </button>
        </div>

        {/* Right: Fullscreen */}
        <div className="vw-controls__right">
          <button
            id="vw-fullscreen"
            className="vw-btn"
            title="Toggle fullscreen (F)"
            onClick={() => setIsFullscreen(f => !f)}
          >
            <IconFullscreen />
          </button>
        </div>
      </div>
    </div>
  );
}
