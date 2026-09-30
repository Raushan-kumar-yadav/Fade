 
import React, { useCallback, useEffect, useRef, useState } from 'react';
import * as FlexLayout from 'flexlayout-react';
import 'flexlayout-react/style/dark.css';
import '../VideoWorkspace.css';
import '../ImageWorkspace.css';
import Timeline from '../timeline/Timeline';
import { TimelineProvider, useTimeline } from '../timeline/TimelineContext';
import ViewportWidget from '../viewport/ViewportWidget';
import InspectorPanel from '../inspector/InspectorPanel';
import EffectsPanel from '../inspector/EffectsPanel';
import TransitionPanel from '../inspector/TransitionPanel';
import { useTool, isShapeTool } from '../../context/toolContext';
import TextToolPanel from '../tools/TextToolPanel';
import BrushToolPanel from '../tools/BrushToolPanel';
import EraserToolPanel from '../tools/EraserToolPanel';
import ShapeToolPanel from '../tools/ShapeToolPanel';
import PagesPanel, { type PdfPage } from './PagesPanel';
import LibraryPanel from '../library/LibraryPanel';
import { type AssetItem } from '../../api/useApi';

// PdfTimeline 
function PdfTimeline() {
  return <Timeline />;
}


// FlexLayout model  

const makePdfLayoutJson = (): FlexLayout.IJsonModel => ({
  global: {
    tabEnableClose: false,
    tabEnableRename: false,
    tabSetEnableDrop: true,
    tabSetEnableMaximize: false,
    tabSetTabStripHeight: 28,
  },
  borders: [],
  layout: {
    type: 'column',
    weight: 100,
    children: [
      // Top row: Pages | Viewport | Inspector tabs
      {
        type: 'row',
        weight: 72,
        children: [
          // Left
          {
            type: 'tabset',
            weight: 15,
            children: [
              { type: 'tab', name: 'Pages',   component: 'pages',   enableClose: false },
              { type: 'tab', name: 'Library', component: 'library', enableClose: false },
            ],
          },
          // Center  
          {
            type: 'tabset',
            weight: 55,
            children: [
              { type: 'tab', name: 'Viewport', component: 'viewport', enableClose: false },
            ],
          },
          // Right  
          {
            type: 'tabset',
            weight: 30,
            selected: 0,
            children: [
              { type: 'tab', name: 'Inspector', component: 'inspector', enableClose: false },
              { type: 'tab', name: 'Effects', component: 'effects', enableClose: false },
              { type: 'tab', name: 'Transitions', component: 'transitions', enableClose: false },
              { type: 'tab', name: 'Tools', component: 'tools', enableClose: false },
            ],
          },
        ],
      },
      // Bottom  
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

//   Module-level PDF doc cache  

let _defaultPdfDocId: string | null = null;
let _defaultPdfDocName: string = 'Untitled Document';
let _defaultPageId: string | null = null;  
let _pdfCreating = false; // mutex: prevent concurrent auto-create

// Export  

interface PdfWorkspaceProps {
  docId?: string | null;
  docName?: string;
}

export default function PdfWorkspace({ docId, docName }: PdfWorkspaceProps) {
  return (
    <TimelineProvider>
      <div className="video-ws image-ws-mode pdf-ws-mode">
        <PdfWorkspaceInner docId={docId ?? null} docName={docName ?? 'Untitled Document'} />
      </div>
    </TimelineProvider>
  );
}

//   Inner  

function PdfWorkspaceInner({ docId, docName }: { docId: string | null; docName: string }) {
  const { state, dispatch } = useTimeline();
  const { activeTool } = useTool();
  const port = (window as any).__FADE_PORT__ ?? 8000;

  //   Resolve PDF doc  
  const [resolvedDocId, setResolvedDocId] = useState<string | null>(docId ?? _defaultPdfDocId);
  const [resolvedDocName, setResolvedDocName] = useState(docName || _defaultPdfDocName);
  const [activePageId, setActivePageId] = useState<string | null>(_defaultPageId);

  // Track the previous resolved doc so we can reset page state on doc switch
  const prevDocIdRef = useRef<string | null>(null);

  useEffect(() => {
    if (docId) {
      const isNewDoc = docId !== prevDocIdRef.current;
      if (isNewDoc) {
        // Switching to a different PDF doc — reset page state immediately
        prevDocIdRef.current = docId;
        _defaultPdfDocId   = docId;
        _defaultPdfDocName = docName || 'Untitled Document';
        _defaultPageId     = null;
        setActivePageId(null);
        setResolvedDocId(docId);
        setResolvedDocName(docName || 'Untitled Document');
      } else {
        // Same doc re-render — just sync name
        setResolvedDocName(docName || 'Untitled Document');
      }
      return;
    }
    if (_defaultPdfDocId) {
      setResolvedDocId(_defaultPdfDocId);
      setResolvedDocName(_defaultPdfDocName);
      return;
    }
    // Check backend  
    if (_pdfCreating) return;        
    _pdfCreating = true;
    fetch(`http://127.0.0.1:${port}/pdf-docs`)
      .then(r => r.ok ? r.json() : null)
      .then(async data => {
        const allDocs: any[] = data?.docs ?? [];
 
        const existing =
          allDocs.find((d: any) => d.isDefault) ||
          allDocs[0];
        if (existing) {
          _defaultPdfDocId = existing.docId;
          _defaultPdfDocName = existing.name || 'Untitled Document';
          prevDocIdRef.current = existing.docId;
          setResolvedDocId(existing.docId);
          setResolvedDocName(existing.name || 'Untitled Document');
          return;
        }
        // No PDF doc yet  
        const res = await fetch(`http://127.0.0.1:${port}/pdf-docs`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name: 'Untitled Document' }),
        });
        const created = res.ok ? await res.json() : null;
        if (!created?.docId) return;
        _defaultPdfDocId = created.docId;
        _defaultPdfDocName = created.name || 'Untitled Document';
        prevDocIdRef.current = created.docId;
        setResolvedDocId(created.docId);
        setResolvedDocName(created.name || 'Untitled Document');
 
        if (created.pageIds?.length > 0) {
          handleSelectPage({ index: 0, pageId: created.pageIds[0], compId: created.pageIds[0], name: 'Page 1' });
        }
      })
      .catch(() => {})
      .finally(() => { _pdfCreating = false; });
  }, [docId, docName]);  

  // Select a page  
  const handleSelectPage = useCallback((page: PdfPage) => {
    _defaultPageId = page.compId;
    setActivePageId(page.compId);
    // Swap the active comp in-place 
    dispatch({ type: 'SWAP_PDF_PAGE', compId: page.compId, compName: page.name });
 
    fetch(`http://127.0.0.1:${port}/comps/${page.compId}/activate`, { method: 'POST' })
      .then(r => r.json())
      .then((data: { width?: number; height?: number; fps?: number }) => {
        // Force immediate track refresh
        window.dispatchEvent(new Event('fade:tracks-changed'));
        // Tell the viewport to resize the C++ render engine + safe-area box
        if (data.width && data.height) {
          window.dispatchEvent(new CustomEvent('fade:comp-resized', {
            detail: { width: data.width, height: data.height, fps: data.fps ?? 30 }
          }));
        }
      })
      .catch(() => {});
  }, [dispatch, port]);


 
  const handleAddToTimeline = useCallback(async (asset: AssetItem, trackIndex = 0) => {
    if (!activePageId) return;
    try {
      await fetch(`http://127.0.0.1:${port}/clips`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ assetId: asset.assetId, startFrame: state.currentFrame ?? 0, trackIndex }),
      });
    } catch { /* silent */ }
  }, [activePageId, port, state.currentFrame]);

  // On first doc resolve 
  useEffect(() => {
    if (!resolvedDocId) return;
    fetch(`http://127.0.0.1:${port}/pdf-docs/${resolvedDocId}/pages`)
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        const first = data?.pages?.[0];
        if (first) handleSelectPage({ index: 0, pageId: first.pageId, compId: first.compId, name: first.name });
      })
      .catch(() => {});
  }, [resolvedDocId]);  

  //   FlexLayout model  
  const modelRef = useRef<FlexLayout.Model>(FlexLayout.Model.fromJson(makePdfLayoutJson()));
  const onModelChange = useCallback((_m: FlexLayout.Model) => { /* no-op */ }, []);

  //   Tool panel  
  const toolPanel = (() => {
    const frame = state.currentFrame ?? 0;
    if (activeTool === 'brush')  return <BrushToolPanel key="brush" />;
    if (activeTool === 'eraser') return <EraserToolPanel key="eraser" />;
    if (activeTool === 'text') return (
      <TextToolPanel currentFrame={frame} onCreated={() => {}} />
    );
    if (isShapeTool(activeTool)) return (
      <ShapeToolPanel currentFrame={frame} onCreated={() => {}} />
    );
    return (
      <div className="vp vp--props" style={{ padding: 12, color: '#475569', fontSize: 11 }}>
        Select a creation tool (T / Q / P) to use here.
      </div>
    );
  })();

  //   Factory  
  const factory = (node: FlexLayout.TabNode) => {
    switch (node.getComponent()) {
      case 'pages':
        return resolvedDocId
          ? <PagesPanel docId={resolvedDocId} activePageId={activePageId} onSelectPage={handleSelectPage} />
          : <div className="vp" style={{ padding: 16, color: '#475569', fontSize: 12 }}>Loading document…</div>;
      case 'library': return <LibraryPanel onAddToTimeline={handleAddToTimeline} />;
      case 'viewport': return <ViewportWidget />;
      case 'timeline': return <div className="vp vp--timeline"><PdfTimeline /></div>;
      case 'inspector': return <InspectorPanel />;
      case 'effects': return <EffectsPanel />;
      case 'transitions': return <TransitionPanel />;
      case 'tools': return toolPanel;
      default: return <div className="vp" />;
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
