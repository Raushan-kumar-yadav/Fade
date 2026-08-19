import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  openPreviewSocket,
  playbackPlay, playbackPause, playbackSeek,
  getPlaybackState, frameUrl,
} from '../../api/useApi';
import './ViewportWidget.css';

function framesToTimecode(frame: number, fps = 30): string {
  const f  = Math.floor(frame);
  const mm = Math.floor(f / (fps * 60));
  const ss = Math.floor((f / fps) % 60);
  const fr = f % Math.max(fps, 1);
  return [mm, ss, fr].map(n => String(n).padStart(2, '0')).join(':');
}

// ── SVG icons ──────────────────────────────────────────────────────────────────

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

// ── Component ──────────────────────────────────────────────────────────────────

export default function ViewportWidget() {
  const [isPlaying,    setIsPlaying]    = useState(false);
  const [currentFrame, setCurrentFrame] = useState(0);
  const [totalFrames,  setTotalFrames]  = useState(1800);
  const [fps,          setFps]          = useState(30);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [connected,    setConnected]    = useState(false);

  // The canvas receives decoded JPEG blobs from the WebSocket
  const canvasRef  = useRef<HTMLCanvasElement>(null);
  const wsRef      = useRef<WebSocket | null>(null);
  const imgRef     = useRef<HTMLImageElement>(new Image());

  // ── WebSocket preview stream ──────────────────────────────────────────────
  useEffect(() => {
    function connect() {
      const ws = openPreviewSocket(
        (blob: Blob) => {
          // Minimal-copy path: decode JPEG blob → draw directly onto canvas
          const url = URL.createObjectURL(blob);
          imgRef.current.onload = () => {
            URL.revokeObjectURL(url);
            const canvas = canvasRef.current;
            if (!canvas) return;
            const ctx2d = canvas.getContext('2d');
            if (!ctx2d) return;
            // Resize canvas only when dimensions change
            if (canvas.width !== imgRef.current.naturalWidth) {
              canvas.width  = imgRef.current.naturalWidth;
              canvas.height = imgRef.current.naturalHeight;
            }
            ctx2d.drawImage(imgRef.current, 0, 0);
          };
          imgRef.current.src = url;
        },
        () => {
          setConnected(false);
          // Reconnect after 1 s
          setTimeout(connect, 1000);
        },
      );
      wsRef.current = ws;
      ws.onopen = () => setConnected(true);
    }
    connect();
    return () => {
      wsRef.current?.close();
    };
  }, []);

  // ── Poll playback state (frame counter + play/pause sync) ─────────────────
  useEffect(() => {
    const id = setInterval(async () => {
      const state = await getPlaybackState();
      setCurrentFrame(state.frame);
      setIsPlaying(state.playing);
      setFps(state.fps);
    }, 100);
    return () => clearInterval(id);
  }, []);

  // ── Controls ──────────────────────────────────────────────────────────────

  const togglePlay = useCallback(async () => {
    if (isPlaying) {
      await playbackPause();
      setIsPlaying(false);
    } else {
      await playbackPlay();
      setIsPlaying(true);
    }
  }, [isPlaying]);

  const stepFrame = useCallback(async (dir: 1 | -1) => {
    if (isPlaying) { await playbackPause(); setIsPlaying(false); }
    const next = Math.max(0, Math.min(totalFrames - 1, currentFrame + dir));
    await playbackSeek(next);
    setCurrentFrame(next);
  }, [isPlaying, currentFrame, totalFrames]);

  // On scrub — pause then seek so the backend renders exactly that frame
  const handleScrub = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = parseInt(e.target.value, 10);
    if (isPlaying) { await playbackPause(); setIsPlaying(false); }
    await playbackSeek(f);
    setCurrentFrame(f);
  }, [isPlaying]);

  const timecode = framesToTimecode(currentFrame, fps);

  return (
    <div className={`vw-root${isFullscreen ? ' vw-root--fullscreen' : ''}`} aria-label="Preview Viewport">
      {/* Canvas — receives frames from WebSocket */}
      <div className="vw-canvas" aria-label="Video preview area">
        <canvas
          ref={canvasRef}
          className="vw-canvas__el"
          width={1920}
          height={1080}
        />
        {!connected && (
          <div className="vw-canvas__overlay">
            <div className="vw-canvas__spinner" />
            <p>Connecting to engine…</p>
          </div>
        )}
      </div>

      {/* Scrub bar */}
      <div className="vw-scrub">
        <input
          type="range"
          className="vw-scrub__bar"
          min={0}
          max={totalFrames - 1}
          step={1}
          value={Math.floor(currentFrame)}
          onChange={handleScrub}
          aria-label="Scrub timeline"
        />
      </div>

      {/* Transport controls */}
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
          <div className={`vw-ws-dot${connected ? ' vw-ws-dot--ok' : ''}`} title={connected ? 'Engine connected' : 'Connecting…'} />
          <button id="vw-fullscreen" className="vw-btn" title="Toggle fullscreen" onClick={() => setIsFullscreen(f => !f)}>
            <IconFullscreen />
          </button>
        </div>
      </div>
    </div>
  );
}
