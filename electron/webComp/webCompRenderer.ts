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
  // Serializes concurrent captures: only one executeJavaScript+capturePage
  // runs at a time per instance, preventing FADE_FRAME races.
  captureQueue: Promise<Buffer | null>
}

const instances = new Map<string, WebCompInstance>()
const MAX_CACHE_FRAMES = 360  // ~12 s at 30fps; JS-side LRU before C++ cache fills

export async function createWebComp(
  webcompId: string, htmlUrl: string,
  width: number, height: number, fps: number
): Promise<void> {
  if (instances.has(webcompId)) destroyWebComp(webcompId)

  const win = new BrowserWindow({
    width,
    height,
    show: false,
    frame: false,                       
    transparent: true,                  
    backgroundColor: '#00000000', 
    paintWhenInitiallyHidden: true,
    webPreferences: {
      offscreen: true,
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,                   
      backgroundThrottling: false,     
    },
  })

  // Inject transparent CSS before page loads
  win.webContents.on('dom-ready', () => {
    win.webContents.insertCSS(
      'html, body { background: transparent !important; margin: 0; padding: 0; overflow: hidden; }'
    ).catch(() => {})
  })

  win.webContents.setFrameRate(Math.min(fps, 60))

  const readyPromise = new Promise<void>(resolve => {
    win.webContents.once('did-finish-load', () => resolve())
    win.webContents.once('did-fail-load', (_ev: any, code: number, desc: string) => {
      console.error(`[WebComp] did-fail-load ${webcompId}: ${code} ${desc}`)
      resolve()   
    })
    // Timeout safety 
    setTimeout(() => {
      console.warn(`[WebComp] readyPromise timeout for ${webcompId}`)
      resolve()
    }, 10_000)
  })
  win.loadURL(htmlUrl)

  const inst: WebCompInstance = {
    win, htmlUrl, width, height, fps,
    frameCache: new Map(),
    ready: false,
    readyPromise,
    captureQueue: Promise.resolve(null),  // serial capture chain
  }
  instances.set(webcompId, inst)
  console.log(`[WebComp] Created ${webcompId} (${width}x${height}@${fps}fps)`)

  // Wait for page to finish loading so the first capture attempt always succeeds
  await readyPromise
  inst.ready = true
  console.log(`[WebComp] Ready ${webcompId}`)
}

export async function captureFrame(
  webcompId: string, frame: number
): Promise<Buffer | null> {
  const inst = instances.get(webcompId)
  if (!inst) return null
  if (inst.win.isDestroyed()) return null

  // Wait for page to finish loading on first capture
  if (!inst.ready) await inst.readyPromise

  // JS-side LRU cache hit — no Chrome round-trip needed
  if (inst.frameCache.has(frame)) return inst.frameCache.get(frame)!

  // ── Serialize captures through a per-instance queue ─────────────────────
  // Only ONE executeJavaScript+capturePage sequence runs at a time.
  // Without this, concurrent callers can race on window.FADE_FRAME:
  //   caller A sets FADE_FRAME=5, caller B immediately sets FADE_FRAME=10,
  //   caller A's capturePage() gets frame 10 — silently wrong pixels.
  const doCapture = async (): Promise<Buffer | null> => {
    // Re-check cache inside the queue (another caller may have captured it)
    if (inst.frameCache.has(frame)) return inst.frameCache.get(frame)!
    if (inst.win.isDestroyed()) return null

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

  // Chain this capture AFTER any in-flight one; the queue itself never rejects.
  const result = inst.captureQueue.then(doCapture, doCapture)
  inst.captureQueue = result.then(() => null, () => null)  // advance queue silently
  return result
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
  /* Clear cached frames  */
  inst.frameCache.clear()
  inst.win.webContents.executeJavaScript(`
    window.FADE_PARAMS = ${JSON.stringify(params)};
    window.dispatchEvent(new CustomEvent('fade:params', {
      detail: ${JSON.stringify(params)}
    }));
  `).catch(() => {})
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

/**
 * Returns the IDs and dimensions of every WebComp instance that is still alive.
 * Used by the export cleanup path to re-seed frame 0 into the C++ compositor
 * after setPreviewScale re-initializes and wipes the WebComp frame buffer.
 */
export function getActiveInstances(): Array<{ webcompId: string; width: number; height: number }> {
  const result: Array<{ webcompId: string; width: number; height: number }> = []
  for (const [id, inst] of instances.entries()) {
    if (!inst.win.isDestroyed()) {
      result.push({ webcompId: id, width: inst.width, height: inst.height })
    }
  }
  return result
}
