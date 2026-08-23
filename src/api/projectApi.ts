/**
 * projectApi.ts
 * Save / Load / New project helpers.
 * File-dialog calls go through Electron IPC; data calls hit the Python backend.
 */

function base(): string {
  const port = (window as any).__FADE_PORT__ ?? 8000
  return `http://127.0.0.1:${port}`
}

export interface ProjectMeta {
  projectId: string
  name: string
  width: number
  height: number
  fps: number
  totalFrame: number
  filePath?: string
}

// ── Save (opens dialog first) ─────────────────────────────────────────────────

export async function saveProject(defaultName = 'My Project'): Promise<string | null> {
  const el = (window as any).electronAPI
  const filepath: string | undefined = await el?.showSaveDialog({
    filters: [{ name: 'Fade Project', extensions: ['fade'] }],
    defaultPath: defaultName,
  })
  if (!filepath) return null

  const r = await fetch(`${base()}/project/save`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ filepath }),
  })
  if (!r.ok) { console.error('[Project] Save failed', await r.text()); return null }
  const res = await r.json()
  console.log('[Project] Saved →', res.filepath)
  return res.filepath as string
}

// ── Save to a known path (Ctrl+S after first save) ────────────────────────────

export async function saveProjectTo(filepath: string): Promise<boolean> {
  const r = await fetch(`${base()}/project/save`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ filepath }),
  })
  return r.ok
}

// ── Load (opens dialog first) ─────────────────────────────────────────────────

export interface LoadResult {
  project: ProjectMeta
  timeline: object
}

export async function loadProject(): Promise<LoadResult | null> {
  const el = (window as any).electronAPI
  const filepath: string | undefined = await el?.showOpenDialog({
    filters: [{ name: 'Fade Project', extensions: ['fade'] }],
  })
  if (!filepath) return null

  const r = await fetch(`${base()}/project/load`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ filepath }),
  })
  if (!r.ok) { console.error('[Project] Load failed', await r.text()); return null }
  return r.json() as Promise<LoadResult>
}

// ── New ───────────────────────────────────────────────────────────────────────

export async function newProject(
  opts: { name?: string; width?: number; height?: number; fps?: number } = {}
): Promise<ProjectMeta | null> {
  const params = new URLSearchParams({
    name:   opts.name   ?? 'Untitled Project',
    width:  String(opts.width  ?? 1920),
    height: String(opts.height ?? 1080),
    fps:    String(opts.fps    ?? 30),
  })
  const r = await fetch(`${base()}/project/new?${params}`, { method: 'POST' })
  if (!r.ok) return null
  const res = await r.json()
  return res.project as ProjectMeta
}
