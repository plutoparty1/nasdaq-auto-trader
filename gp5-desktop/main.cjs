'use strict';

const { app, BrowserWindow, dialog, ipcMain, session, shell } = require('electron');
const fs = require('node:fs/promises');
const path = require('node:path');
const { parseGp5 } = require('./import-score.cjs');
const { writeTrackPdf } = require('./storage.cjs');
const { renderTrackPdf } = require('./render-pdf.cjs');
const { parseSelection } = require('./selection.cjs');

let mainWindow = null;
let source = null;
let picking = false;
let conversion = null;
let abortController = null;
let quitPending = false;

function authorize(event) {
  if (!mainWindow || mainWindow.isDestroyed() || event.sender !== mainWindow.webContents || event.senderFrame !== mainWindow.webContents.mainFrame) {
    throw new Error('허용되지 않은 요청입니다.');
  }
}

function errorMessage(error) {
  if (error.code === 'EACCES' || error.code === 'EPERM') return '폴더에 접근할 권한이 없습니다. 쓰기 가능한 폴더로 GP5 파일을 옮겨 주세요.';
  if (error.code === 'ENOSPC') return '저장 공간이 부족합니다. 공간을 확보한 뒤 다시 시도해 주세요.';
  if (error.code === 'ENOENT') return '파일 또는 출력 폴더를 찾을 수 없습니다. GP5 파일을 다시 선택해 주세요.';
  return error instanceof Error ? error.message : '작업 중 오류가 발생했습니다.';
}

function progress(selection, current, status) {
  if (mainWindow && !mainWindow.isDestroyed() && !mainWindow.webContents.isDestroyed()) {
    const trackIndex = selection[Math.max(0, current - 1)];
    mainWindow.webContents.send('gp5:progress', {
      current,
      total: selection.length,
      trackIndex,
      track: source.trackNames[trackIndex],
      status,
    });
  }
}

async function chooseFile(event) {
  authorize(event);
  if (conversion || picking || quitPending) return { source: null, error: '현재 작업이 끝난 뒤 파일을 선택해 주세요.' };
  picking = true;
  try {
    const result = await dialog.showOpenDialog(mainWindow, {
      title: 'GP5 악보 선택',
      properties: ['openFile'],
      filters: [{ name: 'Guitar Pro 5', extensions: ['gp5'] }],
    });
    if (result.canceled || result.filePaths.length === 0) return { source: null, error: null };
    const filename = result.filePaths[0];
    const stat = await fs.stat(filename);
    if (!stat.isFile() || stat.size > 64 * 1024 * 1024) throw new Error('64MB 이하의 GP5 파일을 선택해 주세요.');
    const bytes = await fs.readFile(filename);
    const name = path.basename(filename);
    const metadata = parseGp5(bytes, name);
    source = { path: filename, name, folder: path.dirname(filename), ...metadata, bytes };
    return { source: { path: source.path, name, folder: source.folder, ...metadata }, error: null };
  } catch (error) {
    return { source: null, error: errorMessage(error) };
  } finally {
    picking = false;
  }
}

async function convertTracks(selection, signal) {
  const files = [];
  let current = 0;
  try {
    for (const [ordinal, index] of selection.entries()) {
      signal.throwIfAborted();
      current = ordinal + 1;
      progress(selection, current, 'rendering');
      const pdf = await renderTrackPdf(source.bytes, index, signal, source.encoding);
      signal.throwIfAborted();
      const file = await writeTrackPdf({
        folder: source.folder,
        sourceName: source.name,
        trackName: source.trackNames[index],
        trackIndex: index,
      }, pdf, signal);
      files.push(file);
      progress(selection, current, 'saved');
    }
    progress(selection, current, 'complete');
    return { files, error: null, cancelled: false };
  } catch (error) {
    const cancelled = error.name === 'AbortError';
    progress(selection, current, cancelled ? 'cancelled' : 'error');
    return { files, error: cancelled ? null : errorMessage(error), cancelled };
  }
}

function convert(event, indices) {
  authorize(event);
  if (conversion || picking || quitPending) return { files: [], error: '이미 작업을 진행하고 있습니다.', cancelled: false };
  if (!source) return { files: [], error: '먼저 GP5 파일을 선택해 주세요.', cancelled: false };
  let selection;
  try {
    selection = parseSelection(indices, source.trackNames.length);
  } catch (error) {
    return { files: [], error: errorMessage(error), cancelled: false };
  }
  abortController = new AbortController();
  conversion = convertTracks(selection, abortController.signal).finally(() => {
    conversion = null;
    abortController = null;
  });
  return conversion;
}

function finishBeforeQuit(event) {
  if (!conversion) return;
  event.preventDefault();
  if (quitPending) return;
  quitPending = true;
  abortController.abort();
  void conversion.then(() => app.quit(), () => app.quit());
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 960,
    height: 760,
    minWidth: 760,
    minHeight: 640,
    title: 'GP5 to PDF',
    autoHideMenuBar: true,
    backgroundColor: '#f4f6f5',
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      webviewTag: false,
    },
  });
  mainWindow.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  mainWindow.webContents.on('will-navigate', (event) => event.preventDefault());
  mainWindow.webContents.on('will-attach-webview', (event) => event.preventDefault());
  mainWindow.webContents.on('render-process-gone', () => abortController?.abort());
  mainWindow.on('close', finishBeforeQuit);
  mainWindow.on('closed', () => { mainWindow = null; });
  void mainWindow.loadFile(path.join(__dirname, 'renderer.html')).catch((error) => {
    dialog.showErrorBox('앱을 시작할 수 없습니다.', errorMessage(error));
    app.quit();
  });
}

ipcMain.handle('gp5:choose-file', chooseFile);
ipcMain.handle('gp5:convert', convert);
ipcMain.handle('gp5:cancel', (event) => {
  authorize(event);
  abortController?.abort();
});
ipcMain.handle('gp5:open-output-folder', async (event) => {
  authorize(event);
  if (!source) return;
  const error = await shell.openPath(source.folder);
  if (error) throw new Error(error);
});

app.on('before-quit', finishBeforeQuit);
app.on('window-all-closed', () => { if (process.platform !== 'darwin') app.quit(); });
app.on('activate', () => { if (!mainWindow && !quitPending) createWindow(); });
void app.whenReady().then(() => {
  session.defaultSession.setPermissionRequestHandler((_contents, _permission, callback) => callback(false));
  session.defaultSession.setPermissionCheckHandler(() => false);
  session.defaultSession.webRequest.onBeforeRequest((details, callback) => {
    callback({ cancel: !/^(file|data|blob|about):/.test(details.url) });
  });
  createWindow();
}).catch((error) => {
  dialog.showErrorBox('앱을 시작할 수 없습니다.', errorMessage(error));
  app.quit();
});
