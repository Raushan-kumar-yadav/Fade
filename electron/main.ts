import { app, BrowserWindow, ipcMain, dialog } from 'electron'
import { spawn, ChildProcess } from 'child_process'
import path from 'path'
import fs from 'fs'
import {
  createWebComp, captureFrame, prefetchFrames,
  updateParams, reloadWebComp, destroyWebComp, destroyAll,
  getActiveInstances
} from './webComp/webCompRenderer'

const isDev = process.env.NODE_ENV === 'development'
let mainWindow:   BrowserWindow | null = null
let splashWindow: BrowserWindow | null = null
let devLogWindow: BrowserWindow | null = null
let pyProcess: ChildProcess  | null = null
let detectedPort:  number | null = null    
let appQuitting  = false
let pyKilledByUs = false
let mainReady    = false    
let backendReady = false   
 
function getResourcesRoot(): string {
  return app.isPackaged
    ? process.resourcesPath
    : path.join(__dirname, '..')
}

// Splash helpers  
type SplashCls = 'ok' | 'warn' | 'err' | undefined

function sendSplash(text: string, progress?: number, cls?: SplashCls, done = false) {
  console.log('[Splash]', text)
  if (splashWindow && !splashWindow.isDestroyed()) {
    splashWindow.webContents.send('splash:status', { text, progress, cls, done })
  }
}

function closeSplashAndShowMain() {
  if (!mainWindow || mainWindow.isDestroyed()) return
  
  setTimeout(() => {
    if (splashWindow && !splashWindow.isDestroyed()) {
      splashWindow.close()
      splashWindow = null
    }
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.show()
      mainWindow.focus()
    }
  }, 700)
}

function tryRevealMain() {
  if (mainReady && backendReady) {
    sendSplash('Launching editor…', 98, 'ok', true)
    closeSplashAndShowMain()
  }
}

// Dev log window — available in ALL builds for debugging
function createDevLogWindow(): void {
  if (devLogWindow && !devLogWindow.isDestroyed()) {
    devLogWindow.focus()
    return
  }
  devLogWindow = new BrowserWindow({
    width: 720,
    height: 700,
    title: 'Fade — Backend Logs',
    frame: false,
    backgroundColor: '#0d0d0f',
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js'),
    },
  })
  const logPath = app.isPackaged
    ? path.join(process.resourcesPath, 'app', 'dist-electron', 'devlog.html')
    : path.join(__dirname, 'devlog.html')
  devLogWindow.loadFile(logPath)
  devLogWindow.on('closed', () => { devLogWindow = null })
  devLogWindow.once('ready-to-show', () => devLogWindow?.show())
}

function sendDevLog(type: 'py' | 'sys', text: string) {
  if (!devLogWindow || devLogWindow.isDestroyed()) return
  devLogWindow.webContents.send('devlog', { type, text })
}

function sendDevStatus(text: string, alive: boolean) {
  if (!devLogWindow || devLogWindow.isDestroyed()) return
  devLogWindow.webContents.send('devlog', { type: 'status', text, alive })
}

 // Loaded lazily  
type RenderEngine = {
  initialize(w: number, h: number, fps: number, effectsDir?: string, port?: number): void
  seekFrame(n: number): void
  play(): void
  pause(): void
  isPlaying(): boolean
  getSharedBuffer(): ArrayBuffer
  setFrameReadyCallback(fn: (frameNum: number) => void): void
  getStats(): { width: number; height: number; fps: number; bufferSize: number }
  setPreviewScale(scale: number): number
  //   Export  
  startExport(config: {
    outputPath: string; width: number; height: number;
    fps: number; totalFrames: number; codec?: string; videoBitrate?: string;
  }, progressCb: (p: { frame: number; total: number; done: boolean; error: string }) => void): void
  cancelExport(): void
}

let renderEngine: RenderEngine | null = null

 
let currentPreviewScale = 0.5  

 
const viewportFrameReadyCb = (frameNum: number) => {
  mainWindow?.webContents.send('render:frame-ready', frameNum)
}

 
 
let _detectedCodec: string | null = null
function detectH264Codec(ffmpegExe: string): string {
  if (_detectedCodec) return _detectedCodec
  const { execFileSync } = require('child_process') as typeof import('child_process')
  const preference = ['h264_nvenc', 'h264_amf', 'h264_mf', 'libopenh264', 'libx264']
  try {
    const out = execFileSync(ffmpegExe, ['-encoders'], { timeout: 5000 }).toString()
    for (const codec of preference) {
      if (out.includes(codec)) {
        console.log('[RenderEngine] Selected H.264 encoder:', codec)
        _detectedCodec = codec
        return codec
      }
    }
  } catch (e) {
    console.warn('[RenderEngine] Could not probe encoders:', e)
  }
 
  _detectedCodec = 'h264_mf'
  return _detectedCodec
}

function loadRenderEngine(): void {
  const resRoot     = getResourcesRoot()
  const addonPath   = path.join(resRoot, 'renderer', 'build', 'Release', 'render_engine.node')
  const releaseBinDir = path.join(resRoot, 'renderer', 'build', 'Release')

  if (!fs.existsSync(addonPath)) {
    console.log('[RenderEngine] Native addon not found at', addonPath, '— using Python compositor fallback')
    return
  }

 
  const currentPath = process.env.PATH ?? ''
  if (!currentPath.includes(releaseBinDir)) {
    process.env.PATH = releaseBinDir + path.delimiter + currentPath
    console.log('[RenderEngine] Prepended FFmpeg dir to PATH:', releaseBinDir)
  }

 
  detectH264Codec(path.join(releaseBinDir, 'ffmpeg.exe'))

  try {
    
    renderEngine = require(addonPath) as RenderEngine
    console.log('[RenderEngine] Native addon loaded successfully')
  } catch (e) {
    console.error('[RenderEngine] Failed to load native addon:', e)
    renderEngine = null
  }
}

function initRenderEngine(pythonPort: number, width = 1920, height = 1080, fps = 30): void {
  if (!renderEngine) return
  const pw = Math.round(width * currentPreviewScale)
  const ph = Math.round(height * currentPreviewScale)
  console.log(`[RenderEngine] Init at preview res: ${pw}x${ph} (full: ${width}x${height}, scale: ${currentPreviewScale})`)
  const effectsDir = path.join(getResourcesRoot(), 'backend', 'timeline', 'effects', 'sksl').replace(/\\/g, '/')
  try {
    renderEngine.initialize(pw, ph, fps, effectsDir, pythonPort)
    renderEngine.setFrameReadyCallback(viewportFrameReadyCb)
    console.log('[RenderEngine] Initialized — effectsDir:', effectsDir, 'port:', pythonPort)
  } catch (e) {
    console.error('[RenderEngine] Initialize error:', e)
    renderEngine = null
  }
}

 
function initRenderEngineFullRes(pythonPort: number, width = 1920, height = 1080, fps = 30): void {
  if (!renderEngine) return
  const effectsDir = path.join(getResourcesRoot(), 'backend', 'timeline', 'effects', 'sksl').replace(/\\/g, '/')
  try {
    renderEngine.initialize(width, height, fps, effectsDir, pythonPort)
    renderEngine.setFrameReadyCallback(viewportFrameReadyCb)
    console.log(`[RenderEngine] Full-res init: ${width}x${height} for export`)
  } catch (e) {
    console.error('[RenderEngine] Full-res init error:', e)
  }
}


 
app.commandLine.appendSwitch('disable-gpu-shader-disk-cache')
app.commandLine.appendSwitch('disable-dev-shm-usage')
app.commandLine.appendSwitch('no-sandbox')
app.commandLine.appendSwitch('disable-gpu-sandbox')
app.commandLine.appendSwitch('disable-software-rasterizer')
app.commandLine.appendSwitch('ignore-gpu-blocklist')
app.commandLine.appendSwitch('enable-gpu-rasterization')
app.commandLine.appendSwitch('disable-zero-copy')
app.commandLine.appendSwitch('autoplay-policy', 'no-user-gesture-required')

// Helpers  

function sendPort(port: number) {
  detectedPort = port
  backendReady = true
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send('backend:port', port)
  }
 
  sendSplash('Loading render engine…', 80)
  initRenderEngine(port)
  sendSplash('Render engine ready', 88, 'ok')
  tryRevealMain()
}

// Python backend
function startPython(): void {
  const resRoot = getResourcesRoot()
  let pythonExe: string
  let pythonArgs: string[]
  let pythonCwd: string

  if (app.isPackaged) {
    // Packaged: PyInstaller bundle is in resources/backend/
    pythonExe  = path.join(resRoot, 'backend', 'backend.exe')
    pythonArgs = []
    pythonCwd  = path.join(resRoot, 'backend')
  } else {
    // Dev: use .venv
    const venvPython = path.join(resRoot, '.venv', 'Scripts', 'python.exe')
    pythonExe  = fs.existsSync(venvPython) ? venvPython : 'python'
    pythonArgs = ['-m', 'backend.main']
    pythonCwd  = resRoot
  }

  pyProcess = spawn(pythonExe, pythonArgs, {
    cwd:   pythonCwd,
    stdio: 'pipe',
    env: {
      ...process.env,
      PYTHONPATH: resRoot + (process.env.PYTHONPATH ? ';' + process.env.PYTHONPATH : ''),
      OPENBLAS_NUM_THREADS: '1',
      OMP_NUM_THREADS: '1',
      MKL_NUM_THREADS: '1',
      FADE_RESOURCES_PATH: resRoot,
    },
  })

  pyProcess.stdout?.on('data', (d: Buffer) => {
    const line = d.toString().trim()
    console.log('[PY]', line)
    sendDevLog('py', line)
    const m = line.match(/starting on port (\d+)/)
    if (m) {
      sendSplash('Backend ready on port ' + m[1], 70, 'ok')
      sendDevStatus('Python: ready on port ' + m[1], true)
      sendPort(parseInt(m[1], 10))
    } else if (line.length > 0 && line.length < 120) {
       
      sendSplash(line, undefined, undefined)
    }
  })

  pyProcess.stderr?.on('data', (d: Buffer) => {
    const msg = d.toString().trim()
    if (!msg.includes('Watching for file changes') && !msg.includes('WARNING')) {
      console.error('[PY ERR]', msg)
      sendDevLog('py', msg)
      // Only surface real errors to splash
      if (msg.includes('Error') || msg.includes('error')) {
        sendSplash(msg.slice(0, 100), undefined, 'err')
      }
    }
  })

  pyProcess.on('close', (code: number | null) => {
    const wasIntentional = pyKilledByUs || appQuitting
    console.log('[PY] exited — code:', code, '| intentional:', wasIntentional)
    sendDevLog('sys', `Python exited (code ${code}) | intentional: ${wasIntentional}`)
    sendDevStatus(`Python: exited (code ${code})`, false)
    pyKilledByUs  = false
    detectedPort  = null    
    if (!wasIntentional && code !== 0) {
      console.log('[PY] crashed — restarting in 2 s…')
      setTimeout(startPython, 2000)
    }
  })

  console.log('[PY] started — pid:', pyProcess.pid, '| python:', pythonExe)
}

// ── Graceful shutdown ──────────────────────────────────────────────────────────
// Kills the FULL process tree (backend.exe + all multiprocessing worker children).
// On Windows a plain .kill() only signals the top-level process; child workers
// created via multiprocessing.Process survive as orphans.
function killPythonTree(): void {
  const { execSync } = require('child_process') as typeof import('child_process')
  const pid = pyProcess?.pid

  if (process.platform === 'win32') {
    // 1. Kill the tracked process tree by PID (covers current session)
    if (pid) {
      console.log(`[Cleanup] taskkill /F /T /PID ${pid}`)
      try { execSync(`taskkill /F /T /PID ${pid}`, { stdio: 'ignore', timeout: 5000 }) } catch { /* already dead */ }
    }
    // 2. Sweep ALL backend.exe processes by name — catches any orphans from
    //    crashed restarts or processes whose PID we lost track of.
    try { execSync('taskkill /F /IM backend.exe /T', { stdio: 'ignore', timeout: 5000 }) } catch { /* none running */ }
  } else {
    // Unix: kill entire process group
    if (pid) {
      try { process.kill(-pid, 'SIGKILL') } catch { /* ignore */ }
    }
  }

  pyProcess = null
}

function doCleanup(): void {
  if (appQuitting) return   // idempotent — only run once
  appQuitting  = true
  pyKilledByUs = true
  console.log('[Cleanup] Starting graceful shutdown…')

  // Pause render engine first so no more callbacks fire
  try { renderEngine?.pause() } catch { /* ignore */ }

  // Destroy all WebComp renderer windows
  try { destroyAll() } catch { /* ignore */ }

  // Close auxiliary windows so window-all-closed fires reliably
  try { if (devLogWindow  && !devLogWindow.isDestroyed())  { devLogWindow.close();  devLogWindow  = null } } catch { /* ignore */ }
  try { if (splashWindow  && !splashWindow.isDestroyed())  { splashWindow.close();  splashWindow  = null } } catch { /* ignore */ }

  // Kill the full Python process tree
  killPythonTree()
  console.log('[Cleanup] Done')
}

//   Splash window  
function createSplash(): void {
  splashWindow = new BrowserWindow({
    width: 460,
    height: 380,
    frame: false,
    transparent: true,
    resizable: false,
    center: true,
    alwaysOnTop: true,
    skipTaskbar: true,
    backgroundColor: '#00000000',
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js'),
    },
  })
  const splashPath = app.isPackaged
    ? path.join(process.resourcesPath, 'app', 'dist-electron', 'splash.html')
    : path.join(__dirname, 'splash.html')
  splashWindow.loadFile(splashPath)
  splashWindow.once('ready-to-show', () => splashWindow?.show())
}

//   Main window  
function createWindow(): void {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1100,
    minHeight: 700,
    frame: false,
    show: false,   
    backgroundColor: '#0d0d0f',
    webPreferences: {
      preload:          path.join(__dirname, 'preload.js'),
      nodeIntegration:  false,
      contextIsolation: true,
    },
  })

  if (isDev) {
    mainWindow.loadURL('http://localhost:5173')
    mainWindow.webContents.openDevTools({ mode: 'detach' })
  } else {
    mainWindow.loadFile(path.join(__dirname, '../dist/index.html'))
  }

  mainWindow.on('close', () => {
    doCleanup()
  })

  mainWindow.webContents.on('did-finish-load', () => {
    mainReady = true
    sendSplash('UI loaded', 90, 'ok')
    if (detectedPort !== null) {
      mainWindow?.webContents.send('backend:port', detectedPort)
      console.log('[Electron] (re-)sent backend:port', detectedPort, 'after did-finish-load')
    }
    tryRevealMain()
  })

   
  setTimeout(() => {
    if (splashWindow && !splashWindow.isDestroyed()) {
      sendSplash('Timeout — showing app anyway', undefined, 'warn')
      mainReady = true
      backendReady = true
      tryRevealMain()
    }
  }, 30_000)
}

// IPC  

ipcMain.on('window:minimize', () => mainWindow?.minimize())
ipcMain.on('window:maximize', () => {
  mainWindow?.isMaximized() ? mainWindow.unmaximize() : mainWindow?.maximize()
})
ipcMain.on('window:close', () => mainWindow?.close())
ipcMain.on('devlog:toggle', () => {
  if (devLogWindow && !devLogWindow.isDestroyed()) {
    devLogWindow.close()
  } else {
    createDevLogWindow()
  }
})

ipcMain.handle('backend:get-port', () => detectedPort)

//   Native render engine IPC  
ipcMain.on('render:seek', (_, frame: number) => renderEngine?.seekFrame(frame))
ipcMain.on('render:play',  () => renderEngine?.play())
ipcMain.on('render:pause', () => renderEngine?.pause())
ipcMain.handle('render:get-buffer', () => renderEngine?.getSharedBuffer() ?? null)
ipcMain.handle('render:get-stats',  () => renderEngine?.getStats() ?? null)
ipcMain.handle('render:is-native',  () => renderEngine !== null)
 
ipcMain.on('render:set-preview-scale', (_, scale: number) => {
  if (renderEngine) {
    currentPreviewScale = renderEngine.setPreviewScale(scale)
  }
})

//   Export IPC  
ipcMain.on('export:start', async (_event, config) => {
  if (!renderEngine) {
    // Native engine not available  
    mainWindow?.webContents.send('export:progress', {
      frame: 0, total: 0, done: true,
      error: 'Native render engine not loaded — use Python export fallback'
    })
    return
  }

   
  let totalFrames: number = config.totalFrames ?? 0
  if (!totalFrames && detectedPort) {
    try {
      const { default: http } = await import('http')
      const data: string = await new Promise((resolve, reject) => {
        http.get(`http://127.0.0.1:${detectedPort}/playback/state`, res => {
          let body = ''
          res.on('data', (c: Buffer) => { body += c.toString() })
          res.on('end', () => resolve(body))
        }).on('error', reject)
      })
      const state = JSON.parse(data)
      totalFrames = state.totalFrames ?? 1800
    } catch {
      totalFrames = 1800
    }
  }
 
  const exportConfig = { ...config, totalFrames }
  console.log('[Export] Starting JS buffer-hijack export:', exportConfig.outputPath, `(${totalFrames} frames)`)

  // Ensure output directory exists
  try { fs.mkdirSync(path.dirname(exportConfig.outputPath), { recursive: true }) } catch { /**/ }

   
  renderEngine.pause()

   
  if (detectedPort) {
    console.log('[Export] Re-initializing compositor at full 1920x1080 for export')
    initRenderEngineFullRes(detectedPort, 1920, 1080, 30)
  }

 
  const prevScale = currentPreviewScale  // save BEFORE setting
  currentPreviewScale = renderEngine.setPreviewScale(1.0)   
  console.log('[Export] Forced preview scale 1.0 (was', prevScale, ')')
  
  const pyScaleReset = detectedPort
    ? new Promise<void>(resolve => {
        const httpMod = require('http') as typeof import('http')
        const body = JSON.stringify({ scale: 1.0 })
        const req = httpMod.request(
          { hostname: '127.0.0.1', port: detectedPort, path: '/preview/scale',
            method: 'POST', headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(body) } },
          () => resolve()
        )
        req.on('error', () => resolve()) // non-fatal
        req.write(body)
        req.end()
      })
    : Promise.resolve()
  await pyScaleReset


   
  interface WcExportClip {
    webcompId: string; startFrame: number; endFrame: number;
    mediaOffset: number; width: number; height: number;
  }
  const wcExportClips: WcExportClip[] = []

  if (detectedPort) {
    try {
      const { default: httpWC } = await import('http')

       
      const httpGet = (url: string): Promise<string> => new Promise(resolve => {
        httpWC.get(url, res => {
          let body = ''
          res.on('data', (c: Buffer) => { body += c.toString() })
          res.on('end', () => resolve(body))
        }).on('error', (e) => {
          console.warn('[Export] HTTP GET failed:', url, e.message)
          resolve('{}')
        })
      })

       
      const clipData = await httpGet(`http://127.0.0.1:${detectedPort}/export/webcomp-clips`)
      const { clips } = JSON.parse(clipData) as { clips: Array<{
        webcompId: string; clipId: string;
        startFrame: number; endFrame: number; mediaOffset: number
      }> }

      console.log(`[Export] Phase 0: found ${clips.length} WebComp clip(s)`)

      if (clips.length > 0) {
         
        const assetListData = await httpGet(`http://127.0.0.1:${detectedPort}/timeline/webcomp/list`)
        const assetList = (JSON.parse(assetListData)?.webcomps ?? []) as Array<{
          assetId: string; folderPath: string;
          width?: number; height?: number; fps?: number
        }>
        const assetMap = new Map(assetList.map(a => [a.assetId, a]))

         
        for (const clip of clips) {
          const asset = assetMap.get(clip.webcompId)
          wcExportClips.push({
            webcompId:   clip.webcompId,
            startFrame:  clip.startFrame,
            endFrame:    clip.endFrame,
            mediaOffset: clip.mediaOffset,
            width:  asset?.width  ?? config.width  ?? 1920,
            height: asset?.height ?? config.height ?? 1080,
          })
        }

        const uniqueIds = [...new Set(clips.map(c => c.webcompId))]
        for (const wcId of uniqueIds) {
          const existing = getActiveInstances().find(i => i.webcompId === wcId)
          if (existing) {
            console.log(`[Export] BrowserWindow already exists for ${wcId.slice(-8)}`)
            continue
          }
          const asset = assetMap.get(wcId)
          if (!asset?.folderPath) {
            console.warn(`[Export] No asset metadata for webcompId=${wcId} — skipping`)
            continue
          }
          const htmlUrl = 'file:///' + asset.folderPath.replace(/\\/g, '/') + '/index.html'
          const w = asset.width  ?? config.width  ?? 1920
          const h = asset.height ?? config.height ?? 1080
          const fps = asset.fps ?? (config as any).fps ?? 30
          console.log(`[Export] Creating BrowserWindow for ${wcId.slice(-8)} (${w}x${h}@${fps})`)
          try {
            await createWebComp(wcId, htmlUrl, w, h, fps)
            console.log(`[Export] BrowserWindow ready for ${wcId.slice(-8)}`)
          } catch (ce) {
            console.warn(`[Export] createWebComp failed for ${wcId}:`, ce)
          }
        }

        // 4. Capture and push every frame
        const totalWebCompFrames = clips.reduce((s, c) => s + (c.endFrame - c.startFrame), 0)
        mainWindow?.webContents.send('export:webcomp-phase', {
          active: true, done: 0, total: totalWebCompFrames
        })

        let doneFrames = 0
        for (const clip of clips) {
          for (let f = clip.startFrame; f < clip.endFrame; f++) {
            const localFrame = Math.max(0, (f - clip.startFrame) + clip.mediaOffset)
            const rgba = await captureFrame(clip.webcompId, localFrame)
            if (rgba && renderEngine) {
              try {
                ;(renderEngine as any).pushWebCompFrame(
                  clip.webcompId, localFrame, rgba,    
                  config.width ?? 1920, config.height ?? 1080
                )
              } catch (e) {
                console.warn(`[Export] pushWebCompFrame f=${f}:`, e)
              }
            } else if (!rgba) {
              console.warn(`[Export] captureFrame returned null for ${clip.webcompId.slice(-8)} localFrame=${localFrame}`)
            }
            doneFrames++
            if (doneFrames % 5 === 0 || doneFrames === totalWebCompFrames) {
              mainWindow?.webContents.send('export:webcomp-phase', {
                active: true, done: doneFrames, total: totalWebCompFrames
              })
            }
          }
        }
        mainWindow?.webContents.send('export:webcomp-phase', {
          active: false, done: doneFrames, total: totalWebCompFrames
        })
        console.log(`[Export] Pre-rendered ${doneFrames} WebComp frames into full-res engine`)
      } else {
        console.log('[Export] No WebComp clips in project')
      }
    } catch (err) {
      console.warn('[Export] WebComp pre-render error:', err)
    }
  }

  
  const releaseBinDir2 = path.join(getResourcesRoot(), 'renderer', 'build', 'Release')
  const ffmpegExe = path.join(releaseBinDir2, 'ffmpeg.exe')
  const rawCodec = exportConfig.codec ?? 'h264_mf'
  const exportCodec = (rawCodec === 'auto' || rawCodec === '' || rawCodec === 'default') ? 'h264_mf' : rawCodec
  const exportBr = (exportConfig as any).videoBitrate ?? '8M'
  // Audio mux settings 
  const exportAudioBr = (exportConfig as any).audioBitrate    ?? '192k'
  const exportAudioSR  = (exportConfig as any).audioSampleRate ?? 48000
  const exportAudioCh  = (exportConfig as any).audioChannels   ?? 2

  const httpModule = require('http') as typeof import('http')
  const portSnapshot = detectedPort

  // Cancellation flag  
  let exportCancelled = false
  const cancelListener = () => { exportCancelled = true }
  ipcMain.once('export:cancel', cancelListener)

   
  ;(async () => {
    const { spawn: spawnProc } = require('child_process') as typeof import('child_process')
    const { width, height, fps } = exportConfig

    console.log(`[Export] Codec: ${exportCodec}  Bitrate: ${exportBr}  Size: ${width}x${height}  FPS: ${fps}`)

 
    const ffArgs = [
      '-y',
      '-f', 'rawvideo', '-vcodec', 'rawvideo', '-pix_fmt', 'rgba',
      '-s', `${width}x${height}`, '-r', String(fps),
      '-i', 'pipe:0',
      '-c:v', exportCodec,
      '-pix_fmt', 'yuv420p',
      '-b:v', exportBr,
      exportConfig.outputPath
    ]
    console.log('[Export] FFmpeg cmd:', ffmpegExe, ffArgs.join(' '))

    const ffProc = spawnProc(ffmpegExe, ffArgs, { stdio: ['pipe', 'ignore', 'pipe'] })

     
    let ffStderr = ''
    ffProc.stderr?.on('data', (d: Buffer) => {
      const line = d.toString()
      ffStderr += line
       
      if (line.includes('Error') || line.includes('error') || line.includes('Invalid')) {
        console.warn('[Export][FFmpeg]', line.trim())
      }
    })

 
    let ffExited = false
    let ffExitCode = -1
    const ffmpegExitCode = new Promise<number>(resolve => ffProc.on('close', code => {
      ffExited = true
      ffExitCode = code ?? -1
      resolve(ffExitCode)
       
      const r = _frameResolve
      _frameResolve = null
      r?.()
    }))

    const frameByteSize = width * height * 4

     
    let _frameResolve: (() => void) | null = null
    renderEngine.setFrameReadyCallback((_frameNum: number) => {
      const r = _frameResolve
      _frameResolve = null
      r?.()
    })

    let exportError = ''

    try {
      for (let f = 0; f < totalFrames; f++) {
        if (exportCancelled) { exportError = 'Cancelled'; break }
        if (ffExited) { exportError = `FFmpeg exited early (code ${ffExitCode}): ${ffStderr.slice(-400)}`; break }

         
        for (const wcc of wcExportClips) {
          if (f >= wcc.startFrame && f < wcc.endFrame) {
            const localFrame = Math.max(0, (f - wcc.startFrame) + wcc.mediaOffset)
            const rgba = await captureFrame(wcc.webcompId, localFrame) 
            if (rgba && renderEngine) {
              try {
                ;(renderEngine as any).pushWebCompFrame(
                  wcc.webcompId, localFrame, rgba, wcc.width, wcc.height
                )
              } catch { }
            }
          }
        }

        await new Promise<void>(resolve => {
          _frameResolve = resolve
          renderEngine!.seekFrame(f)
        })

        if (exportCancelled) { exportError = 'Cancelled'; break }

         
        const rawBuf = renderEngine.getSharedBuffer()
         
        const frameBytes = Buffer.from(rawBuf, 0, Math.min(frameByteSize, rawBuf.byteLength))

         
        const ok = ffProc.stdin!.write(frameBytes)
        if (!ok) {
          await new Promise<void>(r => ffProc.stdin!.once('drain', r))
        }

         
        if (f % 10 === 0 || f === totalFrames - 1) {
          mainWindow?.webContents.send('export:progress', {
            frame: f + 1, total: totalFrames, done: false, error: ''
          })
        }
      }
    } catch (err) {
      exportError = String(err)
      console.error('[Export] Frame loop error:', err)
    } finally {
       
      renderEngine.setFrameReadyCallback(viewportFrameReadyCb)
      ipcMain.removeListener('export:cancel', cancelListener)

       
      if (prevScale !== 1.0) {
        currentPreviewScale = renderEngine.setPreviewScale(prevScale)
        console.log('[Export] Restored preview scale to', prevScale)
         
        if (portSnapshot) {
          initRenderEngine(portSnapshot, 1920, 1080, 30)
          const httpMod2 = require('http') as typeof import('http')
          const body2 = JSON.stringify({ scale: prevScale })
          const req2 = httpMod2.request(
            { hostname: '127.0.0.1', port: portSnapshot, path: '/preview/scale',
              method: 'POST', headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(body2) } },
            () => {}
          )
          req2.on('error', () => {})
          req2.write(body2)
          req2.end()
        }
      }

       
      const liveWebComps = getActiveInstances()
      if (liveWebComps.length > 0) {
        console.log(`[Export] Re-seeding ${liveWebComps.length} WebComp(s) to viewport`)
        for (const { webcompId, width, height } of liveWebComps) {
          captureFrame(webcompId, 0).then(rgba => {
            if (rgba && renderEngine) {
              try {
                ;(renderEngine as any).pushWebCompFrame(webcompId, 0, rgba, width, height)
                console.log(`[Export] Re-seeded WebComp ${webcompId} frame 0`)
              } catch { /* non-fatal */ }
            }
          }).catch(() => { /* non-fatal */ })
        }
      }
    }

    // Close FFmpeg stdin  
    ffProc.stdin!.end()
    const exitCode = await ffmpegExitCode

    if (exitCode !== 0 && !exportError) {
      exportError = `FFmpeg exited ${exitCode}: ${ffStderr.slice(-600)}`
      console.error('[Export] FFmpeg failed:', exportError)
    }

     
    if (exitCode === 0 && !exportError && !exportCancelled && portSnapshot) {
      console.log('[Export] Starting audio mux pass...')
      mainWindow?.webContents.send('export:progress', {
        frame: totalFrames, total: totalFrames, done: false,
        error: '', status: 'audio'
      })

      try {
        // Fetch audio clips
        const audioResp = await new Promise<any>((resolve, reject) => {
          const httpMod3 = require('http') as typeof import('http')
          let data = ''
          const req = httpMod3.request(
            { hostname: '127.0.0.1', port: portSnapshot, path: '/timeline/audio-clips', method: 'GET' },
            res => { res.on('data', c => { data += c }); res.on('end', () => { try { resolve(JSON.parse(data)) } catch { resolve(null) } }) }
          )
          req.on('error', reject)
          req.end()
        })

        const clips: any[] = audioResp?.clips ?? []
        const clipFps: number = audioResp?.fps ?? fps

        if (clips.length > 0) {
           
          const { execFileSync: execSync } = require('child_process') as typeof import('child_process')
          const tmpVideoPath = exportConfig.outputPath.replace(/\.mp4$/i, '_video_only.mp4')
          fs.renameSync(exportConfig.outputPath, tmpVideoPath)

           
          const audioArgs: string[] = ['-y', '-i', tmpVideoPath]

          // De-duplicate same file paths  
          const fileToIdx = new Map<string, number>()
          let inputIdx = 1
          for (const clip of clips) {
            const fp = clip.filePath
            if (fp && !fileToIdx.has(fp)) {
              audioArgs.push('-i', fp)
              fileToIdx.set(fp, inputIdx++)
            }
          }

          // Build filter_complex
          const filterParts: string[] = []
          const mixLabels: string[] = []
          clips.forEach((clip, i) => {
            const fp = clip.filePath
            if (!fp || !fileToIdx.has(fp)) return
            const idx = fileToIdx.get(fp)!
            const startSec = (clip.startFrame / clipFps).toFixed(6)
            const offsetSec = ((clip.mediaOffset ?? 0) / clipFps).toFixed(6)
            const durationSec = (clip.duration / clipFps).toFixed(6)
            const vol = (clip.volume ?? 1.0).toFixed(4)
            const label = `a${i}`
             filterParts.push(
              `[${idx}:a]atrim=start=${offsetSec}:duration=${durationSec},adelay=${Math.round(parseFloat(startSec) * 1000)}|${Math.round(parseFloat(startSec) * 1000)},volume=${vol}[${label}]`
            )
            mixLabels.push(`[${label}]`)
          })

          if (filterParts.length > 0) {
            const filterComplex = [
              ...filterParts,
              `${mixLabels.join('')}amix=inputs=${mixLabels.length}:duration=longest:normalize=0[aout]`
            ].join('; ')

            const muxArgs = [
              ...audioArgs,
              '-filter_complex', filterComplex,
              '-map', '0:v',
              '-map', '[aout]',
              '-c:v', 'copy',       
              '-c:a', 'aac',
              '-b:a', exportAudioBr,
              '-ar', String(exportAudioSR),
              '-ac', String(exportAudioCh),
              '-shortest',
              exportConfig.outputPath
            ]

            console.log('[Export][Audio] FFmpeg mux cmd:', ffmpegExe, muxArgs.slice(0, 8).join(' '), '...')

            const { spawn: spawnMux } = require('child_process') as typeof import('child_process')
            const muxProc = spawnMux(ffmpegExe, muxArgs, { stdio: ['ignore', 'ignore', 'pipe'] })
            let muxStderr = ''
            muxProc.stderr?.on('data', (d: Buffer) => { muxStderr += d.toString() })
            const muxExit = await new Promise<number>(r => muxProc.on('close', r))

            if (muxExit === 0) {
              console.log('[Export][Audio] Mux complete:', exportConfig.outputPath)
               
              try { fs.unlinkSync(tmpVideoPath) } catch { /**/ }
            } else {
              exportError = `Audio mux failed (${muxExit}): ${muxStderr.slice(-400)}`
              console.error('[Export][Audio] Mux failed:', exportError)
               
              try { if (!fs.existsSync(exportConfig.outputPath)) fs.renameSync(tmpVideoPath, exportConfig.outputPath) } catch { /**/ }
            }
          } else {
             
            fs.renameSync(tmpVideoPath, exportConfig.outputPath)
            console.log('[Export][Audio] No audio clips to mux, video-only kept')
          }
        } else {
          console.log('[Export] No audio clips in project, video-only export')
        }
      } catch (audioErr) {
        console.warn('[Export][Audio] Audio mux error (non-fatal):', audioErr)
         
      }
    } else if (exitCode === 0 && !exportError) {
      console.log('[Export] Done (video only — no port for audio fetch):', exportConfig.outputPath)
    }

    // Report final done event
    mainWindow?.webContents.send('export:progress', {
      frame: exportCancelled ? 0 : totalFrames,
      total: totalFrames,
      done: true,
      error: exportError
    })

     
    if (portSnapshot) {
      httpModule.request(
        { hostname: '127.0.0.1', port: portSnapshot, path: '/export/webcomp-cache', method: 'DELETE' },
        () => {}
      ).on('error', () => {}).end()
    }
  })().catch(err => {
    console.error('[Export] Unexpected export error:', err)
    mainWindow?.webContents.send('export:progress', {
      frame: 0, total: totalFrames, done: true,
      error: String(err)
    })
  })
})

 
ipcMain.on('export:cancel', () => {
  renderEngine?.cancelExport()  
  console.log('[Export] Cancel requested')
})

//   WebComp IPC  
ipcMain.handle('webcomp:create', async (_, opts: {
  webcompId: string; htmlUrl: string;
  width: number; height: number; fps: number;
}) => {
  // Await page load  
  await createWebComp(opts.webcompId, opts.htmlUrl, opts.width, opts.height, opts.fps)
  // Warm-cache frame 0  
  const frame0 = await captureFrame(opts.webcompId, 0)
  if (frame0 && renderEngine) {
    try { (renderEngine as any).pushWebCompFrame(opts.webcompId, 0, frame0, opts.width, opts.height) }
    catch {  }
  }
  return true
})

ipcMain.handle('webcomp:capture-frame', async (_, webcompId: string, frame: number) => {
  const rgba = await captureFrame(webcompId, frame)
  return rgba
})

ipcMain.handle('webcomp:prefetch', async (_, webcompId: string, startFrame: number, count: number) => {
  await prefetchFrames(webcompId, startFrame, count)
  return true
})

ipcMain.on('webcomp:update-params', (_, webcompId: string, params: any) => {
  updateParams(webcompId, params)
})

ipcMain.on('webcomp:reload', (_, webcompId: string) => {
  reloadWebComp(webcompId)
})

ipcMain.on('webcomp:destroy', (_, webcompId: string) => {
  destroyWebComp(webcompId)
})


 
ipcMain.handle('webcomp:push-to-native', async (
  _, webcompId: string, localFrame: number, width: number, height: number,
  _timelineFrame?: number   
) => {
  const rgba = await captureFrame(webcompId, localFrame)
  if (rgba && renderEngine) {
    try {
      (renderEngine as any).pushWebCompFrame(webcompId, localFrame, rgba, width, height)
      return true
    } catch (e) {
      console.error('[WebComp] pushWebCompFrame failed:', e)
    }
  }
  return false
})

 
ipcMain.handle('app:get-path', (_event, name: string) => {
  try {
    return app.getPath(name as any)
  } catch {
    return null
  }
})

//   File dialogs  
ipcMain.handle('dialog:save', async (_event, opts) => {
  if (!mainWindow) return undefined
  const result = await dialog.showSaveDialog(mainWindow, {
    filters: opts?.filters ?? [{ name: 'Video', extensions: ['mp4'] }],
    defaultPath: opts?.defaultPath,
  })
  return result.canceled ? undefined : result.filePath
})

ipcMain.handle('dialog:open', async (_event, opts) => {
  if (!mainWindow) return undefined
  const result = await dialog.showOpenDialog(mainWindow, {
    title: opts?.title,
    properties: opts?.properties ?? ['openFile'],
    filters: opts?.filters ?? (opts?.properties?.includes('openDirectory') ? [] : [{ name: 'Fade Project', extensions: ['fade'] }]),
    defaultPath: opts?.defaultPath,
  })
  return result.canceled ? undefined : result.filePaths[0]
})

 

app.whenReady().then(() => {
  createSplash()
  sendSplash('Initializing render engine…', 10)
  loadRenderEngine()

  sendSplash('Creating main window…', 20)
  createWindow()

  // Dev log — auto-show in dev, available via Ctrl+Shift+L in production
  createDevLogWindow()
  if (isDev) {
    sendDevLog('sys', 'Fade dev mode started')
    sendDevLog('sys', 'Waiting for Python backend…')
  } else {
    sendDevLog('sys', 'Fade production build started')
    sendDevLog('sys', 'Press Ctrl+Shift+L to toggle this log window')
  }

  sendSplash('Starting Python backend…', 30)
  startPython()
})

app.on('window-all-closed', () => {
  doCleanup()
  app.quit()
})

app.on('before-quit', () => {
  doCleanup()
})
