 
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
import TrackingWorkspace from './TrackingWorkspace';
import PIIReviewPanel from './pii/PIIReviewPanel';

//   Props  

interface ImageWorkspaceProps {
  compId: string | null;
  compName: string;
  onBack?: () => void; // kept for compat but no longer rendered
  floatingMode?: boolean;
}

 
const makeImageLayoutJson = (): FlexLayout.IJsonModel => ({
  global: {
    tabEnableClose: false,
    tabEnableRename: false,
    tabSetEnableDrop: true,
    tabSetEnableMaximize: false,
    tabSetTabStripHeight: 28,
  } as any,
  borders: [],
  layout: {
     
    type: 'column',
    weight: 100,
    children: [
 
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
              { type: 'tab', name: 'Inspector',  component: 'inspector',  enableClose: false },
              { type: 'tab', name: 'Effects',     component: 'effects',    enableClose: false },
              { type: 'tab', name: 'Transitions', component: 'transitions', enableClose: false },
              { type: 'tab', name: 'Tools',       component: 'tools',      enableClose: false },
              { type: 'tab', name: 'Tracking',    component: 'tracking',   enableClose: false },
              { type: 'tab', name: 'PII',         component: 'pii',        enableClose: false },
            ],
          },
        ],
      },
 
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
//   Export  

export default function ImageWorkspace({ compId, compName, onBack, floatingMode = false }: ImageWorkspaceProps) {
  return (
    <TimelineProvider floatingMode={floatingMode}>
      <div className="video-ws image-ws-mode">
        <ImageWorkspaceInner compId={compId} compName={compName} />
      </div>
    </TimelineProvider>
  );
}

//   Module-level cache  
 
let _defaultImageCompId: string | null = null;
let _defaultImageCompName: string = 'Image Editor';
let _imgCreating = false;  // mutex: prevent concurrent auto-create

interface InnerProps { compId: string | null; compName: string; }

function ImageWorkspaceInner({ compId, compName }: InnerProps) {
  const { state, dispatch } = useTimeline();
  const { activeTool } = useTool();

  //   Resolve a real backend compId  
 
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

    // Check in-memory cache first  
    if (_defaultImageCompId) {
      setResolvedId(_defaultImageCompId);
      setResolvedName(_defaultImageCompName);
      return;
    }

    // Nothing cached  
    const port = (window as any).__FADE_PORT__ ?? 8000;
    if (_imgCreating) return;        
    _imgCreating = true;
    fetch(`http://127.0.0.1:${port}/comps`)
      .then(r => r.ok ? r.json() : null)
      .then(async (data) => {
        if (!data) return;
        const allComps: any[] = data.comps ?? [];
         
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

        // Auto-create 10 default layers for a fresh image comp
        const { addTrack } = await import('../api/useApi');
        for (let i = 1; i <= 10; i++) {
          try {
            await addTrack('video', `Layer ${i}`, created.compId);
          } catch { /* ignore individual failures */ }
        }
        window.dispatchEvent(new CustomEvent('fade:tracks-changed'));
      })
      .catch(() => {})
      .finally(() => { _imgCreating = false; });
  }, [compId, compName]);

 
  useEffect(() => {
    if (!resolvedId) return;
    dispatch({
      type: 'ENTER_COMP',
      compId: resolvedId,
      compName: resolvedName,
      kind: 'image',
    });
 
    const port = (window as any).__FADE_PORT__ ?? 8000;
    fetch(`http://127.0.0.1:${port}/comps/${resolvedId}/activate`, { method: 'POST' })
      .then(r => r.json())
      .then((data: { width?: number; height?: number; fps?: number }) => {
        if (data.width && data.height) {
          window.dispatchEvent(new CustomEvent('fade:comp-resized', {
            detail: { width: data.width, height: data.height, fps: data.fps ?? 30 }
          }));
        }
      })
      .catch(() => {});
  }, [resolvedId, resolvedName, dispatch]);


  // FlexLayout model  
  const modelRef = useRef<FlexLayout.Model>(FlexLayout.Model.fromJson(makeImageLayoutJson()));

  // Image workspace always uses its default layout  
 
  const onModelChange = useCallback((_model: FlexLayout.Model) => {
    // no-op: don't overwrite the video layout
  }, []);

  const handleAddToTimeline = useCallback(async (asset: AssetItem, trackIndex = 0) => {
    await addClipToTimeline(asset.assetId, trackIndex, 0, 90, 0, resolvedId ?? state.activeCompId);
  }, [resolvedId, state.activeCompId]);


  // Tool panel  
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

  // Render tab node content
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
      case 'tracking': {
        const selClipId = state.tracks
          .flatMap(t => t.clips)
          .find(c => c.isSelected)?.id ?? null;
        return (
          <TrackingWorkspace
            selectedClipId={selClipId}
            totalFrames={state.totalFrames}
            fps={state.fps}
          />
        );
      }
      case 'pii': {
        const selClip = state.tracks.flatMap(t => t.clips).find(c => c.isSelected)
        return (
          <PIIReviewPanel
            assetId={selClip?.assetId ?? ''}
            assetType='image'
          />
        )
      }
      default:
        return <div className="vp" />;
    }
  };

   React.useEffect(() => {
 
    let attempts = 0;
    const interval = setInterval(() => {
      const stamps = document.querySelectorAll(
        '.image-ws-mode .flexlayout__tab_button .flexlayout__tab_button_stamp'
      );
      stamps.forEach(stamp => {
        if (stamp.textContent?.trim() === 'Tools') {
          const btn = stamp.closest('.flexlayout__tab_button');
          if (btn) btn.classList.add('iw-hide-tools-tab');
        }
      });
      if (stamps.length > 0 || ++attempts > 20) clearInterval(interval);
    }, 100);
    return () => clearInterval(interval);
  }, []);

  return (
    <FlexLayout.Layout
      model={modelRef.current}
      factory={factory}
      onModelChange={onModelChange}
      realtimeResize
    />
  );
}
