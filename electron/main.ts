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
  setPreviewScale(scale: number): number
  //   Export  
  startExport(config: {
    outputPath: string; width: number; height: number;
    fps: number; totalFrames: number; codec?: string; videoBitrate?: string;
  }, progressCb: (p: { frame: number; total: number; done: boolean; error: string }) => void): void
  cancelExport(): void
}

let renderEngine: RenderEngine | null = null

// ── JS-side mirror of g_previewScale ───────────────────────────────────────
// The C++ setPreviewScale returns the NEW value (after clamping), not the old
// one. So we track it here in JS, defaulting to 0.5 (C++ default) and updating
// it on every call through main.ts. The export loop reads this to know what
// scale to restore after export finishes.
let currentPreviewScale = 0.5 // mirrors g_previewScale in RenderEngineAddon.cpp

// ── Viewport frame-ready callback ───────────────────────────────────────
// Stored so the export loop's finally block can restore it after hijacking it
// to drive frame-by-frame rendering. Without this the viewport goes dark after
// export and the user has to restart.
const viewportFrameReadyCb = (frameNum: number) => {
  mainWindow?.webContents.send('render:frame-ready', frameNum)
}

// ── Detect best H.264 encoder available in the bundled FFmpeg ────────────────
// The bundled build has --disable-libx264, so we must pick an alternative.
// Priority: h264_nvenc (NVIDIA) → h264_amf (AMD) → h264_mf (Win MediaFoundation)
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
  // Absolute fallback: h264_mf is always present on Win10+
  _detectedCodec = 'h264_mf'
  return _detectedCodec
}

function loadRenderEngine(): void {
  const addonPath = path.join(__dirname, '..', 'renderer', 'build', 'Release', 'render_engine.node')
  if (!fs.existsSync(addonPath)) {
    console.log('[RenderEngine] Native addon not found at', addonPath, '— using Python compositor fallback')
    return
  }

  // ── Ensure bundled FFmpeg is on PATH so the C++ addon's _popen("ffmpeg ...") works
  // Electron's process inherits a stripped PATH that often excludes user-installed tools.
  // The C++ encoder calls _popen("ffmpeg -y ... pipe:0 output.mp4", "wb") — if `ffmpeg`
  // isn't found, cmd.exe starts fine (so _popen returns non-NULL) but exits immediately,
  // all fwrite() calls go to a dead pipe, and the file is never created.
  const releaseBinDir = path.join(__dirname, '..', 'renderer', 'build', 'Release')
  const currentPath = process.env.PATH ?? ''
  if (!currentPath.includes(releaseBinDir)) {
    process.env.PATH = releaseBinDir + path.delimiter + currentPath
    console.log('[RenderEngine] Prepended FFmpeg dir to PATH:', releaseBinDir)
  }

  // Probe available encoders now so it's ready before the first export
  detectH264Codec(path.join(releaseBinDir, 'ffmpeg.exe'))

  try {
    // eslint-disable-next-line  
    renderEngine = require(addonPath) as RenderEngine
    console.log('[RenderEngine] Native addon loaded successfully')
  } catch (e) {
    console.error('[RenderEngine] Failed to load native addon:', e)
    renderEngine = null
  }
}

function initRenderEngine(pythonPort: number, width = 1920, height = 1080, fps = 30): void {
  if (!renderEngine) return

  // SkSL shaders live at 
  const projectRoot = path.join(__dirname, '..')
  const effectsDir  = path.join(projectRoot, 'backend', 'timeline', 'effects', 'sksl')
                          .replace(/\\/g, '/')   

  try {
    renderEngine.initialize(width, height, fps, effectsDir, pythonPort)
    renderEngine.setFrameReadyCallback(viewportFrameReadyCb)
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
app.commandLine.appendSwitch('disable-software-rasterizer')
app.commandLine.appendSwitch('ignore-gpu-blocklist')
app.commandLine.appendSwitch('enable-gpu-rasterization')
app.commandLine.appendSwitch('disable-zero-copy')
app.commandLine.appendSwitch('autoplay-policy', 'no-user-gesture-required')

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

  mainWindow.on('close', () => {
     
    try { renderEngine?.pause() } catch (_) {}
  })

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
// Keep JS scale tracker in sync when the renderer process sets preview scale
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
  console.log('[Export] Starting JS buffer-hijack export:', exportConfig.outputPath, `(${totalFrames} frames)`)

  // Ensure output directory exists
  try { fs.mkdirSync(path.dirname(exportConfig.outputPath), { recursive: true }) } catch { /**/ }

   
  renderEngine.pause()

 
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
                  clip.webcompId, f, rgba,
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

  
  const releaseBinDir2 = path.join(__dirname, '..', 'renderer', 'build', 'Release')
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

  // Run the async export loop without blocking the IPC thread
  ;(async () => {
    const { spawn: spawnProc } = require('child_process') as typeof import('child_process')
    const { width, height, fps } = exportConfig

    console.log(`[Export] Codec: ${exportCodec}  Bitrate: ${exportBr}  Size: ${width}x${height}  FPS: ${fps}`)

    // Spawn FFmpeg reading rawvideo RGBA from stdin
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

    // Accumulate stderr so we can report on failure
    let ffStderr = ''
    ffProc.stderr?.on('data', (d: Buffer) => {
      const line = d.toString()
      ffStderr += line
      // Surface codec-level errors immediately
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

         
        await new Promise<void>(resolve => {
          _frameResolve = resolve
          renderEngine!.seekFrame(f)
        })

        if (exportCancelled) { exportError = 'Cancelled'; break }

         
        const rawBuf = renderEngine.getSharedBuffer()
        // The buffer may be preview-scaled; slice to exact frame size
        const frameBytes = Buffer.from(rawBuf, 0, Math.min(frameByteSize, rawBuf.byteLength))

        // Write to FFmpeg stdin; respect backpressure
        const ok = ffProc.stdin!.write(frameBytes)
        if (!ok) {
          await new Promise<void>(r => ffProc.stdin!.once('drain', r))
        }

        // Report progress every 10 frames or on the last frame
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
              '-c:v', 'copy',      // video already encoded, just copy
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
              // Remove temp video-only file
              try { fs.unlinkSync(tmpVideoPath) } catch { /**/ }
            } else {
              exportError = `Audio mux failed (${muxExit}): ${muxStderr.slice(-400)}`
              console.error('[Export][Audio] Mux failed:', exportError)
              // Restore video-only so user isn't left with nothing
              try { if (!fs.existsSync(exportConfig.outputPath)) fs.renameSync(tmpVideoPath, exportConfig.outputPath) } catch { /**/ }
            }
          } else {
            // No valid audio clips after filtering; restore video-only
            fs.renameSync(tmpVideoPath, exportConfig.outputPath)
            console.log('[Export][Audio] No audio clips to mux, video-only kept')
          }
        } else {
          console.log('[Export] No audio clips in project, video-only export')
        }
      } catch (audioErr) {
        console.warn('[Export][Audio] Audio mux error (non-fatal):', audioErr)
        // Audio mux failing is non-fatal; user gets video-only
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

    // Clean up Python-side WebComp frame cache
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


// ─── WebComp push-to-native ───────────────────────────────────────────────────
// IMPORTANT: the C++ compositor looks up WebComp frames via:
//   tryGetCachedFrame(clip.file, clip.sourceFrame)
// where clip.sourceFrame = (timelineFrame - clip.startFrame) + mediaOffset = localFrame.
// Therefore we MUST cache by localFrame, NOT by timelineFrame.
// Passing timelineFrame here was the original cache-key mismatch bug.
ipcMain.handle('webcomp:push-to-native', async (
  _, webcompId: string, localFrame: number, width: number, height: number,
  _timelineFrame?: number   // kept in IPC signature for compat; not used as cache key
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
  destroyAll()  // Clean up all WebComp offscreen windows
  pyProcess?.kill()
})
