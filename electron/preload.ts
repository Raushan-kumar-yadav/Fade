import { contextBridge, ipcRenderer } from 'electron'

export interface ElectronAPI {
  minimize:     () => void
  maximize:     () => void
  close:        () => void
  onBackendPort: (cb: (port: number) => void) => void
  getPort:      () => Promise<number | null>

  // ── Native render engine ───────────────────────────────────────────────────
  isNativeRender: () => Promise<boolean>
  renderSeek:  (frame: number) => void
  renderPlay:  () => void
  renderPause: () => void
  getRenderBuffer: () => Promise<ArrayBuffer | null>
  onFrameReady: (cb: (frameNum: number) => void) => () => void
  getRenderStats: () => Promise<{ width: number; height: number; fps: number; bufferSize: number } | null>

  // ── Export ─────────────────────────────────────────────────────────────────
  startExport: (config: {
    outputPath: string
    width: number
    height: number
    fps: number
    codec?: string
    videoBitrate?: string
  }) => void
  onExportProgress: (cb: (p: {
    frame: number
    total: number
    done: boolean
    error: string
  }) => void) => () => void   // returns cleanup fn
  cancelExport: () => void

  // ── File dialogs ────────────────────────────────────────────────────────────
  showSaveDialog: (opts?: {
    filters?: { name: string; extensions: string[] }[]
    defaultPath?: string
  }) => Promise<string | undefined>
}

contextBridge.exposeInMainWorld('electronAPI', {
  minimize: (): void => ipcRenderer.send('window:minimize'),
  maximize: (): void => ipcRenderer.send('window:maximize'),
  close:    (): void => ipcRenderer.send('window:close'),

  onBackendPort: (cb: (port: number) => void): void => {
    ipcRenderer.on('backend:port', (_event, port: number) => cb(port))
  },

  getPort: (): Promise<number | null> => ipcRenderer.invoke('backend:get-port'),

  // ── Native render engine ─────────────────────────────────────────────────────
  isNativeRender: (): Promise<boolean> => ipcRenderer.invoke('render:is-native'),

  renderSeek:  (frame: number): void => ipcRenderer.send('render:seek', frame),
  renderPlay:  (): void => ipcRenderer.send('render:play'),
  renderPause: (): void => ipcRenderer.send('render:pause'),

  getRenderBuffer: (): Promise<ArrayBuffer | null> => ipcRenderer.invoke('render:get-buffer'),
  getRenderStats:  (): Promise<{ width: number; height: number; fps: number; bufferSize: number } | null> =>
    ipcRenderer.invoke('render:get-stats'),

  onFrameReady: (cb: (frameNum: number) => void): (() => void) => {
    const handler = (_event: Electron.IpcRendererEvent, frameNum: number) => cb(frameNum)
    ipcRenderer.on('render:frame-ready', handler)
    return () => ipcRenderer.removeListener('render:frame-ready', handler)
  },

  // ── Export ─────────────────────────────────────────────────────────────────
  startExport: (config: any): void => ipcRenderer.send('export:start', config),

  onExportProgress: (cb: (p: any) => void): (() => void) => {
    const handler = (_event: Electron.IpcRendererEvent, p: any) => cb(p)
    ipcRenderer.on('export:progress', handler)
    return () => ipcRenderer.removeListener('export:progress', handler)
  },

  cancelExport: (): void => ipcRenderer.send('export:cancel'),

  // ── File dialogs ───────────────────────────────────────────────────────────
  showSaveDialog: (opts?: any): Promise<string | undefined> =>
    ipcRenderer.invoke('dialog:save', opts),

} satisfies ElectronAPI)
