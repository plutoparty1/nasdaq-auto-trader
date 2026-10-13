const { app, BrowserWindow, dialog, session, shell } = require('electron');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const { createHash } = require('node:crypto');

const evidence = path.join(__dirname, '..', 'qa');
const processEvents = [];
app.on('child-process-gone', (_event, details) => processEvents.push(details));
const dialogRequests = [];
const openedFolders = [];
const captures = [];
let selection = null;
dialog.showOpenDialog = async (_window, options) => {
  dialogRequests.push(options);
  return { canceled: !selection, filePaths: selection ? [selection] : [] };
};
shell.openPath = async folder => { openedFolders.push(folder); return ''; };
dialog.showErrorBox = (title, detail) => { throw new Error(`${title}: ${detail}`); };
require('../main.cjs');

async function waitFor(probe, label) {
  const deadline = Date.now() + 90_000;
  while (Date.now() < deadline) {
    if (await probe()) return;
    await new Promise(resolve => setTimeout(resolve, 50));
  }
  throw new Error(`Timed out: ${label}`);
}

async function run() {
  await app.whenReady();
  session.defaultSession.enableNetworkEmulation({ offline: true });
  await fs.mkdir(evidence, { recursive: true });
  const folder = await fs.mkdtemp(path.join(evidence, 'desktop-'));
  const original = await fs.readFile(path.join(__dirname, 'fixtures', 'QA Trio.gp5'));
  const source = path.join(folder, '한글 연습곡.gp5');
  await fs.writeFile(source, original);
  let main;
  await waitFor(() => { main = BrowserWindow.getAllWindows().find(win => win.isVisible()); return Boolean(main); }, 'main window');
  const js = code => main.webContents.executeJavaScript(code, true);
  const screenshot = async name => {
    await js('document.fonts.ready.then(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))))');
    const state = { name, visible: main.isVisible(), focused: main.isFocused(), minimized: main.isMinimized(), bounds: main.getBounds(), gpu: app.getGPUFeatureStatus(), processEvents,
      document: await js(`({ readyState: document.readyState, visibility: document.visibilityState, fonts: document.fonts.status, width: innerWidth, height: innerHeight,
        scrollY, scrollHeight: document.documentElement.scrollHeight, horizontalOverflow: document.documentElement.scrollWidth > innerWidth,
        status: document.getElementById('status').textContent, busy: document.querySelector('main').getAttribute('aria-busy'),
        controls: [...document.querySelectorAll('button')].filter(el => !el.hidden).map(el => ({ id: el.id, text: el.textContent, disabled: el.disabled, height: el.getBoundingClientRect().height })),
        clippedHorizontally: [...document.querySelectorAll('main *')].filter(el => { const r = el.getBoundingClientRect(); return r.width && (r.left < -1 || r.right > innerWidth + 1); }).map(el => el.id || el.className)
      })`) };
    assert.equal(state.document.horizontalOverflow, false);
    assert.deepEqual(state.document.clippedHorizontally, []);
    assert.ok(state.document.controls.every(control => control.height >= 44 && control.text.trim()));
    const bitmap = await main.webContents.capturePage();
    assert.equal(bitmap.isEmpty(), false);
    await fs.writeFile(path.join(evidence, name), bitmap.toPNG());
    captures.push({ ...state, imageSize: bitmap.getSize() });
    console.log('CAPTURE', name);
  };
  const captureState = async name => {
    for (const [width, height, suffix] of [[960, 760, 'default'], [760, 640, 'minimum']]) {
      main.setSize(width, height);
      await js('scrollTo(0, 0)');
      await screenshot(`desktop-${name}-${suffix}.png`);
      if (await js('document.documentElement.scrollHeight > innerHeight + 1')) {
        await js('scrollTo(0, document.documentElement.scrollHeight)');
        await screenshot(`desktop-${name}-${suffix}-bottom.png`);
      }
    }
    main.setSize(960, 760);
    await js('scrollTo(0, 0)');
  };
  await waitFor(() => js("Boolean(document.getElementById('choose'))"), 'UI ready');
  await waitFor(() => js("!document.getElementById('choose').disabled"), 'startup picker cancelled');
  assert.equal(dialogRequests.length, 1);
  assert.deepEqual(dialogRequests[0].filters[0].extensions, ['gp5']);
  await captureState('empty');
  assert.equal(await js("document.getElementById('convert').disabled"), true);
  const accessibility = await js(`({ lang: document.documentElement.lang, headings: document.querySelectorAll('h1').length,
    liveStatus: document.getElementById('status').getAttribute('aria-live'), alertRole: document.getElementById('error').getAttribute('role'),
    progressLabel: document.getElementById('progress').getAttribute('aria-label'), reducedMotion: matchMedia('(prefers-reduced-motion: reduce)').matches })`);
  assert.equal(accessibility.lang, 'ko');
  assert.equal(accessibility.headings, 1);
  assert.equal(accessibility.liveStatus, 'polite');
  assert.equal(accessibility.alertRole, 'alert');
  assert.ok(accessibility.progressLabel);
  main.focus();
  await js('document.activeElement.blur()');
  main.webContents.sendInputEvent({ type: 'keyDown', keyCode: 'Tab' });
  main.webContents.sendInputEvent({ type: 'keyUp', keyCode: 'Tab' });
  await waitFor(() => js("document.activeElement.id === 'choose'"), 'keyboard focus on chooser');
  accessibility.focus = await js("({ style: getComputedStyle(document.activeElement).outlineStyle, width: getComputedStyle(document.activeElement).outlineWidth })");
  assert.equal(accessibility.focus.style, 'solid');
  assert.equal(accessibility.focus.width, '2px');
  await screenshot('desktop-keyboard-focus.png');
  selection = source;
  main.focus();
  main.webContents.focus();
  main.webContents.sendInputEvent({ type: 'keyDown', keyCode: 'Enter' });
  main.webContents.sendInputEvent({ type: 'char', keyCode: 'Enter' });
  main.webContents.sendInputEvent({ type: 'keyUp', keyCode: 'Enter' });
  await waitFor(() => js("document.querySelectorAll('#tracks li').length === 3"), 'track list');
  await captureState('selected');
  const selectedName = await js("document.getElementById('file-name').textContent");
  selection = null;
  await js("document.getElementById('choose').click()");
  await waitFor(() => js("!document.getElementById('choose').disabled"), 'cancel replacement picker');
  assert.equal(await js("document.getElementById('file-name').textContent"), selectedName);
  await js("document.getElementById('convert').click()");
  await waitFor(() => js("document.querySelector('main').getAttribute('aria-busy') === 'true'"), 'busy');
  assert.equal(await js("document.getElementById('choose').disabled"), true);
  await captureState('busy');
  await waitFor(() => js("document.querySelector('main').getAttribute('aria-busy') === 'false'"), 'first conversion');
  assert.equal(await js("document.getElementById('error').hidden"), true, await js("document.getElementById('error').textContent"));
  const first = (await fs.readdir(folder)).filter(file => file.endsWith('.pdf'));
  assert.equal(first.length, 3);
  const hashes = await Promise.all(first.map(async file => createHash('sha256').update(await fs.readFile(path.join(folder, file))).digest('hex')));
  await captureState('complete');
  await js("document.getElementById('open-folder').click()");
  await waitFor(() => openedFolders.length === 1, 'open output folder');
  assert.equal(openedFolders[0], folder);
  await js("document.getElementById('convert').click()");
  await waitFor(() => js("document.querySelector('main').getAttribute('aria-busy') === 'false'"), 'repeat conversion');
  assert.equal((await fs.readdir(folder)).filter(file => file.endsWith('.pdf')).length, 6);
  assert.deepEqual(await Promise.all(first.map(async file => createHash('sha256').update(await fs.readFile(path.join(folder, file))).digest('hex'))), hashes);
  assert.deepEqual(await fs.readFile(source), original);
  const beforeCancel = (await fs.readdir(folder)).filter(file => file.endsWith('.pdf')).length;
  await js("document.getElementById('convert').click(); document.getElementById('cancel').click()");
  await waitFor(() => js("document.querySelector('main').getAttribute('aria-busy') === 'false'"), 'cancel');
  assert.match(await js("document.getElementById('status').textContent"), /취소/);
  assert.equal((await fs.readdir(folder)).filter(file => file.endsWith('.pdf')).length, beforeCancel);
  await captureState('cancelled');
  await js("document.getElementById('convert').click()");
  await waitFor(() => js("[...document.querySelectorAll('.track-state')].some(row => row.textContent === '저장됨')"), 'first completed PDF before cancellation');
  await js("document.getElementById('cancel').click()");
  await waitFor(() => js("document.querySelector('main').getAttribute('aria-busy') === 'false'"), 'partial cancellation');
  const afterPartialCancel = (await fs.readdir(folder)).filter(file => file.endsWith('.pdf')).length;
  assert.ok(afterPartialCancel > beforeCancel && afterPartialCancel < beforeCancel + 3);
  assert.match(await js("document.getElementById('status').textContent"), new RegExp(`완료된 PDF ${afterPartialCancel - beforeCancel}개`));
  await captureState('partial-cancel');
  selection = path.join(folder, 'broken.gp5');
  await fs.writeFile(selection, 'invalid GP5');
  await js("document.getElementById('choose').click()");
  await waitFor(() => js("!document.getElementById('error').hidden"), 'invalid source feedback');
  await captureState('error');
  const afterInvalid = (await fs.readdir(folder)).filter(file => file.endsWith('.pdf')).length;
  assert.equal(afterInvalid, afterPartialCancel);
  selection = source;
  await js("document.getElementById('choose').click()");
  await waitFor(() => js("document.getElementById('error').hidden && !document.getElementById('convert').disabled"), 'retry after malformed file');
  await captureState('recovered');
  assert.equal(await js("typeof require"), 'undefined');
  assert.equal(await js("typeof process"), 'undefined');
  assert.deepEqual(await Promise.all(first.map(async file => createHash('sha256').update(await fs.readFile(path.join(folder, file))).digest('hex'))), hashes);
  assert.deepEqual(await fs.readFile(source), original);
  const report = { passed: true, source, sourceHash: createHash('sha256').update(original).digest('hex'), files: first.map(file => path.join(folder, file)), scenarios: ['automatic startup picker cancellation', 'keyboard choose real GP5', 'cancel replacement picker preserves selection', 'busy guard', '3 actual PDFs while offline', 'repeat no overwrite', 'source unchanged', 'immediate cancel leaves no partial PDF', 'mid-conversion cancel preserves completed PDFs', 'malformed GP5 creates no PDF', 'recover after malformed GP5', 'open output folder target', 'renderer sandbox'], nativeDialogClickTested: false, nativeFolderOpeningTested: false, accessibility, dialogRequests, captures, processEvents };
  await fs.writeFile(path.join(evidence, 'desktop-report.json'), JSON.stringify(report, null, 2));
  console.log(JSON.stringify(report));
}

run().then(() => app.quit(), error => { console.error(error); app.exit(1); });
