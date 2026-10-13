const { app, BrowserWindow, dialog, session, shell } = require('electron');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const { createHash } = require('node:crypto');
const { makeKoreanGp5 } = require('./fixtures/korean-score.cjs');
const { parseGp5 } = require('../import-score.cjs');

const evidence = path.join(__dirname, '..', 'qa');
const captures = [];
const runs = [];
const processEvents = [];
let selection = null;
let dialogCount = 0;
app.setPath('userData', path.join(evidence, 'korean-selection-profile'));
app.on('child-process-gone', (_event, details) => processEvents.push(details));
dialog.showOpenDialog = async () => {
  dialogCount += 1;
  return { canceled: !selection, filePaths: selection ? [selection] : [] };
};
dialog.showErrorBox = (title, detail) => { throw new Error(`${title}: ${detail}`); };
shell.openPath = async () => '';
require('../main.cjs');

async function waitFor(probe, label) {
  const deadline = Date.now() + 60_000;
  while (Date.now() < deadline) {
    if (await probe()) return;
    await new Promise(resolve => setTimeout(resolve, 30));
  }
  throw new Error(`Timed out: ${label}`);
}

const hash = bytes => createHash('sha256').update(bytes).digest('hex');
const pdfNames = async folder => (await fs.readdir(folder)).filter(name => name.endsWith('.pdf')).sort();

async function run() {
  await app.whenReady();
  session.defaultSession.enableNetworkEmulation({ offline: true });
  const folder = await fs.mkdtemp(path.join(evidence, 'korean-selection-run-'));
  let main;
  await waitFor(() => { main = BrowserWindow.getAllWindows().find(win => win.isVisible()); return Boolean(main); }, 'main window');
  main.webContents.setBackgroundThrottling(false);
  const js = code => main.webContents.executeJavaScript(code, true);
  const selected = () => js("[...document.querySelectorAll('.track-check:checked')].map(el => Number(el.value))");
  const states = () => js("[...document.querySelectorAll('.track-state')].map(el => el.textContent)");
  const idle = () => waitFor(() => js("document.querySelector('main').getAttribute('aria-busy') === 'false'"), 'conversion settled');
  const screenshot = async name => {
    main.show();
    main.focus();
    main.webContents.focus();
    await js('document.fonts.ready.then(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))))');
    const metrics = await js(`({ width: innerWidth, height: innerHeight, scrollY,
      overflow: document.documentElement.scrollWidth > innerWidth, text: document.body.innerText,
      count: document.getElementById('track-count').textContent, progressMax: document.getElementById('progress').max,
      busy: document.querySelector('main').getAttribute('aria-busy'),
      targets: [...document.querySelectorAll('.track-option,.select-all,button')].filter(el => el.getBoundingClientRect().width).map(el => ({text:el.textContent,height:el.getBoundingClientRect().height})),
      clipped: [...document.querySelectorAll('main *')].filter(el => { const r=el.getBoundingClientRect(); return r.width && (r.left < -1 || r.right > innerWidth + 1); }).map(el => el.id || el.className) })`);
    assert.equal(metrics.overflow, false);
    assert.deepEqual(metrics.clipped, []);
    assert.ok(metrics.targets.every(target => target.height >= 44));
    assert.equal(metrics.text.includes('\ufffd'), false);
    const image = await main.webContents.capturePage();
    assert.equal(image.isEmpty(), false);
    const filename = `korean-selection-${name}.png`;
    await fs.writeFile(path.join(evidence, filename), image.toPNG());
    captures.push({ filename, window: main.getSize(), metrics });
    console.log('CAPTURE', filename);
  };
  const captureState = async name => {
    for (const [width, height, suffix] of [[960, 760, 'default'], [760, 640, 'minimum']]) {
      main.setSize(width, height);
      await js('scrollTo(0,0)');
      await screenshot(`${name}-${suffix}`);
      if (await js('document.documentElement.scrollHeight > innerHeight + 1')) {
        await js('scrollTo(0,document.documentElement.scrollHeight)');
        await screenshot(`${name}-${suffix}-bottom`);
      }
    }
    main.setSize(960, 760);
    await js('scrollTo(0,0)');
  };
  await waitFor(() => js("Boolean(document.getElementById('choose')) && !document.getElementById('choose').disabled"), 'startup chooser cancellation');
  assert.equal(dialogCount, 1);
  await js('window.__qaEvents=[]; window.gp5.onProgress(event => window.__qaEvents.push(event)); true');
  for (const encoding of ['euc-kr', 'utf-8']) {
    console.log('SCENARIO', encoding);
    const fixture = makeKoreanGp5(encoding, { trackNames: ['리드 기타 뷁', '베이스', '드럼'] });
    const outputFolder = path.join(folder, encoding);
    await fs.mkdir(outputFolder);
    const source = path.join(outputFolder, '한글 악보 뷁.gp5');
    await fs.writeFile(source, fixture.bytes);
    const metadata = parseGp5(fixture.bytes, path.basename(source));
    assert.equal(metadata.encoding, encoding);
    assert.equal(metadata.title, fixture.title);
    assert.deepEqual(metadata.trackNames, fixture.trackNames);
    selection = source;
    await js("document.getElementById('choose').click()");
    await waitFor(() => js("document.querySelectorAll('.track-check').length === 3 && !document.getElementById('choose').disabled"), 'Korean track list');
    assert.deepEqual(await js("[...document.querySelectorAll('.track-name')].map(el => el.textContent)"), fixture.trackNames);
    assert.deepEqual(await selected(), [0, 1, 2]);
    assert.equal(await js("document.getElementById('select-all').checked"), true);
    await captureState(`${encoding}-all`);
    await js("document.getElementById('select-all').click()");
    assert.deepEqual(await selected(), []);
    assert.equal(await js("document.getElementById('convert').disabled"), true);
    for (const invalid of [[], [-1], [3], [0, 0], [0, '2'], null]) {
      const result = await js(`window.gp5.convert(${JSON.stringify(invalid)})`);
      assert.ok(result.error);
      assert.deepEqual(result.files, []);
    }
    assert.deepEqual(await pdfNames(outputFolder), []);
    await captureState(`${encoding}-empty`);
    await js("document.getElementById('select-all').click(); document.getElementById('select-all').focus()");
    for (let index = 0; index < 2; index += 1) {
      main.webContents.sendInputEvent({ type: 'keyDown', keyCode: 'Tab' });
      main.webContents.sendInputEvent({ type: 'keyUp', keyCode: 'Tab' });
    }
    await waitFor(() => js("document.activeElement.className === 'track-check' && document.activeElement.value === '1'"), 'keyboard focus on bass checkbox');
    assert.equal(await js('getComputedStyle(document.activeElement).outlineWidth'), '2px');
    main.webContents.sendInputEvent({ type: 'keyDown', keyCode: 'Space' });
    main.webContents.sendInputEvent({ type: 'char', keyCode: 'Space' });
    main.webContents.sendInputEvent({ type: 'keyUp', keyCode: 'Space' });
    await waitFor(async () => JSON.stringify(await selected()) === '[0,2]', 'keyboard subset selection');
    assert.equal(await js("document.getElementById('select-all').indeterminate"), true);
    assert.equal(await js("document.getElementById('track-count').textContent"), '2/3개 선택');
    await captureState(`${encoding}-subset-focus`);
    selection = null;
    await js("document.getElementById('choose').click()");
    await waitFor(() => js("!document.getElementById('choose').disabled"), 'cancelled replacement');
    assert.deepEqual(await selected(), [0, 2]);
    await js("window.__qaEvents=[]; document.getElementById('convert').click()");
    assert.equal(await js("[...document.querySelectorAll('.track-check,#select-all,#choose,#convert,#open-folder')].every(el => el.disabled)"), true);
    assert.equal(await js("document.getElementById('cancel').hidden || document.getElementById('cancel').disabled"), false);
    assert.equal(await js("document.getElementById('progress').max"), 2);
    assert.equal((await js('window.gp5.convert([1])')).files.length, 0);
    assert.equal((await states())[1], '선택 안 함');
    await captureState(`${encoding}-busy`);
    await idle();
    assert.equal(await js("document.getElementById('error').hidden"), true, await js("document.getElementById('error').textContent"));
    assert.deepEqual(await states(), ['저장됨', '선택 안 함', '저장됨']);
    const files = await pdfNames(outputFolder);
    assert.equal(files.length, 2);
    assert.ok(files[0].includes(' - 01 - 리드 기타 뷁'));
    assert.ok(files[1].includes(' - 03 - 드럼'));
    assert.ok(files.every(file => !file.includes(' - 02 - ')));
    const events = await js('window.__qaEvents');
    assert.deepEqual(events.filter(event => event.status === 'saved').map(event => event.trackIndex), [0, 2]);
    assert.ok(events.every(event => event.total === 2 && [0, 2].includes(event.trackIndex)));
    assert.equal(await js("document.getElementById('progress').value"), 2);
    await captureState(`${encoding}-complete`);
    const hashes = await Promise.all(files.map(async file => hash(await fs.readFile(path.join(outputFolder, file)))));
    await js("document.getElementById('convert').click()");
    await idle();
    assert.equal((await pdfNames(outputFolder)).length, 4);
    await js("document.getElementById('convert').click(); document.getElementById('cancel').click()");
    await idle();
    assert.equal((await pdfNames(outputFolder)).length, 4);
    await js("document.getElementById('convert').click()");
    await waitFor(() => js("document.querySelector('.track-state').textContent === '저장됨'"), 'first subset PDF saved');
    await js("document.getElementById('cancel').click()");
    await idle();
    assert.equal((await pdfNames(outputFolder)).length, 5);
    assert.deepEqual(await states(), ['저장됨', '선택 안 함', '미완료']);
    assert.match(await js("document.getElementById('status').textContent"), /완료된 PDF 1개/);
    await captureState(`${encoding}-partial-cancel`);
    assert.deepEqual(await Promise.all(files.map(async file => hash(await fs.readFile(path.join(outputFolder, file))))), hashes);
    assert.deepEqual(await fs.readFile(source), fixture.bytes);
    runs.push({ encoding, source, sourceHash: hash(fixture.bytes), title: fixture.title, trackNames: fixture.trackNames, beatText: fixture.beatText, files: files.map(file => path.join(outputFolder, file)), events, totalPdfs: 5 });
  }
  assert.deepEqual(processEvents, []);
  const report = { passed: true, runs, captures, dialogCount, nativeChooserIntercepted: true, folderOpeningIntercepted: true, offline: true, processEvents };
  await fs.writeFile(path.join(evidence, 'korean-selection-report.json'), JSON.stringify(report, null, 2));
  console.log(JSON.stringify({ passed: true, encodings: runs.map(run => run.encoding), captures: captures.length, files: runs.flatMap(run => run.files) }));
}

run().then(() => app.quit(), error => { console.error(error); app.exit(1); });
