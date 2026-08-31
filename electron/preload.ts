import { contextBridge, ipcRenderer } from 'electron'

export interface ElectronAPI {
  minimize: () => void
  maximize: () => void
  close: () => void
  onBackendPort: (cb: (port: number) => void) => void
  getPort: () => Promise<number | null>

  //   Native render engine  
  isNativeRender: () => Promise<boolean>
  renderSeek: (frame: number) => void
  renderPlay: () => void
  renderPause: () => void
  renderSetPreviewScale: (scale: number) => void
  getRenderBuffer: () => Promise<ArrayBuffer | null>
  onFrameReady: (cb: (frameNum: number) => void) => () => void
  getRenderStats: () => Promise<{ width: number; height: number; fps: number; bufferSize: number } | null>

  // export
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
  onExportWebcompPhase: (cb: (p: {
    active: boolean
    done: number
    total: number
  }) => void) => () => void   // WebComp pre-render progress
  cancelExport: () => void

  //     File dialogs  
  showSaveDialog: (opts?: {
    filters?: { name: string; extensions: string[] }[]
    defaultPath?: string
  }) => Promise<string | undefined>
  getAppPath: (name: string) => Promise<string | null>

  showOpenDialog: (opts?: {
    filters?: { name: string; extensions: string[] }[]
    defaultPath?: string
  }) => Promise<string | undefined>

  //     WebComp  
  webcompCreate: (opts: {
    webcompId: string; htmlUrl: string;
    width: number; height: number; fps: number;
  }) => Promise<boolean>
  webcompCaptureFrame: (webcompId: string, frame: number) => Promise<Buffer | null>
  webcompPrefetch: (webcompId: string, startFrame: number, count: number) => Promise<boolean>
  webcompUpdateParams: (webcompId: string, params: Record<string, any>) => void
  webcompReload: (webcompId: string) => void
  webcompDestroy: (webcompId: string) => void
  webcompPushToNative: (webcompId: string, localFrame: number, width: number, height: number, timelineFrame?: number) => Promise<boolean>
}

contextBridge.exposeInMainWorld('electronAPI', {
  minimize: (): void => ipcRenderer.send('window:minimize'),
  maximize: (): void => ipcRenderer.send('window:maximize'),
  close:    (): void => ipcRenderer.send('window:close'),

  onBackendPort: (cb: (port: number) => void): void => {
    ipcRenderer.on('backend:port', (_event, port: number) => cb(port))
  },

  getPort: (): Promise<number | null> => ipcRenderer.invoke('backend:get-port'),

  //   Native render engine  
  isNativeRender: (): Promise<boolean> => ipcRenderer.invoke('render:is-native'),

  renderSeek: (frame: number): void => ipcRenderer.send('render:seek', frame),
  renderPlay:  (): void => ipcRenderer.send('render:play'),
  renderPause: (): void => ipcRenderer.send('render:pause'),
  renderSetPreviewScale: (scale: number): void => ipcRenderer.send('render:set-preview-scale', scale),

  getRenderBuffer: (): Promise<ArrayBuffer | null> => ipcRenderer.invoke('render:get-buffer'),
  getRenderStats:  (): Promise<{ width: number; height: number; fps: number; bufferSize: number } | null> =>
    ipcRenderer.invoke('render:get-stats'),

  onFrameReady: (cb: (frameNum: number) => void): (() => void) => {
    const handler = (_event: Electron.IpcRendererEvent, frameNum: number) => cb(frameNum)
    ipcRenderer.on('render:frame-ready', handler)
    return () => ipcRenderer.removeListener('render:frame-ready', handler)
  },

  //   Export  
  startExport: (config: any): void => ipcRenderer.send('export:start', config),

  onExportProgress: (cb: (p: any) => void): (() => void) => {
    const handler = (_event: Electron.IpcRendererEvent, p: any) => cb(p)
    ipcRenderer.on('export:progress', handler)
    return () => ipcRenderer.removeListener('export:progress', handler)
  },

  onExportWebcompPhase: (cb: (p: any) => void): (() => void) => {
    const handler = (_event: Electron.IpcRendererEvent, p: any) => cb(p)
    ipcRenderer.on('export:webcomp-phase', handler)
    return () => ipcRenderer.removeListener('export:webcomp-phase', handler)
  },

  cancelExport: (): void => ipcRenderer.send('export:cancel'),

  // File dialogs  
  showSaveDialog: (opts?: any): Promise<string | undefined> =>
    ipcRenderer.invoke('dialog:save', opts),

  showOpenDialog: (opts?: any): Promise<string | undefined> =>
    ipcRenderer.invoke('dialog:open', opts),

  getAppPath: (name: string): Promise<string | null> =>
    ipcRenderer.invoke('app:get-path', name),

  //   WebComp  
  webcompCreate: (opts: any): Promise<boolean> =>
    ipcRenderer.invoke('webcomp:create', opts),

  webcompCaptureFrame: (id: string, frame: number): Promise<Buffer | null> =>
    ipcRenderer.invoke('webcomp:capture-frame', id, frame),

  webcompPrefetch: (id: string, start: number, count: number): Promise<boolean> =>
    ipcRenderer.invoke('webcomp:prefetch', id, start, count),

  webcompUpdateParams: (id: string, params: Record<string, any>): void =>
    ipcRenderer.send('webcomp:update-params', id, params),

  webcompReload: (id: string): void =>
    ipcRenderer.send('webcomp:reload', id),

  webcompDestroy: (id: string): void =>
    ipcRenderer.send('webcomp:destroy', id),

  webcompPushToNative: (id: string, localFrame: number, w: number, h: number, timelineFrame?: number): Promise<boolean> =>
    ipcRenderer.invoke('webcomp:push-to-native', id, localFrame, w, h, timelineFrame),

} satisfies ElectronAPI)
