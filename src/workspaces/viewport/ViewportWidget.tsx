import React, { useState, useCallback, useRef } from 'react';
import './ViewportWidget.css';

function framesToTimecode(frame: number, fps = 30): string {
  const f  = Math.floor(frame);
  const mm = Math.floor(f / (fps * 60));
  const ss = Math.floor((f / fps) % 60);
  const fr = f % fps;
  return [mm, ss, fr].map(n => String(n).padStart(2, '0')).join(':');
}

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

export default function ViewportWidget() {
  const [isPlaying, setIsPlaying]   = useState(false);
  const [currentFrame, setCurrentFrame] = useState(0);
  const [isFullscreen, setIsFullscreen] = useState(false);

  const totalFrames = 1800;
  const fps = 30;

  const isPlayingRef = useRef<boolean>(false);
  const rafRef = useRef<number>(0);
  const lastRef = useRef<number>(0);

  const stopPlayback = useCallback(() => {
    isPlayingRef.current = false;
    if (rafRef.current) cancelAnimationFrame(rafRef.current);
    rafRef.current = 0;
    lastRef.current = 0;
  }, []);

  const startPlayback = useCallback(() => {
    isPlayingRef.current = true;
    lastRef.current = 0;

    const tick = (now: number) => {
      if (!isPlayingRef.current) return;
      const delta = lastRef.current ? (now - lastRef.current) / 1000 : 0;
      lastRef.current = now;
      setCurrentFrame(prev => {
        const next = prev + delta * fps;
        if (next >= totalFrames) {
          isPlayingRef.current = false;
          setIsPlaying(false);
          return 0;
        }
        return next;
      });
      if (isPlayingRef.current) {
        rafRef.current = requestAnimationFrame(tick);
      }
    };

    rafRef.current = requestAnimationFrame(tick);
  }, [fps, totalFrames]);

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
      <div className="vw-canvas" aria-label="Video preview area">
        <div className="vw-canvas__empty">
          <div className="vw-canvas__icon">?</div>
          <p className="vw-canvas__hint">Drop video or select from Library</p>
        </div>
      </div>

      <div className="vw-controls">
        <div className="vw-controls__tc" aria-label="Current timecode" role="timer">
          {timecode}
        </div>
        <div className="vw-controls__transport">
          <button id="vw-prev-frame" className="vw-btn" title="Previous frame" onClick={() => stepFrame(-1)}>
            <IconPrev />
          </button>
          <button id="vw-play-pause" className="vw-btn vw-btn--play" title={isPlaying ? 'Pause' : 'Play'} onClick={togglePlay}>
            {isPlaying ? <IconPause /> : <IconPlay />}
          </button>
          <button id="vw-next-frame" className="vw-btn" title="Next frame" onClick={() => stepFrame(1)}>
            <IconNext />
          </button>
        </div>
        <div className="vw-controls__right">
          <button id="vw-fullscreen" className="vw-btn" title="Toggle fullscreen" onClick={() => setIsFullscreen(f => !f)}>
            <IconFullscreen />
          </button>
        </div>
      </div>
    </div>
  );
}
