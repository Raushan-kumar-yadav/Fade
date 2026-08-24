import React, { useState } from "react";
import './createProjectModal.css'

interface CreateProjectModalProps {
    onClose: () => void;
    onProjectCreated: () => void;
}

export default function CreateProjectModal({ onClose, onProjectCreated }: CreateProjectModalProps) {
    const [name, setName] = useState("Untitled Project");
    const [width, setWidth] = useState(1920);
    const [height, setHeight] = useState(1080);
    const [fps, setFps] = useState(30.0);
    const [totalFrame, setTotalFrame] = useState(1800);
    const [mediaPath, setMedia] = useState('');
    const [loading, setLoading] = useState(false);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setLoading(true);
        try {
            // Backend reads query params, not JSON body
            const params = new URLSearchParams({
                name,
                width: width.toString(),
                height: height.toString(),
                fps: fps.toString(),
                mediaDownloadPath: mediaPath
            });
            const res = await fetch(`http://127.0.0.1:8000/project/new?${params.toString()}`, {
                method: 'POST',
            });
            if (res.ok) {
                onProjectCreated();
                onClose();
            } else {
                console.error('Failed to create project');
            }
        } catch (err) {
            console.error(err);
        } finally {
            setLoading(false);
        }
    };

    const PRESETS = [
        { label: '1080p 30fps', w: 1920, h: 1080, f: 30 },
        { label: '1080p 60fps', w: 1920, h: 1080, f: 60 },
        { label: '4K 30fps',    w: 3840, h: 2160, f: 30 },
        { label: '720p 30fps',  w: 1280, h:  720, f: 30 },
    ];

    return (
        <div className="sp-overlay" onClick={onClose}>
            <div className="sp-panel" onClick={e => e.stopPropagation()}>

                {/* Header */}
                <div className="sp-header">
                    <h2 className="sp-title">New Project</h2>
                    <button className="sp-close" onClick={onClose}>✕</button>
                </div>

                <form onSubmit={handleSubmit}>

                    {/* Project Name */}
                    <div className="sp-section">
                        <p className="sp-section-title">Project</p>
                        <div className="sp-row">
                            <label className="sp-label">Name</label>
                            <input
                                className="sp-input"
                                style={{ width: '100%' }}
                                type="text"
                                value={name}
                                onChange={e => setName(e.target.value)}
                                placeholder="Untitled Project"
                            />
                        </div>
                    </div>

                    {/* Presets */}
                    <div className="sp-section">
                        <p className="sp-section-title">Preset</p>
                        <div className="sp-row">
                            <label className="sp-label">Quick Preset</label>
                            <select
                                className="sp-select"
                                onChange={e => {
                                    const p = PRESETS[+e.target.value];
                                    if (p) { setWidth(p.w); setHeight(p.h); setFps(p.f); }
                                }}
                                defaultValue=""
                            >
                                <option value="" disabled>Select preset…</option>
                                {PRESETS.map((p, i) => (
                                    <option key={i} value={i}>{p.label}</option>
                                ))}
                            </select>
                        </div>
                    </div>

                    {/* Resolution & FPS */}
                    <div className="sp-section">
                        <p className="sp-section-title">Resolution & Frame Rate</p>
                        <div className="sp-row">
                            <label className="sp-label">Width</label>
                            <input
                                className="sp-input"
                                type="number"
                                value={width}
                                onChange={e => setWidth(Number(e.target.value))}
                                min={1}
                            />
                            <span className="sp-value">px</span>
                        </div>
                        <div className="sp-row">
                            <label className="sp-label">Height</label>
                            <input
                                className="sp-input"
                                type="number"
                                value={height}
                                onChange={e => setHeight(Number(e.target.value))}
                                min={1}
                            />
                            <span className="sp-value">px</span>
                        </div>
                        <div className="sp-row">
                            <label className="sp-label">Frame Rate</label>
                            <input
                                className="sp-input"
                                type="number"
                                step="0.01"
                                value={fps}
                                onChange={e => setFps(Number(e.target.value))}
                                min={1}
                            />
                            <span className="sp-value">fps</span>
                        </div>
                        <div className="sp-row">
                            <label className="sp-label">Duration</label>
                            <input
                                className="sp-input"
                                type="number"
                                value={totalFrame}
                                onChange={e => setTotalFrame(Number(e.target.value))}
                                min={1}
                            />
                            <span className="sp-value">frames ({(totalFrame / fps).toFixed(1)}s)</span>
                        </div>
                    </div>

                    {/* AI Downloads Path */}
                    <div className="sp-section">
                        <p className="sp-section-title">AI Agent</p>
                        <div className="sp-row">
                            <label className="sp-label">Downloads Path</label>
                            <input
                                className="sp-input"
                                style={{ width: '100%' }}
                                type="text"
                                value={mediaPath}
                                onChange={e => setMedia(e.target.value)}
                                placeholder="C:\Users\…\Downloads (optional)"
                            />
                        </div>
                    </div>

                    {/* Footer */}
                    <div className="sp-footer">
                        {loading && <span className="sp-saving">Creating…</span>}
                        <button type="button" className="sp-btn" onClick={onClose}>
                            Cancel
                        </button>
                        <button type="submit" className="sp-btn sp-btn--close" disabled={loading}>
                            Create Project
                        </button>
                    </div>

                </form>
            </div>
        </div>
    );
}
