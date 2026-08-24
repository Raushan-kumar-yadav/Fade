import React, { useState } from "react";
import './createProjectModal.css'

interface CreateProjectModalProps {
    onClose: () => void;
    onProjectCreated: () => void;
}

const SEP = navigator.platform.startsWith('Win') ? '\\' : '/';

export default function CreateProjectModal({ onClose, onProjectCreated }: CreateProjectModalProps) {
    const [name, setName] = useState("Untitled Project");
    const [width, setWidth] = useState(1920);
    const [height, setHeight] = useState(1080);
    const [fps, setFps] = useState(30.0);
    const [totalFrame, setTotalFrame] = useState(1800);
    const [projectFolder, setProjectFolder] = useState('');
    const [folderError, setFolderError] = useState('');
    const [loading, setLoading] = useState(false);

     
    const safeFileName = (n: string) => n.replace(/[<>:"/\\|?*]/g, '_').trim() || 'Untitled Project';

     const previewPath = projectFolder
        ? `${projectFolder}${SEP}${safeFileName(name)}.fade`
        : '';

    const pickFolder = async () => {
        const el = (window as any).electronAPI;
        const fp: string | undefined = await el?.showOpenDialog({
            title: 'Select Project Folder',
            properties: ['openDirectory', 'createDirectory'],
        });
        if (fp) {
            setProjectFolder(fp);
            setFolderError('');
        }
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();

        if (!projectFolder.trim()) {
            setFolderError('Please select a project folder.');
            return;
        }

        setLoading(true);
        const port = (window as any).__FADE_PORT__ ?? 8000;
        const base = `http://127.0.0.1:${port}`;

         const mediaDownloadPath = `${projectFolder}${SEP}media`;
        const fadePath = previewPath;

        try {
             const params = new URLSearchParams({
                name,
                width: width.toString(),
                height: height.toString(),
                fps: fps.toString(),
                mediaDownloadPath,
            });
            const newRes = await fetch(`${base}/project/new?${params}`, { method: 'POST' });
            if (!newRes.ok) {
                console.error('[Project] Create failed', await newRes.text());
                return;
            }

             const saveRes = await fetch(`${base}/project/save`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ filepath: fadePath }),
            });
            if (!saveRes.ok) {
                console.error('[Project] Save failed', await saveRes.text());
             }

            onProjectCreated();
        } catch (err) {
            console.error('[Project] Error', err);
        } finally {
            setLoading(false);
        }
    };

    const PRESETS = [
        { label: '1080p 30fps', w: 1920, h: 1080, f: 30 },
        { label: '1080p 60fps', w: 1920, h: 1080, f: 60 },
        { label: '4K 30fps', w: 3840, h: 2160, f: 30 },
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

                    {/* Project Folder */}
                    <div className="sp-section">
                        <p className="sp-section-title">Project Location</p>

                        {/* Folder picker row */}
                        <div className="sp-row">
                            <label className="sp-label">Folder</label>
                            <div
                                className={`sp-folder-display${!projectFolder ? ' sp-folder-display--empty' : ''}`}
                                title={projectFolder || 'No folder selected'}
                            >
                                {projectFolder || 'No folder selected — click Browse'}
                            </div>
                            <button
                                type="button"
                                className="sp-btn sp-btn--browse"
                                onClick={pickFolder}
                            >
                                Browse…
                            </button>
                        </div>

                        {folderError && (
                            <div className="sp-folder-error">{folderError}</div>
                        )}

                        {/* Preview of where .fade will be saved */}
                        {previewPath && (
                            <div className="sp-folder-preview">
                                <span className="sp-folder-preview__label">Project file:</span>
                                <span className="sp-folder-preview__path" title={previewPath}>
                                    {safeFileName(name)}.fade
                                </span>
                            </div>
                        )}
                        {previewPath && (
                            <div className="sp-folder-preview">
                                <span className="sp-folder-preview__label">Media folder:</span>
                                <span className="sp-folder-preview__path">
                                    media{SEP}
                                </span>
                            </div>
                        )}
                    </div>

                    {/* Project Name */}
                    <div className="sp-section">
                        <p className="sp-section-title">Project</p>
                        <div className="sp-row">
                            <label className="sp-label">Name</label>
                            <input
                                className="sp-input"
                                style={{ flex: 1 }}
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
                            <input className="sp-input" type="number" value={width}
                                onChange={e => setWidth(Number(e.target.value))} min={1} />
                            <span className="sp-value">px</span>
                        </div>
                        <div className="sp-row">
                            <label className="sp-label">Height</label>
                            <input className="sp-input" type="number" value={height}
                                onChange={e => setHeight(Number(e.target.value))} min={1} />
                            <span className="sp-value">px</span>
                        </div>
                        <div className="sp-row">
                            <label className="sp-label">Frame Rate</label>
                            <input className="sp-input" type="number" step="0.01" value={fps}
                                onChange={e => setFps(Number(e.target.value))} min={1} />
                            <span className="sp-value">fps</span>
                        </div>
                        <div className="sp-row">
                            <label className="sp-label">Duration</label>
                            <input className="sp-input" type="number" value={totalFrame}
                                onChange={e => setTotalFrame(Number(e.target.value))} min={1} />
                            <span className="sp-value">frames ({(totalFrame / fps).toFixed(1)}s)</span>
                        </div>
                    </div>

                    {/* Footer */}
                    <div className="sp-footer">
                        {loading && <span className="sp-saving">Creating…</span>}
                        <button type="button" className="sp-btn" onClick={onClose}>
                            Cancel
                        </button>
                        <button
                            type="submit"
                            className="sp-btn sp-btn--close"
                            disabled={loading || !projectFolder}
                            title={!projectFolder ? 'Select a project folder first' : ''}
                        >
                            Create Project
                        </button>
                    </div>

                </form>
            </div>
        </div>
    );
}
