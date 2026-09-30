import React, { useState, useEffect, useCallback } from 'react';
import './TrackingPanel.css';

interface TrackingPanelProps {
  clipId: string;
  startFrame: number;
  duration: number;
}

interface TrackingResultSummary {
  id: string;
  startFrame: number | null;
  endFrame: number | null;
  frameCount: number;
  targetText: string | null;
  targetType: string | null;
  property: string | null;
  sourceClipId: string;
}

export default function TrackingPanel({ clipId, startFrame, duration }: TrackingPanelProps) {
  const [open, setOpen] = useState(false);

  // --- New tracking params ---
  const [trackStart, setTrackStart] = useState(startFrame);
  const [trackEnd, setTrackEnd] = useState(startFrame + Math.min(30, duration));
  const [property, setProperty] = useState('position');
  const [x, setX] = useState(860);
  const [y, setY] = useState(440);
  const [w, setW] = useState(100);
  const [h, setH] = useState(100);

  // --- Target detection ---
  const [targetType, setTargetType] = useState<'manual' | 'text' | 'image'>('manual');
  const [targetText, setTargetText] = useState('');
  const [targetImage, setTargetImage] = useState<string | null>(null);
  const [isDetecting, setIsDetecting] = useState(false);

  // --- Job / tracking state ---
  const [status, setStatus] = useState('');
  const [jobId, setJobId] = useState<string | null>(null);
  const [trackingId, setTrackingId] = useState<string | null>(null);
  // sourceClipId returned from /tracking/track so cross-clip expr uses the correct video clip id
  const [sourceClipId, setSourceClipId] = useState<string>(clipId);

  // --- Existing results history ---
  const [existingResults, setExistingResults] = useState<TrackingResultSummary[]>([]);
  const [loadingResults, setLoadingResults] = useState(false);

  const port = () => (window as any).__FADE_PORT__ ?? 8000;

  // Fetch existing tracking results when panel opens
  const fetchResults = useCallback(async () => {
    setLoadingResults(true);
    try {
      const res = await fetch(`http://127.0.0.1:${port()}/tracking/clip/${clipId}/results`);
      if (res.ok) {
        const data = await res.json();
        setExistingResults(Object.values(data) as TrackingResultSummary[]);
      }
    } catch (_) {}
    setLoadingResults(false);
  }, [clipId]);

  useEffect(() => {
    if (open) fetchResults();
  }, [open, fetchResults]);

  // Poll job progress
  useEffect(() => {
    if (!jobId) return;
    const interval = setInterval(async () => {
      try {
        const res = await fetch(`http://127.0.0.1:${port()}/jobs/${jobId}`);
        if (!res.ok) return;
        const job = await res.json();
        if (job.status === 'running' || job.status === 'pending') {
          setStatus(`Tracking… ${Math.round((job.progress || 0) * 100)}%`);
        } else if (job.status === 'done') {
          setStatus('Tracking complete ✓');
          if (job.result?.tracking_id) setTrackingId(job.result.tracking_id);
          setJobId(null);
          fetchResults(); // refresh history
        } else if (job.status === 'error') {
          setStatus(`Error: ${job.error}`);
          setJobId(null);
        } else if (job.status === 'cancelled') {
          setStatus('Cancelled');
          setJobId(null);
        }
      } catch (_) {}
    }, 500);
    return () => clearInterval(interval);
  }, [jobId, fetchResults]);

  // --- Handlers ---
  const handleDetect = async () => {
    setIsDetecting(true);
    setStatus('Detecting target…');
    try {
      const res = await fetch(`http://127.0.0.1:${port()}/tracking/detect-target`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          clip_id: clipId,
          frame: trackStart,
          target_type: targetType,
          target_text: targetText,
          reference_image: targetImage,
        }),
      });
      if (res.ok) {
        const data = await res.json();
        setX(data.x);
        setY(data.y);
        setW(data.width);
        setH(data.height);
        setStatus(`Detected! Confidence: ${Math.round(data.confidence * 100)}%`);
      } else {
        const err = await res.json().catch(() => ({}));
        setStatus(`Not found: ${err.detail ?? 'Unknown error'}`);
      }
    } catch (e: any) {
      setStatus(`Connection failed: ${e.message}`);
    } finally {
      setIsDetecting(false);
    }
  };

  const handleImageUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => setTargetImage(ev.target?.result as string);
    reader.readAsDataURL(file);
  };

  const handleTrack = async () => {
    setStatus('Starting tracking job…');
    setTrackingId(null);
    try {
      const res = await fetch(`http://127.0.0.1:${port()}/tracking/track`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          clip_id: clipId,
          start_frame: trackStart,
          end_frame: trackEnd,
          property,
          x, y, width: w, height: h,
          target_text: targetType !== 'manual' ? targetText : null,
          target_type: targetType !== 'manual' ? targetType : null,
        }),
      });
      if (res.ok) {
        const data = await res.json();
        setJobId(data.jobId);
        setSourceClipId(data.clipId ?? clipId);
        setStatus('Job queued…');
      } else {
        const err = await res.json().catch(() => ({}));
        setStatus(`Error: ${err.detail}`);
      }
    } catch (e: any) {
      setStatus(`Connection failed: ${e.message}`);
    }
  };

  // Apply tracking expression to THIS video clip's own position
  const handleApplyToSelf = async (tid: string) => {
    setStatus('Applying to this clip…');
    try {
      const res = await fetch(`http://127.0.0.1:${port()}/tracking/bind`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          clip_id: clipId,
          property_name: property,
          expression: `this.tracking('${tid}')`,
        }),
      });
      if (res.ok) {
        setStatus('Applied to this clip ✓');
      } else {
        const err = await res.json().catch(() => ({}));
        setStatus(`Error: ${err.detail}`);
      }
    } catch (e: any) {
      setStatus(`Connection failed: ${e.message}`);
    }
  };

  const crossClipExpr = (tid: string, srcClipId: string) =>
    `comp.clip('${srcClipId}').tracking('${tid}')`;

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text).then(
      () => setStatus('Copied to clipboard ✓'),
      () => setStatus('Copy failed — select manually'),
    );
  };

  // --- Styles ---
  const sLabel: React.CSSProperties = { color: '#9ca3af', fontSize: '11px', minWidth: 88 };
  const sRow: React.CSSProperties = { display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '3px 10px' };
  const sNum: React.CSSProperties = { width: 50, background: '#1e1e1e', border: '1px solid #333', color: '#ccc', padding: '2px 4px', fontSize: '11px', borderRadius: 3 };
  const sSelect: React.CSSProperties = { background: '#1e1e1e', border: '1px solid #333', color: '#ccc', fontSize: '11px', padding: '2px 4px', borderRadius: 3 };
  const sBtn = (accent = true): React.CSSProperties => ({
    flex: 1, background: accent ? '#3b82f6' : '#374151', color: '#fff',
    border: 'none', borderRadius: 4, padding: '5px 6px', fontSize: '11px', cursor: 'pointer',
  });
  const sDisabled: React.CSSProperties = { background: '#374151', color: '#6b7280', cursor: 'not-allowed' };

  return (
    <div style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
      {/* Header */}
      <div
        onClick={() => setOpen(o => !o)}
        style={{
          display: 'flex', alignItems: 'center', gap: 6,
          padding: '5px 8px', background: '#1e293b', cursor: 'pointer',
          userSelect: 'none', fontSize: '11px', fontWeight: 600, color: '#94a3b8',
          borderTop: '1px solid rgba(255,255,255,0.06)',
        }}
      >
        <span style={{ fontSize: 9, transition: 'transform 0.15s', transform: open ? 'rotate(90deg)' : 'rotate(0deg)', display: 'inline-block' }}>▶</span>
        MOTION TRACKING
        {existingResults.length > 0 && (
          <span style={{ marginLeft: 'auto', fontSize: '9px', color: '#6366f1', background: '#1e1b4b', borderRadius: 8, padding: '1px 5px' }}>
            {existingResults.length} result{existingResults.length > 1 ? 's' : ''}
          </span>
        )}
      </div>

      {open && (
        <div style={{ paddingBottom: 8, background: '#0f172a' }}>

          {/* ── Existing tracking results ── */}
          {existingResults.length > 0 && (
            <div style={{ padding: '6px 10px', borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
              <div style={{ fontSize: '10px', color: '#6366f1', fontWeight: 600, marginBottom: 4 }}>
                EXISTING TRACKING RESULTS
              </div>
              {loadingResults && <div style={{ fontSize: '10px', color: '#6b7280' }}>Loading…</div>}
              {existingResults.map(r => (
                <div key={r.id} style={{ background: '#1e293b', borderRadius: 4, padding: '5px 8px', marginBottom: 4, fontSize: '10px' }}>
                  <div style={{ color: '#e2e8f0', fontWeight: 600 }}>{r.id}</div>
                  {r.targetText && <div style={{ color: '#94a3b8' }}>Target: "{r.targetText}" ({r.targetType})</div>}
                  <div style={{ color: '#94a3b8' }}>
                    Frames {r.startFrame}–{r.endFrame} · {r.frameCount} points · {r.property ?? 'position'}
                  </div>
                  {/* Cross-clip expression — the key missing piece */}
                  <div style={{ marginTop: 4, background: '#0f172a', borderRadius: 3, padding: '3px 5px', fontFamily: 'monospace', color: '#818cf8', fontSize: '9px', wordBreak: 'break-all' }}>
                    {crossClipExpr(r.id, r.sourceClipId)}
                  </div>
                  <div style={{ display: 'flex', gap: 4, marginTop: 4 }}>
                    <button
                      onClick={() => copyToClipboard(crossClipExpr(r.id, r.sourceClipId))}
                      style={{ ...sBtn(false), flex: 'none', padding: '2px 7px', fontSize: '9px' }}
                    >
                      Copy expression
                    </button>
                    <button
                      onClick={() => { setTrackingId(r.id); setSourceClipId(r.sourceClipId); setStatus(`Loaded: ${r.id}`); }}
                      style={{ ...sBtn(false), flex: 'none', padding: '2px 7px', fontSize: '9px' }}
                    >
                      Select
                    </button>
                  </div>
                </div>
              ))}
              <div style={{ fontSize: '9px', color: '#4b5563', marginTop: 2 }}>
                💡 Copy expression → paste into another clip's Position X or Y expression field
              </div>
            </div>
          )}

          {/* ── New tracking controls ── */}
          <div style={sRow}>
            <span style={sLabel}>Start Frame</span>
            <input type="number" value={trackStart} onChange={e => setTrackStart(Number(e.target.value))} style={sNum} />
          </div>
          <div style={sRow}>
            <span style={sLabel}>End Frame</span>
            <input type="number" value={trackEnd} onChange={e => setTrackEnd(Number(e.target.value))} style={sNum} />
          </div>

          <div style={sRow}>
            <span style={sLabel}>Target Type</span>
            <select value={targetType} onChange={e => setTargetType(e.target.value as any)} style={sSelect}>
              <option value="manual">Manual</option>
              <option value="text">Text (OCR)</option>
              <option value="image">Image Match</option>
            </select>
          </div>

          {targetType === 'text' && (
            <div style={sRow}>
              <span style={sLabel}>Target Text</span>
              <input type="text" value={targetText} onChange={e => setTargetText(e.target.value)} style={{ ...sNum, width: 110 }} />
            </div>
          )}
          {targetType === 'image' && (
            <div style={sRow}>
              <span style={sLabel}>Ref Image</span>
              <input type="file" accept="image/*" onChange={handleImageUpload} style={{ fontSize: '9px', width: 120 }} />
            </div>
          )}

          {targetType !== 'manual' && (
            <div style={{ padding: '4px 10px' }}>
              <button onClick={handleDetect} disabled={isDetecting} style={isDetecting ? { ...sBtn(), ...sDisabled, flex: 'none', width: '100%' } : { ...sBtn(), flex: 'none', width: '100%' }}>
                {isDetecting ? 'Detecting…' : '🔍 Find Target'}
              </button>
            </div>
          )}

          <div style={sRow}>
            <span style={sLabel}>Box X / Y</span>
            <div style={{ display: 'flex', gap: 3 }}>
              <input type="number" value={Math.round(x)} onChange={e => setX(Number(e.target.value))} style={sNum} title="X" />
              <input type="number" value={Math.round(y)} onChange={e => setY(Number(e.target.value))} style={sNum} title="Y" />
            </div>
          </div>
          <div style={sRow}>
            <span style={sLabel}>W / H</span>
            <div style={{ display: 'flex', gap: 3 }}>
              <input type="number" value={Math.round(w)} onChange={e => setW(Number(e.target.value))} style={sNum} title="W" />
              <input type="number" value={Math.round(h)} onChange={e => setH(Number(e.target.value))} style={sNum} title="H" />
            </div>
          </div>

          <div style={sRow}>
            <span style={sLabel}>Apply to</span>
            <select value={property} onChange={e => setProperty(e.target.value)} style={sSelect}>
              <option value="position">Position</option>
              <option value="scale">Scale</option>
            </select>
          </div>

          <div style={{ display: 'flex', gap: 6, padding: '6px 10px 2px' }}>
            <button
              onClick={handleTrack}
              disabled={jobId !== null}
              style={jobId !== null ? { ...sBtn(), ...sDisabled } : sBtn()}
            >
              {jobId ? 'Tracking…' : '▶ Start Tracking'}
            </button>
            <button
              onClick={() => trackingId && handleApplyToSelf(trackingId)}
              disabled={!trackingId}
              style={!trackingId ? { ...sBtn(false), ...sDisabled } : sBtn(false)}
              title="Apply tracking to this clip's own position (moves the video)"
            >
              Apply to self
            </button>
          </div>

          {/* Status */}
          {status && (
            <div style={{
              padding: '3px 10px', fontSize: '10px', wordBreak: 'break-word',
              color: status.startsWith('Error') || status.startsWith('Not found') ? '#f87171'
                : status.includes('✓') || status.includes('Detected') ? '#34d399'
                  : '#d1d5db',
            }}>
              {status}
            </div>
          )}

          {/* Cross-clip expression after successful new tracking */}
          {trackingId && (
            <div style={{ padding: '4px 10px 6px' }}>
              <div style={{ fontSize: '9px', color: '#6366f1', fontWeight: 600, marginBottom: 2 }}>
                CROSS-CLIP EXPRESSION (paste into another clip's property):
              </div>
              <div style={{ fontFamily: 'monospace', fontSize: '9px', color: '#818cf8', background: '#0f172a', borderRadius: 3, padding: '4px 6px', wordBreak: 'break-all' }}>
                {crossClipExpr(trackingId, sourceClipId)}
              </div>
              <button
                onClick={() => copyToClipboard(crossClipExpr(trackingId, sourceClipId))}
                style={{ ...sBtn(false), flex: 'none', marginTop: 4, fontSize: '9px', padding: '2px 8px' }}
              >
                Copy expression
              </button>
              <div style={{ fontSize: '9px', color: '#4b5563', marginTop: 3 }}>
                Select a Shape/Text clip → Inspector → right-click Position → Enter expression → paste above
              </div>
            </div>
          )}

        </div>
      )}
    </div>
  );
}
