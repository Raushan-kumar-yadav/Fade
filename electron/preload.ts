import { contextBridge, ipcRenderer } from 'electron'

export interface ElectronAPI {
  minimize:     () => void
  maximize:     () => void
  close:        () => void
  onBackendPort: (cb: (port: number) => void) => void
  getPort:      () => Promise<number | null>
}

contextBridge.exposeInMainWorld('electronAPI', {
  minimize: (): void => ipcRenderer.send('window:minimize'),
  maximize: (): void => ipcRenderer.send('window:maximize'),
  close:    (): void => ipcRenderer.send('window:close'),

  // Pushed from main process when Python announces its port
  onBackendPort: (cb: (port: number) => void): void => {
    ipcRenderer.on('backend:port', (_event, port: number) => cb(port))
  },

  // Pull: renderer can ask for the current port (in case it missed the push)
  getPort: (): Promise<number | null> => ipcRenderer.invoke('backend:get-port'),
} satisfies ElectronAPI)
