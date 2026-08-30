 
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

// Save  

export async function saveProject(defaultName = 'My Project'): Promise<string | null> {
  const el = (window as any).electronAPI

  // Try Electron folder picker first
  const folderPath: string | undefined = await el?.showOpenDialog({
    title: 'Save Project To Folder',
    properties: ['openDirectory', 'createDirectory'],
    buttonLabel: 'Save Here',
  })
  if (!folderPath) return null

  const r = await fetch(`${base()}/project/save`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ folderPath }),
  })
  if (!r.ok) { console.error('[Project] Save failed', await r.text()); return null }
  const res = await r.json()
  console.log('[Project] Saved →', res.filepath,
    `| clips:${res.clips} media:${res.mediaAssets} webcomps:${res.webcomps} chroma:${res.chromaDbChunks}`)
  return res.filepath as string
}

// Save to a known folder  

export async function saveProjectTo(filepath: string): Promise<boolean> {
  // filepath may be the anchor .fade file  
  const folderPath = filepath.endsWith('project.fade')
    ? filepath.replace(/[\\/]project\.fade$/, '')
    : filepath

  const r = await fetch(`${base()}/project/save`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ folderPath }),
  })
  if (!r.ok) { console.error('[Project] Save failed', await r.text()); return false }
  const res = await r.json()
  console.log('[Project] Saved →', res.filepath,
    `| clips:${res.clips} media:${res.mediaAssets} webcomps:${res.webcomps} chroma:${res.chromaDbChunks}`)
  return true
}

// Load  

export interface LoadResult {
  project: ProjectMeta
  timeline: object
  missing_assets?: Array<{ assetId: string; filename_hint: string }>
  clips?: number
  effects?: number
  chromaDbBundled?: boolean
}

export async function loadProject(): Promise<LoadResult | null> {
  const el = (window as any).electronAPI

  // Try folder picker first; fall back to .fade file picker
  let filepath: string | undefined = await el?.showOpenDialog({
    title: 'Open Project',
    properties: ['openDirectory'],
    buttonLabel: 'Open Project',
  })

  // If the user picked nothing or the dialog doesn't support folders, try .fade
  if (!filepath) {
    filepath = await el?.showOpenDialog({
      filters: [{ name: 'Fade Project', extensions: ['fade'] }],
    })
  }
  if (!filepath) return null

  const r = await fetch(`${base()}/project/load`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ filepath }),
  })
  if (!r.ok) { console.error('[Project] Load failed', await r.text()); return null }
  const res = await r.json() as LoadResult
  console.log('[Project] Loaded ←', filepath,
    `| clips:${res.clips} effects:${res.effects} chroma:${res.chromaDbBundled ? 'bundled' : 'global'}`)
  return res
}

// New  

export async function newProject(
  opts: { name?: string; width?: number; height?: number; fps?: number } = {}
): Promise<ProjectMeta | null> {
  const params = new URLSearchParams({
    name: opts.name   ?? 'Untitled Project',
    width: String(opts.width  ?? 1920),
    height: String(opts.height ?? 1080),
    fps: String(opts.fps    ?? 30),
  })
  const r = await fetch(`${base()}/project/new?${params}`, { method: 'POST' })
  if (!r.ok) return null
  const res = await r.json()
  return res.project as ProjectMeta
}
