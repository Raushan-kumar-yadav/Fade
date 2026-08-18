import { contextBridge, ipcRenderer } from 'electron'

 export interface ElectronAPI {
  minimize: () => void
  maximize: () => void
  close: () => void
}

 contextBridge.exposeInMainWorld('electronAPI', {
  minimize: (): void => ipcRenderer.send('window:minimize'),
  maximize: (): void => ipcRenderer.send('window:maximize'),
  close: (): void => ipcRenderer.send('window:close'),
} satisfies ElectronAPI)
