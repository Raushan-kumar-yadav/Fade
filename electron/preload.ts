import { contextBridge, ipcRenderer } from 'electron'

export interface ElectronAPI {
  minimize:     () => void
  maximize:     () => void
  close:        () => void
  onBackendPort: (cb: (port: number) => void) => void
  getPort:      () => Promise<number | null>

  // ── Native render engine ───────────────────────────────────────────────────
  // Returns true if render_engine.node is loaded and working
  isNativeRender: () => Promise<boolean>

  // Seek to a specific frame — C++ fetches layout from Python, composites, writes SharedArrayBuffer
  renderSeek:  (frame: number) => void
  renderPlay:  () => void
  renderPause: () => void

  // Get the raw SharedArrayBuffer — call once and cache; it's the same buffer every frame
  getRenderBuffer: () => Promise<ArrayBuffer | null>

  // Subscribe to frame-ready events from the C++ compositor
  onFrameReady: (cb: (frameNum: number) => void) => () => void

  // Stats for debugging
  getRenderStats: () => Promise<{ width: number; height: number; fps: number; bufferSize: number } | null>
}

contextBridge.exposeInMainWorld('electronAPI', {
  minimize: (): void => ipcRenderer.send('window:minimize'),
  maximize: (): void => ipcRenderer.send('window:maximize'),
  close:    (): void => ipcRenderer.send('window:close'),

  onBackendPort: (cb: (port: number) => void): void => {
    ipcRenderer.on('backend:port', (_event, port: number) => cb(port))
  },

  getPort: (): Promise<number | null> => ipcRenderer.invoke('backend:get-port'),

  // ── Native render engine ───────────────────────────────────────────────────
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
    // Return cleanup function
    return () => ipcRenderer.removeListener('render:frame-ready', handler)
  },
} satisfies ElectronAPI)
