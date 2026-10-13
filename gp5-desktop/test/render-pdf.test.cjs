'use strict';

const assert = require('node:assert/strict');
const { EventEmitter, getEventListeners } = require('node:events');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

function deferred() {
  let resolve;
  const promise = new Promise((complete) => { resolve = complete; });
  return { promise, resolve };
}

function createHarness() {
  const ipcMain = new EventEmitter();
  const timers = new Map();
  const printStarted = deferred();
  const printResult = deferred();
  const jobSent = deferred();
  let window;
  let job;
  let automaticallyComplete = true;
  class BrowserWindow extends EventEmitter {
    constructor() {
      super();
      window = this;
      this.destroyed = false;
      this.webContents = new EventEmitter();
      this.webContents.mainFrame = {};
      this.webContents.setWindowOpenHandler = () => {};
      this.webContents.send = (_channel, payload) => {
        job = payload;
        jobSent.resolve();
        if (automaticallyComplete) completeRender(this.webContents.mainFrame);
      };
      this.webContents.printToPDF = () => {
        printStarted.resolve();
        return printResult.promise;
      };
    }
    loadFile() { return Promise.resolve(); }
    isDestroyed() { return this.destroyed; }
    destroy() { this.destroyed = true; this.emit('closed'); }
  }
  function completeRender(senderFrame) {
    ipcMain.emit('gp5:render-done', { sender: window.webContents, senderFrame }, { id: job.id, ok: true });
  }
  const module = { exports: {} };
  const filename = path.join(__dirname, '..', 'render-pdf.cjs');
  vm.runInNewContext(fs.readFileSync(filename, 'utf8'), {
    module,
    __dirname: path.dirname(filename),
    require: (name) => name === 'electron' ? { BrowserWindow, ipcMain } : require(name),
    setTimeout(callback, milliseconds) {
      const id = {};
      timers.set(id, { callback, milliseconds });
      return id;
    },
    clearTimeout: (id) => timers.delete(id),
  }, { filename });
  return {
    render: module.exports.renderTrackPdf,
    get job() { return job; },
    get window() { return window; },
    timers,
    ipcMain,
    printStarted: printStarted.promise,
    jobSent: jobSent.promise,
    completePrint: () => printResult.resolve(Buffer.from('%PDF-1.7\n')),
    completeRender,
    manualReadiness: () => { automaticallyComplete = false; },
  };
}

async function beginStalledPrint(t) {
  const harness = createHarness();
  const controller = new AbortController();
  const result = harness.render(Buffer.from('source'), 0, controller.signal)
    .then((pdf) => ({ pdf }), (error) => ({ error }));
  t.after(async () => { harness.completePrint(); await result; });
  await harness.printStarted;
  return { harness, controller, result };
}

async function requireSettled(result) {
  const outcome = await Promise.race([
    result,
    new Promise((resolve) => setImmediate(() => resolve({ pending: true }))),
  ]);
  assert.equal(outcome.pending, undefined, 'render task must settle while printToPDF remains stalled');
  return outcome;
}

function assertClean(harness, signal) {
  assert.equal(harness.window.isDestroyed(), true);
  assert.equal(harness.ipcMain.listenerCount('gp5:render-done'), 0);
  assert.equal(harness.window.listenerCount('closed'), 0);
  assert.equal(harness.window.webContents.listenerCount('render-process-gone'), 0);
  assert.equal(getEventListeners(signal, 'abort').length, 0);
  assert.equal(harness.timers.size, 0);
}

test('abort settles a stalled print and destroys its hidden window without leaked listeners', async (t) => {
  const { harness, controller, result } = await beginStalledPrint(t);
  assert.equal(getEventListeners(controller.signal, 'abort').length, 1);
  controller.abort();
  const outcome = await requireSettled(result);
  assert.equal(outcome.error, controller.signal.reason);
  assertClean(harness, controller.signal);
});

test('the 90 second timeout settles a stalled print and removes every lifecycle listener', async (t) => {
  const { harness, controller, result } = await beginStalledPrint(t);
  const timeout = [...harness.timers.values()][0];
  assert.equal(timeout.milliseconds, 90_000);
  timeout.callback();
  const outcome = await requireSettled(result);
  assert.match(outcome.error.message, /90초/);
  assertClean(harness, controller.signal);
});

test('renderer crash settles a stalled print and cleans up its window', async (t) => {
  const { harness, controller, result } = await beginStalledPrint(t);
  harness.window.webContents.emit('render-process-gone');
  const outcome = await requireSettled(result);
  assert.match(outcome.error.message, /중단/);
  assertClean(harness, controller.signal);
});

test('closing the hidden window settles a stalled print and removes remaining listeners', async (t) => {
  const { harness, controller, result } = await beginStalledPrint(t);
  harness.window.destroy();
  const outcome = await requireSettled(result);
  assert.match(outcome.error.message, /닫혔/);
  assertClean(harness, controller.signal);
});

test('readiness accepts only the hidden window main frame before printing and cleans up success', async () => {
  const harness = createHarness();
  harness.manualReadiness();
  const controller = new AbortController();
  const result = harness.render(Buffer.from('source'), 0, controller.signal);
  await harness.jobSent;
  harness.completeRender({});
  const prematurePrint = await Promise.race([
    harness.printStarted.then(() => true),
    new Promise((resolve) => setImmediate(() => resolve(false))),
  ]);
  assert.equal(prematurePrint, false);
  harness.completeRender(harness.window.webContents.mainFrame);
  await harness.printStarted;
  harness.completePrint();
  assert.match((await result).toString(), /^%PDF-/);
  assertClean(harness, controller.signal);
});

test('passes the importer charset into the PDF job for the same Korean text', async () => {
  const harness = createHarness();
  const controller = new AbortController();
  const result = harness.render(Buffer.from('source'), 2, controller.signal, 'euc-kr');
  await harness.jobSent;
  harness.completePrint();
  await result;
  assert.equal(harness.job.encoding, 'euc-kr');
  assert.equal(harness.job.trackIndex, 2);
  assertClean(harness, controller.signal);
});
