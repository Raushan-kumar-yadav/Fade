import React, { useEffect, useState } from 'react';
import { PIIDetection } from './PIITypes';
import { fetchPIIDetections } from '../../api/piiApi';
import { usePII } from '../../context/piiContext';
import { useTimeline } from '../timeline/TimelineContext';
import './PIIReviewPanel.css';

interface PIIReviewPanelProps {
  assetId: string;
  assetType: 'image' | 'video' | 'text';
}

export default function PIIReviewPanel({ assetId, assetType }: PIIReviewPanelProps) {
  const piiContext = usePII();
  const { state } = useTimeline();
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<'REVIEWING' | 'SANITIZING' | 'SANITIZED' | 'ERROR'>('REVIEWING');
  const [sanitizeResult, setSanitizeResult] = useState<{filename: string; clips: number} | null>(null);

  useEffect(() => {
    async function resolveFile() {
      if (!assetId) return;
      try {
        setLoading(true);
        const port = (window as any).__FADE_PORT__ ?? 8000;
        const res = await fetch(`http://127.0.0.1:${port}/library/raw/${assetId}`);
        if (!res.ok) throw new Error("Could not download raw asset");
        const blob = await res.blob();
        
        const extMap: Record<string, string> = {
          'image/jpeg': '.jpg',
          'image/png': '.png',
          'image/webp': '.webp',
          'video/mp4': '.mp4',
          'text/plain': '.txt'
        };
        const ext = extMap[blob.type] || '.png';
        
        // Convert to File object
        const f = new File([blob], `asset_file${ext}`, { type: blob.type });
        setFile(f);
      } catch (err) {
        console.error("Auto-resolve failed", err);
        setError("Failed to fetch asset file from library. Try restarting the backend.");
        setLoading(false);
      }
    }
    if (assetId && !file) {
      resolveFile();
    }
  }, [assetId, file]);

  useEffect(() => {
    if (file && piiContext?.detections.length === 0) {
      loadDetections(file);
    }
  }, [file]);

  // When context state changes (like moving a box), switch status back to REVIEWING
  useEffect(() => {
    if (status === 'SANITIZED') {
      setStatus('REVIEWING');
    }
  }, [piiContext?.detections]);

  const loadDetections = async (selectedFile: File) => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchPIIDetections(selectedFile);
      // Polyfill a static bbox for video detections so the user can see and edit them in the viewport!
      if (assetType === 'video') {
        data.forEach(d => {
          if (d.frames && Object.keys(d.frames).length > 0) {
            const firstFrame = Object.keys(d.frames)[0];
            d.bbox = { ...d.frames[firstFrame] };
          }
        });
      }
      if (piiContext) piiContext.setDetections(data);
    } catch (err: any) {
      setError(err.message || 'Failed to load detections');
    } finally {
      setLoading(false);
    }
  };

  const toggleEnabled = (id: string) => {
    if (!piiContext) return;
    const det = piiContext.detections.find(d => d.id === id);
    if (det) {
      piiContext.updateDetection(id, { enabled: !det.enabled });
      setStatus('REVIEWING');
    }
  };

  const handleSelect = (id: string) => {
    if (!piiContext) return;
    const newId = piiContext.selectedId === id ? null : id;
    piiContext.setSelectedId(newId);
  };

  const addManualRedaction = () => {
    if (!piiContext) return;
    const newRedaction: PIIDetection = {
      id: `manual_${Date.now()}`,
      type: 'MANUAL',
      source: 'manual',
      enabled: true,
      bbox: { x: 100, y: 100, width: 200, height: 50 }
    };
    piiContext.setDetections([...piiContext.detections, newRedaction]);
    piiContext.setSelectedId(newRedaction.id);
    setStatus('REVIEWING');
  };

  const removeRedaction = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!piiContext) return;
    piiContext.setDetections(piiContext.detections.filter(d => d.id !== id));
    if (piiContext.selectedId === id) {
      piiContext.setSelectedId(null);
    }
    setStatus('REVIEWING');
  };

  const handleSanitize = async () => {
    if (!piiContext || !assetId) return;
    setStatus('SANITIZING');
    try {
      const activeDetections = piiContext.detections.filter(d => d.enabled);

      // If video, map the user's edited static bbox across all frames
      if (assetType === 'video') {
        activeDetections.forEach(d => {
          if (d.bbox) {
            d.frames = {};
            const len = state.totalFrames || 1800;
            for (let i = 0; i < len; i++) {
              d.frames[i.toString()] = { ...d.bbox };
            }
          }
        });
      }

      // Call backend-side sanitize — saves next to original, imports to library automatically.
      // No browser download dialog.
      const port = (window as any).__FADE_PORT__ ?? 8000;
      const res = await fetch(`http://127.0.0.1:${port}/pii/sanitize-by-id`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          asset_id: assetId,
          auto_redact_all: false,          // use the user's reviewed redactions
          redactions: activeDetections,
        }),
      });
      if (!res.ok) {
        const detail = await res.text();
        throw new Error(`Sanitization failed: ${detail}`);
      }
      const result = await res.json();
      console.log(
        `[PII] Sanitized → new asset ${result.sanitizedAssetId?.slice(0, 8)} "`  +
        `${result.sanitizedFilename}" | ${result.clipsSwapped} clip(s) updated | ` +
        `${result.detectionCount} redaction(s) applied`,
      );
      setSanitizeResult({ filename: result.sanitizedFilename, clips: result.clipsSwapped ?? 0 });
      setStatus('SANITIZED');
      piiContext.setSelectedId(null);
    } catch (err: any) {
      setStatus('ERROR');
      setError(err.message || 'Sanitization failed');
    }
  };

  if (!assetId) {
    return (
      <div className="pii-panel">
        <h3>PII REVIEW</h3>
        <p style={{ color: '#94a3b8', marginTop: 12, fontSize: 13 }}>
          Select a clip on the timeline to scan it for PII.
        </p>
      </div>
    );
  }

  if (!file) {
    return (
      <div className="pii-panel">
        <h3>PII REVIEW</h3>
        {error ? (
          <div className="pii-error">{error}</div>
        ) : (
          <p>Fetching asset file...</p>
        )}
      </div>
    );
  }

  if (loading) return <div className="pii-panel"><p>Loading PII detections...</p></div>;

  const detections = piiContext?.detections || [];
  const selectedId = piiContext?.selectedId || null;

  return (
    <div className="pii-panel">
      <h3>PII REVIEW</h3>
      {error && <div className="pii-error">{error}</div>}
      
      <div className="pii-status">
        {status === 'SANITIZED' && sanitizeResult ? (
          <span style={{ color: '#4ade80' }}>
            ✓ Sanitized version saved as <strong>{sanitizeResult.filename}</strong>
            {sanitizeResult.clips > 0 && ` — ${sanitizeResult.clips} clip(s) updated on timeline`}
          </span>
        ) : (
          <span>Status: {status}</span>
        )}
      </div>

      <div className="pii-list">
        {detections.length === 0 ? <p>No PII detected.</p> : null}
        {detections.map(det => (
          <div 
            key={det.id} 
            className={`pii-item ${selectedId === det.id ? 'selected' : ''}`}
            onClick={() => handleSelect(det.id)}
          >
            <label onClick={(e) => e.stopPropagation()}>
              <input 
                type="checkbox" 
                checked={det.enabled} 
                onChange={() => toggleEnabled(det.id)}
              />
              <span className="pii-type">{det.type}</span>
              {det.confidence && <span className="pii-conf">{Math.round(det.confidence * 100)}%</span>}
            </label>
            <button className="pii-delete-btn" onClick={(e) => removeRedaction(det.id, e)} title="Remove">×</button>
          </div>
        ))}
      </div>

      <div className="pii-actions">
        <button className="pii-btn" onClick={addManualRedaction}>+ Add Redaction</button>
        <button className="pii-btn primary" onClick={handleSanitize} disabled={status === 'SANITIZING'}>
          {status === 'SANITIZING' ? 'Sanitizing...' : 'Confirm & Sanitize'}
        </button>
      </div>
    </div>
  );
}
