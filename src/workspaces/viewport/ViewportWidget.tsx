import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  openPreviewSocket,
  playbackPlay, playbackPause, playbackSeek,
  getPlaybackState, frameUrl, setPreviewScale,
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
  const [retryCount,   setRetryCount]   = useState(0);
  const [resScale,     setResScale]     = useState<number>(0.5);

  // The canvas receives decoded JPEG blobs from the WebSocket
  const canvasRef  = useRef<HTMLCanvasElement>(null);
  const wsRef      = useRef<WebSocket | null>(null);
  const imgRef     = useRef<HTMLImageElement>(new Image());

  //   WebSocket preview stream 
  useEffect(() => {
    let destroyed = false;
    let wsInst: WebSocket | null = null;

    function connect(port: number) {
      if (destroyed) return;
      const url = `ws://127.0.0.1:${port}/ws/preview`;
      const ws  = new WebSocket(url);
      wsInst = ws;
      wsRef.current = ws;

      ws.binaryType = 'arraybuffer';
      ws.onopen    = () => { if (!destroyed) { setConnected(true); setRetryCount(0); } };
      ws.onmessage = (ev: MessageEvent<ArrayBuffer>) => {
        
        if (ev.data.byteLength < 5) return;
        const view     = new DataView(ev.data);
        const frameNum = view.getUint32(0, false);          // big-endian
        setCurrentFrame(frameNum);                          // zero-lag timeline update
        const jpegBytes = ev.data.slice(4);
        const blob      = new Blob([jpegBytes], { type: 'image/jpeg' });
        const blobUrl   = URL.createObjectURL(blob);
        imgRef.current.onload = () => {
          URL.revokeObjectURL(blobUrl);
          const canvas = canvasRef.current;
          if (!canvas) return;
          const ctx2d = canvas.getContext('2d');
          if (!ctx2d) return;
          if (canvas.width !== imgRef.current.naturalWidth) {
            canvas.width  = imgRef.current.naturalWidth;
            canvas.height = imgRef.current.naturalHeight;
          }
          ctx2d.drawImage(imgRef.current, 0, 0);
        };
        imgRef.current.src = blobUrl;
      };
      ws.onerror = () => { /* will retry via onclose */ };
      ws.onclose = () => {
        if (destroyed) return;
        setConnected(false);
        setRetryCount(n => n + 1);
        // Retry after 2s — backend may be restarting
        setTimeout(() => connect(port), 2000);
      };
    }

   
    function tryConnect(port: number) {
      const t = setTimeout(() => connect(port), 150);
      return () => clearTimeout(t);
    }

    let cleanup = () => {};

    const knownPort: number | null = (window as any).__FADE_PORT__;
    if (knownPort) {
      cleanup = tryConnect(knownPort);
    } else {
      const handler = (e: Event) => {
        const port = (e as CustomEvent<number>).detail;
        cleanup = tryConnect(port);
      };
      window.addEventListener('fade:port', handler, { once: true });
      cleanup = () => window.removeEventListener('fade:port', handler);
    }

    return () => {
      destroyed = true;
      cleanup();
      wsInst?.close();
    };
  }, []);

  //   Poll playback state 
  useEffect(() => {
    let id: ReturnType<typeof setInterval> | null = null;

    function startPolling(port: number) {
      id = setInterval(async () => {
        try {
          const r = await fetch(`http://127.0.0.1:${port}/playback/state`);
          if (!r.ok) return;
          const data = await r.json();
           
          setIsPlaying(data.playing);
          setFps(data.fps);
          setTotalFrames(data.totalFrames ?? 1800);
        } catch { /* backend restarting */ }
      }, 200);
    }

    const knownPort: number | null = (window as any).__FADE_PORT__;
    if (knownPort) {
      startPolling(knownPort);
    } else {
      const handler = (e: Event) => startPolling((e as CustomEvent<number>).detail);
      window.addEventListener('fade:port', handler, { once: true });
      return () => { window.removeEventListener('fade:port', handler); };
    }

    return () => { if (id) clearInterval(id); };
  }, []);

  //   Controls  

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

  // On scrub 
  const handleScrub = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = parseInt(e.target.value, 10);
    if (isPlaying) { await playbackPause(); setIsPlaying(false); }
    await playbackSeek(f);
    setCurrentFrame(f);
  }, [isPlaying]);

  const handleResChange = useCallback(async (e: React.ChangeEvent<HTMLSelectElement>) => {
    const scale = parseFloat(e.target.value);
    setResScale(scale);
    try { await setPreviewScale(scale); } catch { /* backend busy */ }
  }, []);

  const timecode = framesToTimecode(currentFrame, fps);

  return (
    <div className={`vw-root${isFullscreen ? ' vw-root--fullscreen' : ''}`} aria-label="Preview Viewport">
      {/* Canvas  */}
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
            <p>{retryCount === 0 ? 'Connecting to engine…' : `Engine starting… (retry ${retryCount})`}</p>
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
          {/* Resolution cap dropdown */}
          <select
            id="vw-res-select"
            className="vw-res-select"
            value={resScale}
            onChange={handleResChange}
            title="Preview decode resolution"
            aria-label="Preview resolution"
          >
            <option value={1.0}>Full</option>
            <option value={0.5}>1/2</option>
            <option value={0.25}>1/4</option>
            <option value={0.125}>1/8</option>
          </select>
          <div className={`vw-ws-dot${connected ? ' vw-ws-dot--ok' : ''}`} title={connected ? 'Engine connected' : 'Connecting…'} />
          <button id="vw-fullscreen" className="vw-btn" title="Toggle fullscreen" onClick={() => setIsFullscreen(f => !f)}>
            <IconFullscreen />
          </button>
        </div>
      </div>
    </div>
  );
}
