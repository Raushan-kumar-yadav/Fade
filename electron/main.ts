import { app, BrowserWindow, ipcMain, dialog } from 'electron'
import { spawn, ChildProcess } from 'child_process'
import path from 'path'
import fs from 'fs'

const isDev = process.env.NODE_ENV === 'development'
let mainWindow: BrowserWindow | null = null
let pyProcess: ChildProcess  | null = null
let detectedPort:  number | null = null    
let appQuitting  = false
let pyKilledByUs = false

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
  //   Export  
  startExport(config: {
    outputPath: string; width: number; height: number;
    fps: number; totalFrames: number; codec?: string; videoBitrate?: string;
  }, progressCb: (p: { frame: number; total: number; done: boolean; error: string }) => void): void
  cancelExport(): void
}

let renderEngine: RenderEngine | null = null

function loadRenderEngine(): void {
  const addonPath = path.join(__dirname, '..', 'renderer', 'build', 'Release', 'render_engine.node')
  if (!fs.existsSync(addonPath)) {
    console.log('[RenderEngine] Native addon not found at', addonPath, '— using Python compositor fallback')
    return
  }
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    renderEngine = require(addonPath) as RenderEngine
    console.log('[RenderEngine] Native addon loaded successfully')
  } catch (e) {
    console.error('[RenderEngine] Failed to load native addon:', e)
    renderEngine = null
  }
}

function initRenderEngine(pythonPort: number, width = 1920, height = 1080, fps = 30): void {
  if (!renderEngine) return

  // SkSL shaders live at:  <projectRoot>/backend/timeline/effects/sksl/
  const projectRoot = path.join(__dirname, '..')
  const effectsDir  = path.join(projectRoot, 'backend', 'timeline', 'effects', 'sksl')
                          .replace(/\\/g, '/')  // C++ std::ifstream prefers forward slashes

  try {
    renderEngine.initialize(width, height, fps, effectsDir, pythonPort)
    renderEngine.setFrameReadyCallback((frameNum: number) => {
      mainWindow?.webContents.send('render:frame-ready', frameNum)
    })
    console.log('[RenderEngine] Initialized — effectsDir:', effectsDir, 'port:', pythonPort)
  } catch (e) {
    console.error('[RenderEngine] Initialize error:', e)
    renderEngine = null
  }
}


 
app.commandLine.appendSwitch('disable-gpu-shader-disk-cache')
app.commandLine.appendSwitch('disable-dev-shm-usage')
app.commandLine.appendSwitch('no-sandbox')
app.commandLine.appendSwitch('disable-gpu-sandbox')
app.commandLine.appendSwitch('disable-software-rasterizer')   // use ANGLE instead of SW
app.commandLine.appendSwitch('ignore-gpu-blocklist')           // don't block GPU on driver issues
app.commandLine.appendSwitch('enable-gpu-rasterization')       // keep GPU for Chromium UI
app.commandLine.appendSwitch('disable-zero-copy')              // prevent zero-copy GPU mem pressure

// Helpers  

function sendPort(port: number) {
  detectedPort = port
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send('backend:port', port)
  }
  // Initialize native render engine once Python is ready
  initRenderEngine(port)
}

// Python backend  
function startPython(): void {
  const projectRoot = path.join(__dirname, '..')
  const venvPython  = path.join(projectRoot, '.venv', 'Scripts', 'python.exe')
  const fs = require('fs')
  const pythonExe = fs.existsSync(venvPython) ? venvPython : 'python'

  pyProcess = spawn(pythonExe, ['-m', 'backend.main'], {
    cwd:   projectRoot,
    stdio: 'pipe',
    env: {
      ...process.env,
      PYTHONPATH: projectRoot + (process.env.PYTHONPATH ? ';' + process.env.PYTHONPATH : ''),
      OPENBLAS_NUM_THREADS: '1',
      OMP_NUM_THREADS: '1',
      MKL_NUM_THREADS: '1',
    },
  })

  pyProcess.stdout?.on('data', (d: Buffer) => {
    const line = d.toString().trim()
    console.log('[PY]', line)
    const m = line.match(/starting on port (\d+)/)
    if (m) sendPort(parseInt(m[1], 10))
  })

  pyProcess.stderr?.on('data', (d: Buffer) => {
    const msg = d.toString().trim()
    if (!msg.includes('Watching for file changes') && !msg.includes('WARNING')) {
      console.error('[PY ERR]', msg)
    }
  })

  pyProcess.on('close', (code: number | null) => {
    const wasIntentional = pyKilledByUs || appQuitting
    console.log('[PY] exited — code:', code, '| intentional:', wasIntentional)
    pyKilledByUs  = false
    detectedPort  = null    
    if (!wasIntentional && code !== 0) {
      console.log('[PY] crashed — restarting in 2 s…')
      setTimeout(startPython, 2000)
    }
  })

  console.log('[PY] started — pid:', pyProcess.pid, '| python:', pythonExe)
}

// Window  

function createWindow(): void {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1100,
    minHeight: 700,
    frame: false,
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

 
  mainWindow.webContents.on('did-finish-load', () => {
    if (detectedPort !== null) {
      mainWindow?.webContents.send('backend:port', detectedPort)
      console.log('[Electron] (re-)sent backend:port', detectedPort, 'after did-finish-load')
    }
  })
}

// IPC  

ipcMain.on('window:minimize', () => mainWindow?.minimize())
ipcMain.on('window:maximize', () => {
  mainWindow?.isMaximized() ? mainWindow.unmaximize() : mainWindow?.maximize()
})
ipcMain.on('window:close', () => mainWindow?.close())

ipcMain.handle('backend:get-port', () => detectedPort)

//   Native render engine IPC  
ipcMain.on('render:seek', (_, frame: number) => renderEngine?.seekFrame(frame))
ipcMain.on('render:play',  () => renderEngine?.play())
ipcMain.on('render:pause', () => renderEngine?.pause())
ipcMain.handle('render:get-buffer', () => renderEngine?.getSharedBuffer() ?? null)
ipcMain.handle('render:get-stats',  () => renderEngine?.getStats() ?? null)
ipcMain.handle('render:is-native',  () => renderEngine !== null)

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

  // Resolve totalFrames from Python 
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
  console.log('[Export] Starting GPU export:', exportConfig.outputPath, `(${totalFrames} frames)`)

  // Pause play-loop  
  renderEngine.pause()

  renderEngine.startExport(
    exportConfig,
    (progress: { frame: number; total: number; done: boolean; error: string }) => {
      mainWindow?.webContents.send('export:progress', progress)
      if (progress.done) {
        console.log('[Export] Done:', progress.error || exportConfig.outputPath)
      }
    }
  )
})

ipcMain.on('export:cancel', () => {
  renderEngine?.cancelExport()
  console.log('[Export] Cancelled')
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

// Lifecycle  

app.whenReady().then(() => {
  loadRenderEngine()   // try to load native addon  
  createWindow()
  startPython()
})

app.on('window-all-closed', () => {
  appQuitting  = true
  pyKilledByUs = true
  pyProcess?.kill()
  app.quit()
})

app.on('before-quit', () => {
  appQuitting  = true
  pyKilledByUs = true
  pyProcess?.kill()
})
