import { BrowserWindow } from 'electron'

interface WebCompInstance {
  win: BrowserWindow
  htmlUrl: string
  width: number
  height: number
  fps: number
  frameCache: Map<number, Buffer>
  ready: boolean
  readyPromise: Promise<void>
}

const instances = new Map<string, WebCompInstance>()
const MAX_CACHE_FRAMES = 60

export function createWebComp(
  webcompId: string, htmlUrl: string,
  width: number, height: number, fps: number
): void {
  if (instances.has(webcompId)) destroyWebComp(webcompId)

  const win = new BrowserWindow({
    width,
    height,
    show: false,
    paintWhenInitiallyHidden: true,
    webPreferences: {
      offscreen: true,              // Enable offscreen rendering
      nodeIntegration: false,       // Security: no Node.js access
      contextIsolation: true,
      sandbox: true,                // Maximum sandboxing
    },
  })

  win.webContents.setFrameRate(Math.min(fps, 60))

  const readyPromise = new Promise<void>(resolve => {
    win.webContents.once('did-finish-load', () => resolve())
  })
  win.loadURL(htmlUrl)

  const inst: WebCompInstance = {
    win, htmlUrl, width, height, fps,
    frameCache: new Map(),
    ready: false,
    readyPromise,
  }
  readyPromise.then(() => { inst.ready = true })
  instances.set(webcompId, inst)
  console.log(`[WebComp] Created ${webcompId} (${width}x${height}@${fps}fps)`)
}

export async function captureFrame(
  webcompId: string, frame: number
): Promise<Buffer | null> {
  const inst = instances.get(webcompId)
  if (!inst) return null
  if (inst.win.isDestroyed()) return null

  // Wait for page to finish loading on first capture
  if (!inst.ready) await inst.readyPromise

  // Cache hit
  if (inst.frameCache.has(frame)) return inst.frameCache.get(frame)!

  try {
    // Inject frame number into the page
    await inst.win.webContents.executeJavaScript(`
      window.FADE_FRAME = ${frame};
      window.FADE_TIME = ${frame / inst.fps};
      window.FADE_FPS = ${inst.fps};
      window.FADE_WIDTH = ${inst.width};
      window.FADE_HEIGHT = ${inst.height};
      window.dispatchEvent(new CustomEvent('fade:frame', {
        detail: { frame: ${frame}, time: ${frame / inst.fps} }
      }));
    `)

    // Wait for render (double rAF ensures paint is complete)
    await inst.win.webContents.executeJavaScript(
      `new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))`
    )

    // Capture BGRA bitmap from Chromium
    const nativeImage = await inst.win.webContents.capturePage()
    const size = nativeImage.getSize()
    const bgra = nativeImage.toBitmap()

    // Swizzle BGRA → RGBA (Chromium outputs BGRA, Skia expects RGBA)
    const rgba = Buffer.alloc(size.width * size.height * 4)
    for (let i = 0; i < size.width * size.height; i++) {
      const o = i * 4
      rgba[o + 0] = bgra[o + 2]  // R ← B
      rgba[o + 1] = bgra[o + 1]  // G ← G
      rgba[o + 2] = bgra[o + 0]  // B ← R
      rgba[o + 3] = bgra[o + 3]  // A ← A
    }

    // LRU cache — keep last MAX_CACHE_FRAMES frames
    inst.frameCache.set(frame, rgba)
    if (inst.frameCache.size > MAX_CACHE_FRAMES) {
      const oldest = inst.frameCache.keys().next().value
      if (oldest !== undefined) inst.frameCache.delete(oldest)
    }

    return rgba
  } catch (err) {
    console.error(`[WebComp] captureFrame error ${webcompId}:${frame}`, err)
    return null
  }
}

export async function prefetchFrames(
  webcompId: string, startFrame: number, count: number
): Promise<void> {
  for (let f = startFrame; f < startFrame + count; f++) {
    await captureFrame(webcompId, f)
  }
}

export function updateParams(
  webcompId: string, params: Record<string, any>
): void {
  const inst = instances.get(webcompId)
  if (!inst) return
  inst.win.webContents.executeJavaScript(`
    window.FADE_PARAMS = ${JSON.stringify(params)};
    window.dispatchEvent(new CustomEvent('fade:params', {
      detail: ${JSON.stringify(params)}
    }));
  `)
}

export function reloadWebComp(webcompId: string): void {
  const inst = instances.get(webcompId)
  if (!inst) return
  inst.frameCache.clear()
  inst.win.webContents.reload()
  console.log(`[WebComp] Reloaded ${webcompId}`)
}

export function destroyWebComp(webcompId: string): void {
  const inst = instances.get(webcompId)
  if (inst) {
    inst.win.destroy()
    inst.frameCache.clear()
    instances.delete(webcompId)
    console.log(`[WebComp] Destroyed ${webcompId}`)
  }
}

export function destroyAll(): void {
  for (const id of instances.keys()) destroyWebComp(id)
}
