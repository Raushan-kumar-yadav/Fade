import { app, BrowserWindow, ipcMain } from 'electron'
import { spawn, ChildProcess } from 'child_process'
import path from 'path'

const isDev = process.env.NODE_ENV === 'development'
let mainWindow: BrowserWindow | null = null
let pyProcess:  ChildProcess  | null = null

// Start FastAPI backend 
function startPython(): void {
  const scriptPath = path.join(__dirname, '../backend/main.py')

  pyProcess = spawn('python', [scriptPath], { stdio: 'pipe' })

  pyProcess.stdout?.on('data', (d: Buffer) =>
    console.log('[PY]', d.toString().trim()))

  pyProcess.stderr?.on('data', (d: Buffer) =>
    console.error('[PY ERR]', d.toString().trim()))

  pyProcess.on('close', (code: number | null) =>
    console.log('[PY] exited with code', code))

  console.log('[PY] started — pid:', pyProcess.pid)
}

// Create main window  
function createWindow(): void {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1100,
    minHeight: 700,
    frame: false,
    backgroundColor: '#0d0d0f',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
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
}

// Window control IPC 
ipcMain.on('window:minimize', () => mainWindow?.minimize())
ipcMain.on('window:maximize', () => {
  mainWindow?.isMaximized()
    ? mainWindow.unmaximize()
    : mainWindow?.maximize()
})
ipcMain.on('window:close', () => mainWindow?.close())

// App lifecycle  
app.whenReady().then(() => {
  startPython()
  createWindow()
})

app.on('window-all-closed', () => {
  pyProcess?.kill()
  app.quit()
})

app.on('before-quit', () => {
  pyProcess?.kill()
})
