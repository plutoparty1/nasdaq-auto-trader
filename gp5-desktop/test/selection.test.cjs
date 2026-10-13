'use strict';

const assert = require('node:assert/strict');
const { EventEmitter } = require('node:events');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');
const { parseSelection } = require('../selection.cjs');

const invalidSelections = [
  undefined, null, '0', 0, {}, new Set([0]), new Uint8Array([0]),
  [], [0, 0], [-1], [3], [0.5], [NaN], [Infinity], ['0'], [true],
  new Array(1), [0, , 2], [0, 1, 2, 0],
];

test('selection accepts original track indices in requested order and snapshots caller input', () => {
  const indices = [2, 0];
  const selected = parseSelection(indices, 3);
  indices[0] = 1;
  assert.deepEqual(selected, [2, 0]);
  assert.equal(Object.isFrozen(selected), true);
});

test('selection rejects missing, empty, duplicate, fractional, out-of-range and sparse indices', () => {
  for (const indices of invalidSelections) {
    assert.throws(() => parseSelection(indices, 3), /악기/);
  }
});

async function createBackend() {
  const handlers = new Map();
  const rendered = [];
  const written = [];
  const progress = [];
  let window;
  let progressListener = () => {};
  let rejectedTrack = null;
  class BrowserWindow extends EventEmitter {
    constructor() {
      super();
      window = this;
      this.webContents = new EventEmitter();
      this.webContents.mainFrame = {};
      this.webContents.isDestroyed = () => false;
      this.webContents.setWindowOpenHandler = () => {};
      this.webContents.send = (_channel, value) => { progress.push(value); progressListener(value); };
    }
    isDestroyed() { return false; }
    loadFile() { return Promise.resolve(); }
  }
  const app = new EventEmitter();
  app.whenReady = () => Promise.resolve();
  app.quit = () => {};
  const electron = {
    app, BrowserWindow,
    dialog: { showOpenDialog: async () => ({ canceled: false, filePaths: ['C:/music/Song.gp5'] }) },
    ipcMain: { handle: (channel, callback) => handlers.set(channel, callback) },
    shell: { openPath: async () => '' },
    session: { defaultSession: {
      setPermissionRequestHandler() {},
      setPermissionCheckHandler() {},
      webRequest: { onBeforeRequest() {} },
    } },
  };
  const overrides = {
    electron,
    'node:fs/promises': { stat: async () => ({ isFile: () => true, size: 10 }), readFile: async () => Buffer.from('source') },
    './import-score.cjs': { parseGp5: () => ({ title: '악보', trackNames: ['기타', '베이스', '드럼'], encoding: 'euc-kr' }) },
    './render-pdf.cjs': { renderTrackPdf: async (_bytes, index, _signal, encoding) => {
      rendered.push({ index, encoding });
      if (index === rejectedTrack) throw new Error('Render failed');
      return Buffer.from('render result');
    } },
    './storage.cjs': { writeTrackPdf: async (output) => {
      written.push(output);
      return path.join(output.folder, `${output.trackIndex + 1}.pdf`);
    } },
  };
  const filename = path.join(__dirname, '..', 'main.cjs');
  vm.runInNewContext(fs.readFileSync(filename, 'utf8'), {
    __dirname: path.dirname(filename),
    require: (name) => overrides[name] ?? (name.startsWith('./') ? require(path.join('..', name)) : require(name)),
    process: { platform: 'win32' },
    AbortController,
  }, { filename });
  await new Promise((resolve) => setImmediate(resolve));
  const invoke = (channel, argument) => handlers.get(channel)({ sender: window.webContents, senderFrame: window.webContents.mainFrame }, argument);
  const picked = await invoke('gp5:choose-file');
  assert.equal(picked.error, null);
  return {
    invoke, rendered, written, progress,
    onProgress: (callback) => { progressListener = callback; },
    rejectTrack: (index) => { rejectedTrack = index; },
  };
}

test('conversion renders only selected tracks, keeps original indices and forwards source encoding', async () => {
  const backend = await createBackend();
  const selected = [2, 0];
  const conversion = backend.invoke('gp5:convert', selected);
  selected[1] = 1;
  const result = await conversion;
  assert.equal(result.error, null);
  assert.equal(result.files.length, 2);
  assert.deepEqual(backend.rendered, [{ index: 2, encoding: 'euc-kr' }, { index: 0, encoding: 'euc-kr' }]);
  assert.deepEqual(backend.written.map((output) => output.trackIndex), [2, 0]);
  assert.deepEqual(backend.progress.filter((event) => event.status === 'rendering').map((event) => [event.current, event.total, event.trackIndex, event.track]), [
    [1, 2, 2, '드럼'], [2, 2, 0, '기타'],
  ]);
});

test('IPC rejects every invalid selection before rendering, writing, or publishing progress', async () => {
  const backend = await createBackend();
  for (const indices of invalidSelections) {
    const result = await backend.invoke('gp5:convert', indices);
    assert.equal(result.cancelled, false);
    assert.equal(result.files.length, 0);
    assert.equal(typeof result.error, 'string');
  }
  assert.deepEqual(backend.rendered, []);
  assert.deepEqual(backend.written, []);
  assert.deepEqual(backend.progress, []);
});

test('cancelling a selection keeps completed files and never renders a remaining unselected track', async () => {
  const backend = await createBackend();
  backend.onProgress((event) => {
    if (event.status === 'saved') backend.invoke('gp5:cancel');
  });
  const result = await backend.invoke('gp5:convert', [2, 0]);
  assert.equal(result.cancelled, true);
  assert.equal(result.error, null);
  assert.equal(result.files.length, 1);
  assert.deepEqual(backend.rendered.map((call) => call.index), [2]);
  const last = backend.progress.at(-1);
  assert.deepEqual([last.current, last.total, last.trackIndex, last.status], [1, 2, 2, 'cancelled']);
});

test('partial failure reports the selected ordinal and original track index while retaining completed files', async () => {
  const backend = await createBackend();
  backend.rejectTrack(0);
  const result = await backend.invoke('gp5:convert', [2, 0]);
  assert.equal(result.cancelled, false);
  assert.equal(typeof result.error, 'string');
  assert.equal(result.files.length, 1);
  assert.deepEqual(backend.written.map((output) => output.trackIndex), [2]);
  const last = backend.progress.at(-1);
  assert.deepEqual([last.current, last.total, last.trackIndex, last.track, last.status], [2, 2, 0, '기타', 'error']);
});

test('preload forwards the checked indices and original track index progress through the narrow API', async () => {
  let api;
  let listener;
  let invocation;
  const electron = {
    contextBridge: { exposeInMainWorld: (_name, value) => { api = value; } },
    ipcRenderer: {
      invoke: async (...args) => { invocation = args; },
      on: (_channel, callback) => { listener = callback; },
      removeListener: (_channel, callback) => { assert.equal(callback, listener); listener = null; },
    },
  };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '..', 'preload.cjs'), 'utf8'), { require: () => electron });
  await api.convert([2]);
  assert.deepEqual(invocation, ['gp5:convert', [2]]);
  let progress;
  const unsubscribe = api.onProgress((value) => { progress = value; });
  listener({}, { current: 1, total: 1, trackIndex: 2, track: '드럼', status: 'rendering' });
  assert.equal(progress.trackIndex, 2);
  unsubscribe();
  assert.equal(listener, null);
});
