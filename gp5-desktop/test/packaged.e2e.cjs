const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const net = require('node:net');
const { spawn } = require('node:child_process');
const { createHash } = require('node:crypto');
const { makeKoreanGp5 } = require('./fixtures/korean-score.cjs');

const root = path.join(__dirname, '..');
const evidence = path.join(root, 'qa');
const executable = process.env.GP5_QA_EXE || path.join(root, 'release', 'GP5-PDF-Windows-x64.exe');
let socket;
let child;
let sequence = 0;
const requests = new Map();
const events = [];
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));

async function until(probe, label) {
  const deadline = Date.now() + 90_000;
  while (Date.now() < deadline) {
    const result = await probe();
    if (result) return result;
    await delay(100);
  }
  throw new Error(`Timed out: ${label}`);
}

function call(method, params = {}) {
  return new Promise((resolve, reject) => {
    const id = ++sequence;
    const timer = setTimeout(() => { requests.delete(id); reject(new Error(`${method}: ${params.expression || ''}`)); }, 95_000);
    requests.set(id, { resolve, reject, timer });
    socket.send(JSON.stringify({ id, method, params }));
  });
}

async function evaluate(expression) {
  const result = await call('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true });
  if (result.exceptionDetails) throw new Error(JSON.stringify(result.exceptionDetails));
  return result.result.value;
}

async function run() {
  await fs.mkdir(evidence, { recursive: true });
  const folder = await fs.mkdtemp(path.join(evidence, 'packaged-'));
  const source = path.join(folder, '배포 검증.gp5');
  const fixture = makeKoreanGp5('euc-kr', { trackNames: ['리드 기타 뷁', '베이스', '드럼'] });
  const original = fixture.bytes;
  await fs.writeFile(source, original);
  const server = net.createServer();
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const port = server.address().port;
  await new Promise(resolve => server.close(resolve));
  child = spawn(executable, [`--inspect-brk=127.0.0.1:${port}`, `--user-data-dir=${path.join(folder, 'profile')}`], { stdio: 'ignore' });
  child.on('error', error => console.error(error));
  const endpoint = await until(async () => {
    try {
      const response = await fetch(`http://127.0.0.1:${port}/json/list`, { signal: AbortSignal.timeout(1000) });
      return (await response.json())[0]?.webSocketDebuggerUrl;
    } catch { return false; }
  }, 'packaged inspector');
  socket = new WebSocket(endpoint);
  socket.addEventListener('message', event => {
    const message = JSON.parse(event.data);
    if (!message.id) { events.push(message); return; }
    const request = requests.get(message.id);
    if (!request) return;
    clearTimeout(request.timer);
    requests.delete(message.id);
    if (message.error) request.reject(new Error(JSON.stringify(message.error)));
    else request.resolve(message.result);
  });
  await new Promise((resolve, reject) => {
    socket.addEventListener('open', resolve, { once: true });
    socket.addEventListener('error', reject, { once: true });
  });
  await call('Debugger.enable');
  await call('Runtime.runIfWaitingForDebugger');
  const paused = await until(() => events.find(event => event.method === 'Debugger.paused'), 'main entry');
  const setup = await call('Debugger.evaluateOnCallFrame', {
    callFrameId: paused.params.callFrames[0].callFrameId,
    expression: `globalThis.__gp5qa = { electron: require('electron'), selected: ${JSON.stringify(source)} }; __gp5qa.electron.dialog.showOpenDialog = async () => ({ canceled: false, filePaths: [__gp5qa.selected] }); 'ready'`,
    returnByValue: true,
  });
  if (setup.exceptionDetails) throw new Error(JSON.stringify(setup.exceptionDetails));
  await call('Debugger.resume');
  const windowExpression = "__gp5qa.electron.BrowserWindow.getAllWindows().find(win => win.webContents.getURL().endsWith('renderer.html'))";
  const ui = code => evaluate(`${windowExpression}?.webContents.executeJavaScript(${JSON.stringify(code)}, true)`);
  await until(() => ui("document.querySelectorAll('#tracks li').length === 3"), 'automatic GP5 selection');
  assert.deepEqual(await ui("[...document.querySelectorAll('.track-name')].map(row => row.textContent)"), fixture.trackNames);
  assert.equal(await ui("document.querySelectorAll('.track-check:checked').length"), 3);
  await ui("document.querySelector('.track-check[value=\"1\"]').click()");
  assert.equal(await ui("document.getElementById('select-all').indeterminate"), true);
  const runtime = await evaluate('({packaged: __gp5qa.electron.app.isPackaged, version: __gp5qa.electron.app.getVersion(), path: __gp5qa.electron.app.getAppPath(), executable: process.execPath, electron: process.versions.electron})');
  assert.equal(runtime.packaged, true);
  assert.equal(runtime.version, '1.1.0');
  assert.match(runtime.path, /app\.asar$/);
  await ui("document.getElementById('convert').click()");
  await until(() => ui("document.querySelector('main').getAttribute('aria-busy') === 'false'"), 'packaged conversion');
  assert.equal(await ui("document.getElementById('error').hidden"), true, await ui("document.getElementById('error').textContent"));
  const names = (await fs.readdir(folder)).filter(name => name.endsWith('.pdf'));
  assert.equal(names.length, 2);
  assert.ok(names.some(name => name.includes('01') && name.includes(fixture.trackNames[0])));
  assert.ok(names.some(name => name.includes('03') && name.includes(fixture.trackNames[2])));
  assert.ok(names.every(name => !name.includes(fixture.trackNames[1])));
  assert.deepEqual(await ui("[...document.querySelectorAll('.track-state')].map(row => row.textContent)"), ['저장됨', '선택 안 함', '저장됨']);
  for (const name of names) assert.equal((await fs.readFile(path.join(folder, name))).subarray(0, 5).toString(), '%PDF-');
  assert.deepEqual(await fs.readFile(source), original);
  console.log('STEP: packaged conversion and source preservation verified');
  await evaluate(`(() => { const win = ${windowExpression}; win.webContents.setBackgroundThrottling(false); win.show(); win.focus(); })()`);
  await ui('document.fonts.ready.then(() => true)');
  console.log('STEP: fonts ready; capturing foreground window');
  const png = await evaluate(`${windowExpression}.webContents.capturePage().then(image => image.toPNG().toString('base64'))`);
  await fs.writeFile(path.join(evidence, 'packaged-complete.png'), Buffer.from(png, 'base64'));
  const report = { passed: true, executable, sha256: createHash('sha256').update(await fs.readFile(executable)).digest('hex'), runtime, source, encoding: 'euc-kr', title: fixture.title, trackNames: fixture.trackNames, selectedIndices: [0, 2], files: names.map(name => path.join(folder, name)), nativeDialogIntercepted: true };
  await fs.writeFile(path.join(evidence, 'packaged-report.json'), JSON.stringify(report, null, 2));
  console.log(JSON.stringify(report));
}

run().catch(error => { console.error(error); process.exitCode = 1; }).finally(async () => {
  if (socket?.readyState === WebSocket.OPEN) {
    try { await evaluate('setTimeout(() => __gp5qa.electron.app.quit(), 100); true'); } catch (error) { console.error(error); }
    socket.close();
  } else if (child && child.exitCode === null) child.kill();
  for (const request of requests.values()) clearTimeout(request.timer);
});
