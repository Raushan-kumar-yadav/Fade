import React, { useState, useEffect, useCallback, useRef } from 'react';
import { fetchAssets, importAsset, removeAsset, type AssetItem } from '../../api/useApi';
import './LibraryPanel.css';

const TYPE_ICON: Record<string, string> = {
  video:    '▶',
  image:    '🖼',
  audio:    '♪',
  subtitle: '✎',
  unknown:  '?',
};

const TYPE_COLOR: Record<string, string> = {
  video:   'var(--accent-blue)',
  image:   'var(--accent-green)',
  audio:   'var(--accent-purple)',
  unknown: 'var(--text-muted)',
};

interface Props {
  /** Called when the user double-clicks an asset — parent places it on the timeline */
  onAddToTimeline?: (asset: AssetItem, trackIndex?: number) => void;
}

export default function LibraryPanel({ onAddToTimeline }: Props) {
  const [assets,   setAssets]   = useState<AssetItem[]>([]);
  const [query,    setQuery]    = useState('');
  const [loading,  setLoading]  = useState(false);
  const [dragging, setDragging] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // ── Load assets from backend ──────────────────────────────────────────────
  const refresh = useCallback(async () => {
    setLoading(true);
    const data = await fetchAssets();
    setAssets(data);
    setLoading(false);
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  // ── Import via hidden file input ──────────────────────────────────────────
  const handleFileSelect = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files) return;
    setLoading(true);
    for (const file of Array.from(files)) {
      await importAsset(file.path ?? (file as any).webkitRelativePath ?? file.name);
    }
    await refresh();
    // Reset so the same file can be re-imported
    if (inputRef.current) inputRef.current.value = '';
  }, [refresh]);

  // ── Drop zone ─────────────────────────────────────────────────────────────
  const handleDrop = useCallback(async (e: React.DragEvent) => {
    e.preventDefault();
    setLoading(true);
    const paths: string[] = [];
    for (const item of Array.from(e.dataTransfer.items)) {
      const entry = item.webkitGetAsEntry?.();
      if (entry?.isFile) {
        await new Promise<void>(res => {
          (entry as any).file((f: File) => { paths.push((f as any).path ?? f.name); res(); });
        });
      }
    }
    for (const p of paths) await importAsset(p);
    await refresh();
  }, [refresh]);

  // ── Delete ────────────────────────────────────────────────────────────────
  const handleDelete = useCallback(async (assetId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    await removeAsset(assetId);
    setAssets(prev => prev.filter(a => a.assetId !== assetId));
  }, []);

  const filtered = assets.filter(a =>
    a.filename.toLowerCase().includes(query.toLowerCase())
  );

  return (
    <div
      className="lib"
      onDragOver={e => { e.preventDefault(); e.dataTransfer.dropEffect = 'copy'; }}
      onDrop={handleDrop}
    >
      {/* Search bar */}
      <div className="lib__search">
        <span className="lib__search-icon">⌕</span>
        <input
          className="lib__search-input"
          placeholder="Search assets…"
          value={query}
          onChange={e => setQuery(e.target.value)}
        />
        <button
          className="lib__import-btn"
          title="Import file"
          onClick={() => inputRef.current?.click()}
        >
          +
        </button>
        <input
          ref={inputRef}
          type="file"
          hidden
          multiple
          accept="video/*,image/*,audio/*"
          onChange={handleFileSelect}
        />
      </div>

      {/* Asset list */}
      <div className="lib__list">
        {loading && filtered.length === 0 && (
          <div className="lib__empty">
            <div className="lib__spinner" />
          </div>
        )}

        {!loading && filtered.length === 0 && (
          <div className="lib__empty">
            <div className="lib__empty-icon">📂</div>
            <p className="lib__empty-hint">Drop files here or click <strong>+</strong></p>
          </div>
        )}

        {filtered.map(asset => (
          <div
            key={asset.assetId}
            id={`lib-asset-${asset.assetId}`}
            className={`lib__item${dragging === asset.assetId ? ' lib__item--dragging' : ''}`}
            draggable
            onDragStart={e => {
              setDragging(asset.assetId);
              e.dataTransfer.setData('application/fade-asset', JSON.stringify(asset));
              e.dataTransfer.effectAllowed = 'copy';
            }}
            onDragEnd={() => setDragging(null)}
            onDoubleClick={() => onAddToTimeline?.(asset, 0)}
            title={asset.filepath}
          >
            <span
              className="lib__item-icon"
              style={{ color: TYPE_COLOR[asset.type] ?? TYPE_COLOR.unknown }}
            >
              {TYPE_ICON[asset.type] ?? '?'}
            </span>
            <span className="lib__item-name">{asset.filename}</span>
            <span className="lib__item-type">{asset.type}</span>
            <button
              className="lib__item-del"
              title="Remove from library"
              onClick={e => handleDelete(asset.assetId, e)}
            >
              ✕
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
