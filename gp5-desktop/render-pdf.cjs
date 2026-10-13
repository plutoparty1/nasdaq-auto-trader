const { BrowserWindow, ipcMain } = require('electron');
const path = require('node:path');
const { randomUUID } = require('node:crypto');

async function renderTrackPdf(bytes, trackIndex, signal, encoding = 'utf-8') {
  signal.throwIfAborted();
  const jobId = randomUUID();
  const window = new BrowserWindow({
    show: false,
    width: 1000,
    height: 1200,
    webPreferences: {
      preload: path.join(__dirname, 'preload-score.cjs'),
      sandbox: true,
      contextIsolation: true,
      nodeIntegration: false,
      backgroundThrottling: false,
    },
  });
  const webContents = window.webContents;
  webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  webContents.on('will-navigate', (event) => event.preventDefault());
  let timer;
  let done;
  let onCrash;
  let onAbort;
  let onClose;
  try {
    const interrupted = new Promise((_resolve, reject) => {
      const fail = (message) => reject(new Error(message));
      timer = setTimeout(() => fail('악보 한 파트의 변환 시간이 90초를 넘었습니다.'), 90_000);
      onAbort = () => reject(signal.reason);
      onCrash = () => fail('악보 변환 화면이 중단됐습니다.');
      onClose = () => fail('악보 변환 화면이 닫혔습니다.');
      signal.addEventListener('abort', onAbort, { once: true });
      webContents.once('render-process-gone', onCrash);
      window.once('closed', onClose);
    });
    const ready = new Promise((resolve, reject) => {
      done = (event, result) => {
        if (event.sender !== webContents || event.senderFrame !== webContents.mainFrame || result?.id !== jobId) return;
        if (result.ok === true) resolve();
        else reject(new Error(typeof result.error === 'string' ? result.error : '악보를 그리지 못했습니다.'));
      };
      ipcMain.on('gp5:render-done', done);
      window.loadFile(path.join(__dirname, 'score.html')).then(() => {
        signal.throwIfAborted();
        if (!window.isDestroyed()) webContents.send('gp5:render-job', { id: jobId, bytes, trackIndex, encoding });
      }).catch(reject);
    });
    const printed = ready.then(async () => {
      signal.throwIfAborted();
      const pdf = await webContents.printToPDF({
        pageSize: 'A4',
        preferCSSPageSize: true,
        printBackground: true,
        margins: { top: 0, bottom: 0, left: 0, right: 0 },
        generateTaggedPDF: true,
      });
      signal.throwIfAborted();
      if (pdf.subarray(0, 5).toString() !== '%PDF-') throw new Error('PDF 생성 결과가 올바르지 않습니다.');
      return pdf;
    });
    return await Promise.race([printed, interrupted]);
  } finally {
    clearTimeout(timer);
    if (done) ipcMain.removeListener('gp5:render-done', done);
    if (onAbort) signal.removeEventListener('abort', onAbort);
    if (onClose) window.removeListener('closed', onClose);
    if (onCrash) webContents.removeListener('render-process-gone', onCrash);
    if (!window.isDestroyed()) window.destroy();
  }
}

module.exports = { renderTrackPdf };
