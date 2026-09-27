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
  },
  borders: [],
  layout: {
    type: 'row',
    weight: 100,
    children: [
      // ── Left: Library (narrow)
      {
        type: 'tabset',
        weight: 14,
        children: [
          { type: 'tab', name: 'Library', component: 'library', enableClose: false },
        ],
      },

      // ── Center: Viewport (wide)
      {
        type: 'tabset',
        weight: 56,
        children: [
          { type: 'tab', name: 'Viewport', component: 'viewport', enableClose: false },
        ],
      },

      // ── Right: Inspector top + Layers bottom (in a column)
      {
        type: 'column',
        weight: 30,
        children: [
          // Right top — Inspector / Effects / Tools tabs
          {
            type: 'tabset',
            weight: 55,
            selected: 0,
            children: [
              { type: 'tab', name: 'Inspector',   component: 'inspector',    enableClose: false },
              { type: 'tab', name: 'Effects',     component: 'effects',      enableClose: false },
              { type: 'tab', name: 'Tools',       component: 'tools',        enableClose: false },
            ],
          },
          // Right bottom — Layers (Timeline in image mode)
          {
            type: 'tabset',
            weight: 45,
            children: [
              { type: 'tab', name: 'Layers', component: 'timeline', enableClose: false },
            ],
          },
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

// ─── Inner ────────────────────────────────────────────────────────────────────

interface InnerProps { compId: string | null; compName: string; }

function ImageWorkspaceInner({ compId, compName }: InnerProps) {
  const { state, dispatch } = useTimeline();
  const { activeTool } = useTool();

  // Force image mode in this workspace's TimelineContext.
  // We always dispatch with kind='image' so isImageComp=true applies
  // immediately — even when the user opens Image tab directly without
  // double-clicking a comp (compId may be null).
  useEffect(() => {
    dispatch({
      type: 'ENTER_COMP',
      compId: compId || '__image_workspace__',
      compName: compName || 'Image Editor',
      kind: 'image',
    });
  }, [compId, compName, dispatch]);

  // FlexLayout model (fixed — not persisted separately from video layout)
  const modelRef = useRef<FlexLayout.Model>(FlexLayout.Model.fromJson(makeImageLayoutJson()));

  // Image workspace always uses its default layout (not persisted separately)
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const onModelChange = useCallback((_model: FlexLayout.Model) => {
    // no-op: don't overwrite the video layout
  }, []);

  const handleAddToTimeline = useCallback(async (asset: AssetItem, trackIndex = 0) => {
    await addClipToTimeline(asset.assetId, trackIndex, 0, 90, 0, state.activeCompId);
  }, [state.activeCompId]);

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
