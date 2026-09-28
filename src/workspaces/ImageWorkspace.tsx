/**
 * ImageWorkspace.tsx
 *
 * Uses the SAME real widgets as VideoWorkspace:
 *   LibraryPanel  → left
 *   ViewportWidget → center (playback controls hidden via isImageComp)
 *   InspectorPanel / EffectsPanel → right
 *   Timeline → bottom (shows as Layers panel via isImageComp)
 *
 * The only differences vs VideoWorkspace:
 *  • Starts its own TimelineProvider and immediately dispatches ENTER_COMP
 *    so the comp is active from the first render.
 *  • Slightly different FlexLayout weights (timeline taller for layers).
 *  • A thin top-bar with comp name + "Back to Video" button.
 */
import React, { useCallback, useEffect, useRef } from 'react';
import * as FlexLayout from 'flexlayout-react';
import 'flexlayout-react/style/dark.css';
import './VideoWorkspace.css';
import './ImageWorkspace.css';
import Timeline from './timeline/Timeline';
import { TimelineProvider, useTimeline } from './timeline/TimelineContext';
import ViewportWidget from './viewport/ViewportWidget';
import LibraryPanel from './library/LibraryPanel';
import InspectorPanel from './inspector/InspectorPanel';
import EffectsPanel from './inspector/EffectsPanel';
import TransitionPanel from './inspector/TransitionPanel';
import { addClipToTimeline, type AssetItem } from '../api/useApi';
import { useTool, isShapeTool } from '../context/toolContext';
import TextToolPanel from './tools/TextToolPanel';
import BrushToolPanel from './tools/BrushToolPanel';
import EraserToolPanel from './tools/EraserToolPanel';
import ShapeToolPanel from './tools/ShapeToolPanel';

// ─── Props ────────────────────────────────────────────────────────────────────

interface ImageWorkspaceProps {
  compId: string | null;
  compName: string;
  onBack?: () => void; // kept for compat but no longer rendered
}

// ─── FlexLayout model — image editing layout ──────────────────────────────────
// Similar to VideoWorkspace but timeline is slightly taller (acts as layers)

const makeImageLayoutJson = (): FlexLayout.IJsonModel => ({
  global: {
    tabEnableClose: false,
    tabEnableRename: false,
    tabSetEnableDrop: true,
    tabSetEnableMaximize: false,
    tabSetTabStripHeight: 28,
  },
  borders: [],
  layout: {
    // ── Outer column: top-row + bottom-timeline (same as VideoWorkspace) ──
    type: 'column',
    weight: 100,
    children: [
      // ── Top row: Library | Viewport | Inspector/Effects/Transitions/Tools
      {
        type: 'row',
        weight: 72,
        children: [
          {
            type: 'tabset',
            weight: 18,
            children: [
              { type: 'tab', name: 'Library', component: 'library', enableClose: false },
            ],
          },
          {
            type: 'tabset',
            weight: 52,
            children: [
              { type: 'tab', name: 'Viewport', component: 'viewport', enableClose: false },
            ],
          },
          {
            type: 'tabset',
            weight: 30,
            selected: 0,
            children: [
              { type: 'tab', name: 'Inspector',   component: 'inspector',   enableClose: false },
              { type: 'tab', name: 'Effects',     component: 'effects',     enableClose: false },
              { type: 'tab', name: 'Transitions', component: 'transitions', enableClose: false },
              { type: 'tab', name: 'Tools',       component: 'tools',       enableClose: false },
            ],
          },
        ],
      },
      // ── Bottom: full-width Timeline (acts as Layers in image mode) ────────
      {
        type: 'tabset',
        weight: 28,
        children: [
          { type: 'tab', name: 'Timeline', component: 'timeline', enableClose: false },
        ],
      },
    ],
  },
});
// ─── Export ───────────────────────────────────────────────────────────────────

export default function ImageWorkspace({ compId, compName, onBack }: ImageWorkspaceProps) {
  return (
    <TimelineProvider>
      <div className="video-ws image-ws-mode">
        <ImageWorkspaceInner compId={compId} compName={compName} />
      </div>
    </TimelineProvider>
  );
}

// ─── Module-level cache ───────────────────────────────────────────────────────
// Persists across tab switches (component unmounts/remounts).
// Stores the last-used default image comp so we don't create a new one
// every time the user clicks the Image tab.
let _defaultImageCompId: string | null = null;
let _defaultImageCompName: string = 'Image Editor';
let _imgCreating = false;  // mutex: prevent concurrent auto-create

interface InnerProps { compId: string | null; compName: string; }

function ImageWorkspaceInner({ compId, compName }: InnerProps) {
  const { state, dispatch } = useTimeline();
  const { activeTool } = useTool();

  // ── Resolve a real backend compId ──────────────────────────────────────────
  // Priority:
  //   1. Explicit compId passed from App (user double-clicked an image comp)
  //   2. Module-level cache (_defaultImageCompId) — survives tab switches
  //   3. First existing image comp found via GET /comps
  //   4. Auto-create a new image comp (only when truly none exists)
  const [resolvedId,   setResolvedId]   = React.useState<string | null>(compId ?? _defaultImageCompId);
  const [resolvedName, setResolvedName] = React.useState(compName || _defaultImageCompName);

  useEffect(() => {
    if (compId) {
      // Explicit comp provided — always respect it.
      _defaultImageCompId   = compId;
      _defaultImageCompName = compName || 'Image Editor';
      setResolvedId(compId);
      setResolvedName(compName || 'Image Editor');
      return;
    }

    // Check in-memory cache first (avoids network round-trip on tab switch).
    if (_defaultImageCompId) {
      setResolvedId(_defaultImageCompId);
      setResolvedName(_defaultImageCompName);
      return;
    }

    // Nothing cached — query the backend for an existing image comp.
    const port = (window as any).__FADE_PORT__ ?? 8000;
    if (_imgCreating) return;          // another instance is already fetching
    _imgCreating = true;
    fetch(`http://127.0.0.1:${port}/comps`)
      .then(r => r.ok ? r.json() : null)
      .then(async (data) => {
        if (!data) return;
        const allComps: any[] = data.comps ?? [];
        // Prefer the marked default; fall back to any non-hidden image comp.
        const existing =
          allComps.find((c: any) => c.kind === 'image' && c.isDefault) ||
          allComps.find((c: any) => c.kind === 'image' && !c.isHidden);
        if (existing) {
          _defaultImageCompId   = existing.compId;
          _defaultImageCompName = existing.name || 'Image Editor';
          setResolvedId(existing.compId);
          setResolvedName(existing.name || 'Image Editor');
          return;
        }
        // No image comp exists yet — create exactly one, marked as default.
        const res = await fetch(`http://127.0.0.1:${port}/comps`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name: 'Image Editor', kind: 'image', width: 1920, height: 1080, isDefault: true }),
        });
        const created = res.ok ? await res.json() : null;
        if (!created?.compId) return;
        _defaultImageCompId   = created.compId;
        _defaultImageCompName = created.name || 'Image Editor';
        setResolvedId(created.compId);
        setResolvedName(created.name || 'Image Editor');
      })
      .catch(() => {})
      .finally(() => { _imgCreating = false; });
  }, [compId, compName]);

  // Dispatch ENTER_COMP only once we have a real backend compId.
  useEffect(() => {
    if (!resolvedId) return;
    dispatch({
      type: 'ENTER_COMP',
      compId: resolvedId,
      compName: resolvedName,
      kind: 'image',
    });
    // Activate on the backend so renders go to this comp.
    const port = (window as any).__FADE_PORT__ ?? 8000;
    fetch(`http://127.0.0.1:${port}/comps/${resolvedId}/activate`, { method: 'POST' }).catch(() => {});
  }, [resolvedId, resolvedName, dispatch]);

  // FlexLayout model (fixed — not persisted separately from video layout)
  const modelRef = useRef<FlexLayout.Model>(FlexLayout.Model.fromJson(makeImageLayoutJson()));

  // Image workspace always uses its default layout (not persisted separately)
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const onModelChange = useCallback((_model: FlexLayout.Model) => {
    // no-op: don't overwrite the video layout
  }, []);

  const handleAddToTimeline = useCallback(async (asset: AssetItem, trackIndex = 0) => {
    await addClipToTimeline(asset.assetId, trackIndex, 0, 90, 0, resolvedId ?? state.activeCompId);
  }, [resolvedId, state.activeCompId]);


  // Tool panel — identical to VideoWorkspace
  const toolPanel = (() => {
    const frame = state.currentFrame ?? 0;
    if (activeTool === 'brush') return <BrushToolPanel key="brush" />;
    if (activeTool === 'eraser') return <EraserToolPanel key="eraser" />;
    if (activeTool === 'text') {
      return (
        <TextToolPanel
          currentFrame={frame}
          onCreated={clip => console.log('[Fade] text clip created', clip.clipId)}
        />
      );
    }
    if (isShapeTool(activeTool)) {
      return (
        <ShapeToolPanel
          currentFrame={frame}
          onCreated={clip => console.log('[Fade] shape clip created', clip.clipId)}
        />
      );
    }
    return (
      <div className="vp vp--props" style={{ padding: 12, color: '#475569', fontSize: 11 }}>
        Select a creation tool (T / Q / P) to use here.
      </div>
    );
  })();

  const factory = (node: FlexLayout.TabNode) => {
    switch (node.getComponent()) {
      case 'library':
        return <LibraryPanel onAddToTimeline={handleAddToTimeline} />;
      case 'viewport':
        return <ViewportWidget />;
      case 'timeline':
        return (
          <div className="vp vp--timeline"><Timeline /></div>
        );
      case 'inspector':
        return <InspectorPanel />;
      case 'effects':
        return <EffectsPanel />;
      case 'transitions':
        return <TransitionPanel />;
      case 'tools':
        return toolPanel;
      default:
        return <div className="vp" />;
    }
  };

  return (
    <FlexLayout.Layout
      model={modelRef.current}
      factory={factory}
      onModelChange={onModelChange}
      realtimeResize
    />
  );
}
