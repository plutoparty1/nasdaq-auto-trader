const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('scoreJob', {
  onRender(callback) {
    ipcRenderer.removeAllListeners('gp5:render-job');
    ipcRenderer.on('gp5:render-job', (_event, job) => callback(job));
  },
  done(result) {
    ipcRenderer.send('gp5:render-done', result);
  },
});
