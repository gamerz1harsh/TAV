// Electron preload script — exposes a safe, typed API to the renderer.
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('ElectronAPI', {
  // App lifecycle
  onServerReady: (callback) => ipcRenderer.on('server:ready', () => callback()),
  onServerFailed: (callback) => ipcRenderer.on('server:failed', (_event, error) => callback(error)),

  // Dialog helpers
  showErrorMessage: (title, content) => ipcRenderer.invoke('dialog:error', title, content),

  // Open external links
  openExternal: (url) => ipcRenderer.invoke('shell:openExternal', url),

  // Get Python path used by the main process
  getPythonInfo: () => ipcRenderer.invoke('python:info'),

  // Logging
  logToMain: (level, message) => ipcRenderer.send('app:log', level, message),
});
