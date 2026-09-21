/**
 * fade-react.js  —  Echo WebComp React Runtime  (v1.0)
 *
 * Provides Remotion-compatible hooks for writing React-based WebComp templates.
 * Load AFTER react.production.min.js and react-dom.production.min.js.
 *
 * How it works
 * -------------
 * Electron injects per-frame globals via executeJavaScript():
 *   window.FADE_FRAME, window.FADE_TIME, window.FADE_FPS,
 *   window.FADE_WIDTH, window.FADE_HEIGHT, window.FADE_PARAMS
 * then fires:  window.dispatchEvent(new CustomEvent('fade:frame', {...}))
 *              window.dispatchEvent(new CustomEvent('fade:params', {...}))
 *
 * This runtime subscribes to those events and re-renders React components.
 *
 * Usage
 * -----
 * <script src="https://unpkg.com/react@18/umd/react.production.min.js"></script>
 * <script src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js"></script>
 * <script src="../../_runtime/fade-react.js"></script>
 * <script type="text/babel" src="./composition.jsx"></script>
 *
 * In composition.jsx:
 *   const { FadeComposition, useCurrentFrame, useVideoConfig, interpolate, spring } = window.FadeReact;
 */
(function (global) {
  'use strict';
  const React    = global.React;
  const ReactDOM = global.ReactDOM;
  if (!React || !ReactDOM) {
    console.error('[echo-react] React and ReactDOM must be loaded first'); return;
  }

  // -- Internal state -------------------------------------------------------
  let _frame  = global.FADE_FRAME  ?? 0;
  let _fps    = global.FADE_FPS    ?? 30;
  let _width  = global.FADE_WIDTH  ?? 1920;
  let _height = global.FADE_HEIGHT ?? 1080;
  let _params = global.FADE_PARAMS ?? {};
  const _subs = new Set();
  function _notify() { for (const fn of _subs) fn(); }

  global.addEventListener('fade:frame', (e) => {
    _frame  = e.detail?.frame ?? global.FADE_FRAME ?? _frame;
    _fps    = global.FADE_FPS    ?? _fps;
    _width  = global.FADE_WIDTH  ?? _width;
    _height = global.FADE_HEIGHT ?? _height;
    _notify();
  });
  global.addEventListener('fade:params', (e) => {
    _params = Object.assign({}, _params, e.detail);
    _notify();
  });

  // -- VideoContext ---------------------------------------------------------
  const VideoContext = React.createContext({ frame:0, fps:30, width:1920, height:1080, durationFrames:150, params:{} });

  // -- <FadeComposition> ----------------------------------------------------
  function FadeComposition({ durationFrames, children }) {
    const dur = durationFrames ?? global.FADE_DURATION ?? 150;
    const [ctx, setCtx] = React.useState(() => ({
      frame:_frame, fps:_fps, width:_width, height:_height, durationFrames:dur, params:_params
    }));
    React.useEffect(() => {
      const upd = () => setCtx({ frame:_frame, fps:_fps, width:_width, height:_height, durationFrames:dur, params:_params });
      _subs.add(upd); upd();
      return () => _subs.delete(upd);
    }, [dur]);
    return React.createElement(VideoContext.Provider, { value: ctx }, children);
  }

  // -- Hooks ----------------------------------------------------------------
  function useCurrentFrame()  { return React.useContext(VideoContext).frame; }
  function useVideoConfig()   { const { frame, params, ...c } = React.useContext(VideoContext); return c; }
  function useParams()        { return React.useContext(VideoContext).params; }

  // -- interpolate ---------------------------------------------------------
  function interpolate(value, inputRange, outputRange, options = {}) {
    const [inMin, inMax] = inputRange;
    const [outMin, outMax] = outputRange;
    let t = (value - inMin) / (inMax - inMin);
    if (options.extrapolateLeft  !== 'extend' && t < 0) t = 0;
    if (options.extrapolateRight !== 'extend' && t > 1) t = 1;
    const easedT = options.easing ? options.easing(t) : t;
    return outMin + easedT * (outMax - outMin);
  }

  // -- spring ---------------------------------------------------------------
  function spring({ frame = 0, fps = 30, config = {}, delay = 0, from = 0, to = 1 } = {}) {
    const { mass = 1, damping = 10, stiffness = 100 } = config;
    const f = Math.max(0, frame - delay);
    const omega = Math.sqrt(stiffness / mass);
    const zeta  = damping / (2 * Math.sqrt(stiffness * mass));
    if (zeta < 1) {
      const omegaD = omega * Math.sqrt(1 - zeta * zeta);
      const t = f / fps;
      const env = Math.exp(-zeta * omega * t);
      const val = 1 - env * (Math.cos(omegaD * t) + (zeta * omega / omegaD) * Math.sin(omegaD * t));
      return from + (to - from) * Math.min(1, Math.max(0, val));
    }
    return from + (to - from) * Math.min(1, (f / fps) / 0.5);
  }

  // -- Easing ---------------------------------------------------------------
  const Easing = {
    linear:  t => t,
    ease:    t => t < 0.5 ? 2*t*t : -1+(4-2*t)*t,
    in:      fn => fn,
    out:     fn => t => 1 - fn(1 - t),
    inOut:   fn => t => t < 0.5 ? fn(t * 2) / 2 : 1 - fn((1 - t) * 2) / 2,
    cubic:   t => t * t * t,
    quad:    t => t * t,
    elastic: t => t === 0 ? 0 : t === 1 ? 1 : -Math.pow(2, 10*t-10)*Math.sin((t*10-10.75)*(2*Math.PI/3)),
    bounce:  t => {
      const n1=7.5625, d1=2.75;
      if (t < 1/d1)       return n1*t*t;
      if (t < 2/d1)       return n1*(t-=1.5/d1)*t+0.75;
      if (t < 2.5/d1)     return n1*(t-=2.25/d1)*t+0.9375;
      return n1*(t-=2.625/d1)*t+0.984375;
    },
  };

  // -- mount helper ---------------------------------------------------------
  function mount(element, container) {
    const el = container ?? document.getElementById('root') ?? (() => {
      const d = document.createElement('div'); document.body.appendChild(d); return d;
    })();
    const root = ReactDOM.createRoot(el);
    root.render(element);
    return root;
  }

  // -- Export ---------------------------------------------------------------
  global.FadeReact = {
    FadeComposition, VideoContext,
    useCurrentFrame, useVideoConfig, useParams,
    interpolate, spring, Easing,
    mount,
    React, ReactDOM,
  };
  console.log('[echo-react] Runtime v1.0 ready');
})(window);
