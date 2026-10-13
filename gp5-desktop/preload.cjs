'use strict';

const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('gp5', Object.freeze({
  chooseFile: () => ipcRenderer.invoke('gp5:choose-file'),
  convert: (indices) => ipcRenderer.invoke('gp5:convert', indices),
  cancel: () => ipcRenderer.invoke('gp5:cancel'),
  openOutputFolder: () => ipcRenderer.invoke('gp5:open-output-folder'),
  onProgress(callback) {
    if (typeof callback !== 'function') throw new TypeError('A progress callback is required.');
    const listener = (_event, progress) => callback({
      current: progress.current,
      total: progress.total,
      trackIndex: progress.trackIndex,
      track: progress.track,
      status: progress.status,
    });
    ipcRenderer.on('gp5:progress', listener);
    return () => ipcRenderer.removeListener('gp5:progress', listener);
  },
}));
