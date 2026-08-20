import { app, BrowserWindow, ipcMain } from 'electron'
import { spawn, ChildProcess } from 'child_process'
import path from 'path'

const isDev = process.env.NODE_ENV === 'development'
let mainWindow: BrowserWindow | null = null
let pyProcess: ChildProcess  | null = null
let detectedPort:  number | null = null    
let appQuitting  = false
let pyKilledByUs = false   

// Suppress harmless 
app.commandLine.appendSwitch('disable-gpu-shader-disk-cache')
app.commandLine.appendSwitch('disable-dev-shm-usage')
app.commandLine.appendSwitch('no-sandbox')

// Helpers  

function sendPort(port: number) {
  detectedPort = port
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send('backend:port', port)
  }
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

// Lifecycle  

app.whenReady().then(() => {
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
