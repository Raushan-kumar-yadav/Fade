import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  openPreviewSocket,
  playbackPlay, playbackPause, playbackSeek,
  getPlaybackState, frameUrl, setPreviewScale,
} from '../../api/useApi';
import { useTool } from '../../context/toolContext';
import { useSelection } from '../../context/selectionContext';
import OverlayCanvas from './OverlayCanvas';
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

  // Pending bitmap for next animation frame — avoids drawing stale frames
  const pendingBitmapRef = useRef<ImageBitmap | null>(null);
  const rafIdRef         = useRef<number>(0);
  // Local frame ref updated on every WS message (avoids React re-render per frame)
  const frameNumRef      = useRef<number>(0);
  // Throttled React state update (only drives scrub bar, not canvas)
  const lastStateFrameRef = useRef<number>(-1);

  //   WebSocket preview stream 
  useEffect(() => {
    let destroyed = false;
    let wsInst: WebSocket | null = null;

    // RAF loop: draws the latest decoded bitmap each display frame
    function rafLoop() {
      rafIdRef.current = requestAnimationFrame(rafLoop);
      const bmp = pendingBitmapRef.current;
      if (!bmp) return;
      pendingBitmapRef.current = null;
      const canvas = canvasRef.current;
      if (!canvas) return;
      const ctx2d = canvas.getContext('2d');
      if (!ctx2d) return;
      if (canvas.width !== bmp.width || canvas.height !== bmp.height) {
        canvas.width  = bmp.width;
        canvas.height = bmp.height;
      }
      ctx2d.drawImage(bmp, 0, 0);
      bmp.close();   // release GPU/CPU memory immediately

      // Throttle React setState to max 30/s — prevents 60 re-renders/sec
      const frame = frameNumRef.current;
      if (frame !== lastStateFrameRef.current) {
        lastStateFrameRef.current = frame;
        setCurrentFrame(frame);
      }
    }
    rafIdRef.current = requestAnimationFrame(rafLoop);

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

        // Parse frame number from 4-byte big-endian header
        const view     = new DataView(ev.data);
        const frameNum = view.getUint32(0, false);
        frameNumRef.current = frameNum;

        // Dispatch zero-lag custom event so Timeline updates immediately
        window.dispatchEvent(new CustomEvent('fade:frame', { detail: frameNum }));

        // Decode JPEG off-main-thread using createImageBitmap
        // This is much faster than Blob → BlobURL → img.onload
        const jpegBytes = ev.data.slice(4);
        const blob = new Blob([jpegBytes], { type: 'image/jpeg' });
        createImageBitmap(blob).then((bmp) => {
          // Drop previous pending bitmap if it wasn't consumed (frame-skip)
          pendingBitmapRef.current?.close();
          pendingBitmapRef.current = bmp;
        }).catch(() => {/* decode error, skip frame */});
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
      cancelAnimationFrame(rafIdRef.current);
      pendingBitmapRef.current?.close();
      pendingBitmapRef.current = null;
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

  const [canvasSize, setCanvasSize] = useState({ w: 1920, h: 1080 });
  const { activeTool, penOutputMode } = useTool();
  const { selected } = useSelection();
  const containerRef = useRef<HTMLDivElement>(null);

  // Pan / Zoom state  
  const [vpZoom, setVpZoom] = useState(1);     
  const [vpPan, setVpPan] = useState({ x: 0, y: 0 });  
  const spaceDown = useRef(false);
  const mmDown = useRef(false);   
  const lastPan = useRef({ x: 0, y: 0 });

  // Fit canvas to container on mount / resize
  const fitToFrame = useCallback(() => {
    const el = containerRef.current;
    if (!el) return;
    const { width, height } = el.getBoundingClientRect();
    const scaleW = (width - 24) / 1920;
    const scaleH = (height - 24) / 1080;
    setVpZoom(Math.min(scaleW, scaleH));
    setVpPan({ x: 0, y: 0 });
  }, []);

  useEffect(() => { fitToFrame(); }, [fitToFrame]);

  // Scroll to zoom (centered on mouse)
  const handleWheel = useCallback((e: React.WheelEvent<HTMLDivElement>) => {
    // Only zoom when Ctrl is held OR it's a trackpad pinch  
    if (!e.ctrlKey && !spaceDown.current) {
       
      return;
    }
    e.preventDefault();
    const el = containerRef.current;
    if (!el) return;
    const rect  = el.getBoundingClientRect();
    const mouseX = e.clientX - rect.left - rect.width  / 2;
    const mouseY = e.clientY - rect.top  - rect.height / 2;

    const factor = e.deltaY < 0 ? 1.12 : 1 / 1.12;
    setVpZoom(prev => {
      const next = Math.max(0.05, Math.min(8, prev * factor));
      // Adjust pan so zoom stays centred on mouse position
      const ratio = next / prev;
      setVpPan(p => ({
        x: mouseX + (p.x - mouseX) * ratio,
        y: mouseY + (p.y - mouseY) * ratio,
      }));
      return next;
    });
  }, []);

  // Middle-mouse drag to pan
  const handleMouseDown = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    const isMM    = e.button === 1;
    const isSpace = spaceDown.current && e.button === 0;
    if (!isMM && !isSpace) return;
    e.preventDefault();
    if (isMM) mmDown.current = true;
    lastPan.current = { x: e.clientX, y: e.clientY };
  }, []);

  const handleMouseMove = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    if (!mmDown.current && !spaceDown.current) return;
    if (e.buttons === 0) { mmDown.current = false; return; } // released outside
    const dx = e.clientX - lastPan.current.x;
    const dy = e.clientY - lastPan.current.y;
    lastPan.current = { x: e.clientX, y: e.clientY };
    setVpPan(p => ({ x: p.x + dx, y: p.y + dy }));
  }, []);

  const handleMouseUp = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    if (e.button === 1) mmDown.current = false;
  }, []);

  // Space key for pan mode
  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (e.code === 'Space' && !(e.target as HTMLElement).matches('input,textarea,select')) {
        e.preventDefault();
        spaceDown.current = true;
      }
      if (e.code === 'KeyF' && !(e.target as HTMLElement).matches('input,textarea,select')) {
        fitToFrame();
      }
    };
    const up = (e: KeyboardEvent) => {
      if (e.code === 'Space') {
        spaceDown.current = false;
        mmDown.current = false;
      }
    };
    window.addEventListener('keydown', down);
    window.addEventListener('keyup',   up);
    return () => {
      window.removeEventListener('keydown', down);
      window.removeEventListener('keyup',   up);
    };
  }, [fitToFrame]);

  // Track rendered canvas size for OverlayCanvas
  useEffect(() => {
    const obs = new ResizeObserver(entries => {
      for (const e of entries) {
        const { width, height } = e.contentRect;
        setCanvasSize({ w: Math.round(width * vpZoom), h: Math.round(height * vpZoom) });
      }
    });
    if (containerRef.current) obs.observe(containerRef.current);
    return () => obs.disconnect();
  }, [vpZoom]);

  const timecode = framesToTimecode(currentFrame, fps);

  return (
    <div className={`vw-root${isFullscreen ? ' vw-root--fullscreen' : ''}`} aria-label="Preview Viewport">
      {/* Canvas area  */}
      <div
        className="vw-canvas"
        ref={containerRef}
        aria-label="Video preview area"
        onWheel={handleWheel}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onDoubleClick={fitToFrame}
        style={{ cursor: spaceDown.current ? 'grab' : 'default' }}
      >
        {/*   the element that moves with pan/zoom */}
        <div
          className="vw-stage"
          style={{
            transform: `translate(${vpPan.x}px, ${vpPan.y}px) scale(${vpZoom})`,
            transformOrigin: 'center center',
          }}
        >
          <canvas
            ref={canvasRef}
            className="vw-canvas__el"
            width={1920}
            height={1080}
          />
          {/* Pen / Mask overlay — shape:path activates based on penOutputMode */}
          {activeTool === 'shape:path' && (
            penOutputMode === 'mask' && selected ? (
              <OverlayCanvas
                mode="mask"
                clipId={selected.clipId}
                width={1920}
                height={1080}
              />
            ) : (
              <OverlayCanvas
                mode="pen"
                width={1920}
                height={1080}
              />
            )
          )}

          {/* Shape draw overlay — drag to draw bounding box */}
          {activeTool !== 'shape:path' && activeTool.startsWith('shape:') && (
            <OverlayCanvas
              mode="shape"
              width={1920}
              height={1080}
            />
          )}
        </div>{/* /vw-stage */}

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
          {/* Zoom indicator + reset */}
          <button
            className="vw-zoom-btn"
            title="Zoom level — click to fit (or press F)"
            onClick={fitToFrame}
          >
            {Math.round(vpZoom * 100)}%
          </button>
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
