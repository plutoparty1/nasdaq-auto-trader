import { chromium } from '@playwright/test';
import assert from 'node:assert/strict';
import { readFile, writeFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';

const root = new URL('../../', import.meta.url);
const output = new URL('./', import.meta.url);
const url = 'http://127.0.0.1:4173/';
const rows = [];
const captures = [];
const errors = [];
const started = new Date().toISOString();
const digest = data => createHash('sha256').update(data).digest('hex');
const build = await readFile(new URL('dist/index.html', root));
const hash = digest(build);
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
let browser;
let recovery;
let cleanup = false;
let legacyCase;

async function report(final = false) {
  const fails = rows.filter(row => row.result === 'FAIL');
  const currentHash = digest(await readFile(new URL('dist/index.html', root)));
  const verdict = final ? fails.length ? 'FAIL' : 'PASS (installed Chrome runtime scope)' : 'WORKING';
  const text = `# Revision 3 independent manual QA\n\nVerdict: **${verdict}**. ${rows.length - fails.length}/${rows.length} scenarios passed.\n\n` +
    `Started ${started}; updated ${new Date().toISOString()}; Chrome ${browser?.version() ?? 'not launched'}; Node ${process.version}. Tested ${url} in private disposable contexts.\n\n` +
    `dist/index.html: ${build.length} bytes, SHA-256 \`${hash}\`. Current SHA-256 \`${currentHash}\`. Build stable: **${hash === currentHash}**.\n\n` +
    `Actual Web Audio contexts/nodes run with transparent method forwarding, not an audio replacement. Gain reads wait for a processing quantum. Keyboard checks use real Chrome key events; mixed paste uses a controlled DOM ClipboardEvent without touching the user clipboard. Tap timestamps come from trusted pointerdown events generated through real Chrome's mouse input API; elapsed time passes on the real clock. These are browser pointer inputs, not physical r1 touches. Slow storage and delayed resume are explicit controlled bridge fault injection. Physical r1 OS keyboard, wheel/button wiring, native storage implementation, speaker/perceived timbre and installation remain unverified. Headless installed Chrome, no new packages or Lighthouse.\n\n` +
    `## Executed scenarios\n\n| # | Scenario | Result | Exact observed values |\n|---|---|---|---|\n` +
    rows.map((row, i) => `| ${i + 1} | ${row.name} | ${row.result} | ${JSON.stringify(row.observed).replaceAll('|', '\\|')} |`).join('\n') +
    `\n\n## Fresh screenshot evidence\n\n` + captures.map(c => `- [${c.file}](./${c.file}): ${c.description}`).join('\n') +
    `\n\n## Failures and reproduction\n\n` + (fails.length ? fails.map(f => `### ${f.name}\n\n${f.error}\n\nObserved: \`${JSON.stringify(f.observed)}\`\n`).join('\n') : 'No scenario failed.\n') +
    `\n## Browser errors\n\n\`\`\`json\n${JSON.stringify(errors, null, 2)}\n\`\`\`\n\n` +
    `## Cleanup and scope\n\n${cleanup ? 'All owned Chrome contexts and the browser were closed.' : 'Browser QA remains active.'} Reused root preview 4173 read-only; no server process was launched or terminated. Only qa/revision-3/manual-* files were created. No product, test, dependency or trader edits. Parent independent visual reviewers must consume these fresh captures for the complete visual gate.\n`;
  await writeFile(new URL('manual-review.md', output), text);
}
async function check(name, action) {
  const observed = {};
  try { await action(observed); rows.push({ name, result: 'PASS', observed }); }
  catch (error) {
    rows.push({ name, result: 'FAIL', observed, error: error.stack });
    if (recovery && !recovery.isClosed()) await recovery.evaluate(() => {
      document.querySelector('[data-page="home"]').click();
      if (document.querySelector('#play').getAttribute('aria-pressed') === 'true') window.dispatchEvent(new Event('sideClick'));
    });
  }
  console.log(JSON.stringify(rows.at(-1))); await report();
}
function observeAudio() {
  const Native = window.AudioContext;
  window.__audio = { contexts: [], gains: [], sources: [], buffers: 0 };
  class Observed extends Native {
    constructor(options) { super(options); window.__audio.contexts.push(this); }
    createGain() {
      const node = super.createGain(); const entry = { node, events: [] }; window.__audio.gains.push(entry);
      for (const method of ['setValueAtTime', 'exponentialRampToValueAtTime']) {
        const native = node.gain[method].bind(node.gain);
        node.gain[method] = (...args) => { entry.events.push({ method, args, at: this.currentTime }); return native(...args); };
      }
      return node;
    }
    createOscillator() {
      const node = super.createOscillator(); const entry = { frequencies: [], start: [], stop: [] }; window.__audio.sources.push(entry);
      for (const method of ['setValueAtTime', 'exponentialRampToValueAtTime']) {
        const native = node.frequency[method].bind(node.frequency);
        node.frequency[method] = (...args) => { entry.frequencies.push({ method, args }); return native(...args); };
      }
      for (const method of ['start', 'stop']) {
        const native = node[method].bind(node);
        node[method] = (...args) => { entry.type = node.type; entry[method].push({ args, at: this.currentTime }); return native(...args); };
      }
      return node;
    }
    createBufferSource() { window.__audio.buffers++; return super.createBufferSource(); }
  }
  window.AudioContext = Observed;
}
async function fresh(init = observeAudio) {
  const context = await browser.newContext({ viewport: { width: 240, height: 282 } });
  if (init) await context.addInitScript(init);
  const page = await context.newPage();
  page.on('pageerror', e => errors.push({ message: e.message, url: page.url() }));
  await page.goto(url); await page.waitForFunction(() => !document.querySelector('#play').disabled);
  return { page, context };
}
const nav = (page, id) => page.locator(`[data-page="${id}"]`).click();
async function bpm(page, value) { await page.locator('#bpm').fill(String(value)); await page.locator('#bpm').press('Enter'); }
async function play(page) { await page.locator('#play').click(); await page.waitForFunction(() => document.querySelector('#play').getAttribute('aria-pressed') === 'true'); }
async function stop(page) { await page.evaluate(() => window.dispatchEvent(new Event('sideClick'))); await page.waitForFunction(() => document.querySelector('#play').getAttribute('aria-pressed') === 'false'); }
const audio = page => page.evaluate(() => ({ contexts: window.__audio.contexts.map(c => ({ state: c.state, time: c.currentTime, sampleRate: c.sampleRate })), sources: window.__audio.sources, buffers: window.__audio.buffers, gains: window.__audio.gains.map(g => ({ value: g.node.gain.value, events: g.events })) }));
async function shot(page, name, description) {
  const file = `manual-${name}.png`;
  await page.screenshot({ path: new URL(file, output).pathname.replace(/^\/(\w:)/, '$1') }); captures.push({ file, description });
}
function watchTaps() {
  window.__taps = [];
  document.querySelector('#tap-pad').addEventListener('pointerdown', event => window.__taps.push({ epoch: performance.timeOrigin + performance.now(), mono: performance.now(), trusted: event.isTrusted, pointer: event.pointerType }), { capture: true });
}
async function tapAt(page, point, target) { if (target) await pause(Math.max(0, target - Date.now())); await page.mouse.click(point.x, point.y); }
const taps = page => page.evaluate(() => window.__taps);
const measured = async page => Number(await page.locator('#tap-pad strong').textContent());

try {
  browser = await chromium.launch({ channel: 'chrome', headless: true });
  const main = await fresh(); const p = main.page; recovery = p;
  await check('Boot, four 240×282 pages and removed controls', async o => {
    o.pages = [];
    for (const page of ['home', 'tap', 'settings', 'library']) {
      await nav(p, page); await shot(p, `240-${page}`, `${page} current Revision 3 page.`);
      const size = await p.locator('#app').evaluate(e => ({ width: e.clientWidth, height: e.clientHeight, docWidth: document.documentElement.scrollWidth }));
      o.pages.push({ page, ...size }); assert.deepEqual(size, { width: 240, height: 282, docWidth: 240 });
    }
    o.removedControls = await p.locator('#volume,#volume-label,#mute-setting,input[type=range],input[type=checkbox]').count(); assert.equal(o.removedControls, 0);
    o.initialTapCaption = await p.locator('#tap-time').textContent(); assert.equal(o.initialTapCaption, '');
    o.settingsText = await p.locator('#settings').textContent(); assert(!o.settingsText.includes('무음 · 화면 박자')); await nav(p, 'home');
  });
  await check('Native wheel reverses direction and clamps boundaries', async o => {
    await bpm(p, 80); await p.evaluate(() => window.dispatchEvent(new Event('scrollUp'))); o.up = await p.locator('#bpm').inputValue();
    await p.evaluate(() => window.dispatchEvent(new Event('scrollDown'))); o.down = await p.locator('#bpm').inputValue();
    await bpm(p, 20); await p.evaluate(() => window.dispatchEvent(new Event('scrollUp'))); o.low = await p.locator('#bpm').inputValue();
    await bpm(p, 300); await p.evaluate(() => window.dispatchEvent(new Event('scrollDown'))); o.high = await p.locator('#bpm').inputValue();
    assert.deepEqual([o.up, o.down, o.low, o.high], ['79', '80', '20', '300']);
  });
  await check('PC wheel, numeric keyboard editing and ignored English/mixed paste', async o => {
    await bpm(p, 80); await p.locator('#home').hover(); await p.mouse.wheel(0, -100); await p.waitForFunction(() => document.querySelector('#bpm').value === '79'); o.up = '79';
    await p.mouse.wheel(0, 100); await p.waitForFunction(() => document.querySelector('#bpm').value === '80'); o.down = '80';
    await p.locator('#plus').focus(); await p.keyboard.press('ArrowUp'); o.arrowUp = await p.locator('#bpm').inputValue();
    await p.locator('#plus').click(); o.plus = await p.locator('#bpm').inputValue(); assert.deepEqual([o.arrowUp, o.plus], ['81', '82']);
    const input = p.locator('#bpm'); o.type = await input.getAttribute('type'); o.inputmode = await input.getAttribute('inputmode'); assert.equal(o.type, 'number'); assert.equal(o.inputmode, 'numeric');
    await input.focus(); await p.keyboard.press('Control+A'); await p.keyboard.press('Backspace'); o.emptyDraft = await input.inputValue(); assert.equal(o.emptyDraft, ''); await p.keyboard.press('Enter'); o.emptyInvalid = await input.getAttribute('aria-invalid'); assert.equal(o.emptyInvalid, 'true'); await shot(p, 'numeric-empty', 'Real Backspace permits an empty draft; commit shows the range error.');
    await input.focus(); await p.keyboard.type('246'); o.threeDigits = await input.inputValue(); assert.equal(o.threeDigits, '246'); await p.keyboard.type('7'); o.fourthDigitIgnored = await input.inputValue(); assert.equal(o.fourthDigitIgnored, '246'); await p.keyboard.press('Enter');
    await bpm(p, 80); await input.focus(); await p.keyboard.press('Control+A'); await p.keyboard.type('eE+-.abc'); o.englishUnchanged = await input.inputValue(); assert.equal(o.englishUnchanged, '80');
    o.mixedPaste = await input.evaluate(e => { const clipboard = new DataTransfer(); clipboard.setData('text', '12a3'); const event = new ClipboardEvent('paste', { clipboardData: clipboard, bubbles: true, cancelable: true }); e.dispatchEvent(event); return { value: e.value, prevented: event.defaultPrevented }; }); assert.equal(o.mixedPaste.value, '80'); assert.equal(o.mixedPaste.prevented, true); await shot(p, 'numeric-english-ignored', 'English/exponent/sign/decimal keys and controlled mixed paste retain80.'); await p.keyboard.press('Enter');
  });
  for (const sound of ['drum', 'melody']) for (const subdivision of [1, 2, 3]) {
    await check(`Actual ${sound} ${subdivision === 1 ? 'quarters' : subdivision === 2 ? 'eighths' : 'triplets'} has only accent and regular sound`, async o => {
      await bpm(p, 240); await p.locator(`[data-sub="${subdivision}"]`).click(); await nav(p, 'settings'); await p.locator(`[data-sound="${sound}"]`).click(); await nav(p, 'home');
      const first = (await audio(p)).sources.length; await play(p); await p.waitForFunction(n => window.__audio.sources.length >= n.first + n.count, { first, count: 4 * subdivision });
      const a = await audio(p); const notes = a.sources.slice(first, first + 4 * subdivision); await stop(p);
      o.context = a.contexts[0]; o.notes = notes; o.buffers = a.buffers; o.pitches = notes.map(n => n.frequencies[0].args[0]);
      assert.equal(o.context.state, 'running'); assert.equal(o.buffers, 0);
      const accent = sound === 'drum' ? 150 : 1320; const regular = sound === 'drum' ? 1000 : 660;
      assert.deepEqual(o.pitches, Array.from({ length: 4 * subdivision }, (_, step) => step % subdivision === 0 && (subdivision > 1 || step === 0) ? accent : regular));
      assert(notes.every(n => n.type === (sound === 'drum' ? 'triangle' : 'sine')));
      if (sound === 'drum') assert.deepEqual(notes[0].frequencies[1].args, [45, notes[0].start[0].args[0] + 0.08]);
      const starts = notes.map(n => n.start[0].args[0]); o.intervals = starts.slice(1).map((t, i) => t - starts[i]); assert(o.intervals.every(t => Math.abs(t - 0.25 / subdivision) < 0.000001));
    });
  }
  await check('All accents off removes accent pitches without muting regular subparts', async o => {
    for (let beat = 0; beat < 4; beat++) if (await p.locator(`[data-beat="${beat}"]`).getAttribute('aria-pressed') === 'true') await p.locator(`[data-beat="${beat}"]`).click(); const first = (await audio(p)).sources.length;
    await play(p); await p.waitForFunction(n => window.__audio.sources.length >= n + 12, first); const a = await audio(p); await stop(p);
    o.pitches = a.sources.slice(first, first + 12).map(n => n.frequencies[0].args[0]); assert(o.pitches.every(n => n === 660));
    o.pressed = await p.locator('[data-beat]').evaluateAll(e => e.map(n => n.getAttribute('aria-pressed'))); assert(o.pressed.every(n => n === 'false')); await p.locator('[data-sub="3"]').click(); o.restoredPreset = await p.locator('[data-beat]').evaluateAll(e => e.map(n => n.getAttribute('aria-pressed'))); assert(o.restoredPreset.every(n => n === 'true'));
  });
  await check('Actual running master is binary mute0/unmute1 only', async o => {
    await play(p); await p.waitForFunction(() => window.__audio.gains[0].node.gain.value === 1); o.before = (await audio(p)).gains[0].value;
    await p.locator('#mute').click(); await p.waitForFunction(() => window.__audio.gains[0].node.gain.value === 0); o.muted = (await audio(p)).gains[0].value;
    await p.locator('#mute').click(); await p.waitForFunction(() => window.__audio.gains[0].node.gain.value === 1); const a = await audio(p); o.unmuted = a.gains[0].value; o.masterEvents = a.gains[0].events;
    assert.deepEqual([o.before, o.muted, o.unmuted], [1, 0, 1]); assert(o.masterEvents.every(e => [0, 1].includes(e.args[0]))); await stop(p);
  });
  await check('Strong quarter-only pulse has orange0.62 peak,110ms and content-only bounds', async o => {
    await bpm(p, 120); await p.locator('#mute').click(); o.restLabelColor = await p.locator('#song-label').evaluate(e => getComputedStyle(e).color); await shot(p, 'pulse-rest', 'Silent mode stopped; no pulse.');
    await p.evaluate(() => {
      window.__pulses = []; window.__animations = []; let flashing = false;
      const app = document.querySelector('#app');
      new MutationObserver(() => { const next = app.classList.contains('flash'); if (next !== flashing) window.__pulses.push({ now: performance.now(), flash: next }); flashing = next; }).observe(app, { attributes: true, attributeFilter: ['class'] });
      app.addEventListener('animationstart', e => window.__animations.push({ kind: 'start', time: performance.now(), elapsed: e.elapsedTime }));
      app.addEventListener('animationend', e => window.__animations.push({ kind: 'end', time: performance.now(), elapsed: e.elapsedTime }));
    });
    const peak = p.evaluate(() => new Promise(resolve => {
      const app = document.querySelector('#app'); const observer = new MutationObserver(() => {
        if (!app.classList.contains('flash')) return;
        requestAnimationFrame(() => { const s = getComputedStyle(app, '::after'); observer.disconnect(); resolve({ opacity: Number(s.opacity), duration: s.animationDuration, color: s.backgroundColor, top: s.top, bottom: s.bottom, layer: s.zIndex, pointer: s.pointerEvents, pageLayer: getComputedStyle(document.querySelector('#home')).zIndex, songLabelColor: getComputedStyle(document.querySelector('#song-label')).color, bpmLabelColor: getComputedStyle(document.querySelector('.tempo-number > span')).color }); });
      }); observer.observe(app, { attributes: true, attributeFilter: ['class'] });
    }));
    await play(p); o.peak = await peak; await p.waitForFunction(() => document.querySelector('#app').classList.contains('flash') && Number(getComputedStyle(document.querySelector('#app'),'::after').opacity) > 0.6);
    await shot(p, 'pulse-mid', 'Actual quarter pulse; orange field sits behind readable controls.');
    await pause(1250); o.events = await p.evaluate(() => ({ pulses: window.__pulses, animations: window.__animations }));
    const on = o.events.pulses.filter(e => e.flash); o.onsetIntervalsMs = on.slice(1).map((e, i) => e.now - on[i].now);
    assert.equal(o.peak.opacity, 0.62); assert.equal(o.peak.duration, '0.11s'); assert.equal(o.peak.color, 'rgb(254, 80, 0)'); assert.deepEqual([o.peak.top, o.peak.bottom, o.peak.layer, o.peak.pointer, o.peak.pageLayer], ['32px', '40px', '0', 'none', '1']);
    assert.equal(o.restLabelColor, 'rgb(183, 188, 196)'); assert.equal(o.peak.songLabelColor, 'rgb(249, 249, 249)'); assert.equal(o.peak.bpmLabelColor, 'rgb(249, 249, 249)');
    assert(o.onsetIntervalsMs.length >= 2); assert(o.onsetIntervalsMs.every(t => t > 400 && t < 650));
    assert(o.events.animations.filter(e => e.kind === 'end').every(e => Math.abs(e.elapsed - 0.11) < 0.000001)); await stop(p); await shot(p, 'pulse-settled', 'Stopping clears orange pulse and current-beat state.');
  });
  await check('Pulse permits live content controls and top mute interaction', async o => {
    await play(p); await p.waitForFunction(() => document.querySelector('#app').classList.contains('flash')); await p.locator('#plus').click(); o.bpm = await p.locator('#bpm').inputValue(); assert.equal(o.bpm, '121');
    await p.locator('#mute').click(); o.mute = await p.locator('#mute').getAttribute('aria-pressed'); assert.equal(o.mute, 'false'); await stop(p);
  });
  await check('Reduced-motion pulse is discrete0.2 behind current beat', async o => {
    await p.emulateMedia({ reducedMotion: 'reduce' }); await p.locator('#mute').click(); await play(p); await p.waitForFunction(() => document.querySelector('#app').classList.contains('flash'));
    o.style = await p.evaluate(() => { const s = getComputedStyle(document.querySelector('#app'), '::after'); return { opacity: s.opacity, animation: s.animationName, playing: document.querySelectorAll('.beats .playing').length }; });
    assert.deepEqual(o.style, { opacity: '0.2', animation: 'none', playing: 1 }); await shot(p, 'reduced-motion', 'Reduced motion discrete orange quarter indication at0.2.'); await stop(p); await p.emulateMedia({ reducedMotion: 'no-preference' }); await p.locator('#mute').click();
  });
  const tapPage = (await fresh()).page; const tapContext = tapPage.context(); recovery = tapPage;
  await nav(tapPage, 'tap'); await tapPage.evaluate(watchTaps); const box = await tapPage.locator('#tap-pad').boundingBox(); const point = { x: box.x + box.width / 2, y: box.y + box.height / 2 }; let target;
  await check('Second real pointer tap displays and auto-applies BPM immediately', async o => {
    await tapAt(tapPage, point); const first = (await taps(tapPage))[0]; target = first.epoch + 750; await tapAt(tapPage, point, target);
    o.taps = await taps(tapPage); o.measured = await measured(tapPage); o.applied = await tapPage.locator('#bpm').inputValue(); o.label = await tapPage.locator('#tap-time').textContent();
    assert(o.taps.every(t => t.trusted && t.pointer === 'mouse')); assert(o.measured >= 78 && o.measured <= 82); assert.equal(o.applied, String(o.measured)); assert.equal(o.label, 'BPM'); await shot(tapPage, 'tap-second', 'Second trusted pointer tap has measured BPM and already applies it.');
  });
  await check('Rolling latest4intervals follows80→120after4newintervals', async o => {
    for (let i = 0; i < 3; i++) { target += 750; await tapAt(tapPage, point, target); }
    o.baseline = await measured(tapPage); o.faster = [];
    for (let i = 0; i < 4; i++) { target += 500; await tapAt(tapPage, point, target); o.faster.push(await measured(tapPage)); }
    o.taps = await taps(tapPage); o.latestIntervals = o.taps.slice(-4).map((t, i) => t.mono - o.taps.slice(-5)[i].mono);
    assert(o.baseline >= 78 && o.baseline <= 82); assert(o.faster.at(-1) >= 118 && o.faster.at(-1) <= 122); assert.equal(await tapPage.locator('#bpm').inputValue(), String(o.faster.at(-1))); await shot(tapPage, 'tap-faster', 'After four new500ms intervals the live estimate is about120BPM.');
  });
  await check('Real-clock pointer tapping continues beyond10seconds', async o => {
    for (let i = 0; i < 11; i++) { target += 500; await tapAt(tapPage, point, target); }
    o.taps = await taps(tapPage); o.elapsedMs = o.taps.at(-1).mono - o.taps[0].mono; o.count = await tapPage.locator('#tap-count').textContent(); o.measured = await measured(tapPage); o.label = await tapPage.locator('#tap-time').textContent();
    assert(o.elapsedMs > 10000); assert.equal(o.count, '20회'); assert(o.measured >= 118 && o.measured <= 122); assert.equal(o.label, 'BPM'); await shot(tapPage, 'tap-past10s', '20 real pointer taps over more than10seconds; measurement remains live.');
  });
  await check('Real gap greater than4seconds starts a fresh one-tap series', async o => {
    await pause(4150); await tapAt(tapPage, point); const all = await taps(tapPage); o.actualGapMs = all.at(-1).mono - all.at(-2).mono; o.count = await tapPage.locator('#tap-count').textContent(); o.pad = await tapPage.locator('#tap-pad strong').textContent(); o.appliedBpm = await tapPage.locator('#bpm').inputValue();
    assert(o.actualGapMs > 4000); assert.equal(o.count, '1회'); assert.equal(o.pad, 'TAP'); assert.equal(await tapPage.locator('#tap-apply').isDisabled(), true); await shot(tapPage, 'tap-gap-reset', 'Gap resets series without reverting last applied tempo.');
  });
  await check('Two trusted pointerdown events less than100ms apart count once', async o => {
    await tapPage.locator('#tap-reset').click(); o.resetCaption = await tapPage.locator('#tap-time').textContent(); assert.equal(o.resetCaption, ''); const before = (await taps(tapPage)).length; await tapPage.mouse.dblclick(point.x, point.y, { delay: 25 });
    o.events = (await taps(tapPage)).slice(before); o.gapMs = o.events[1].mono - o.events[0].mono; o.count = await tapPage.locator('#tap-count').textContent(); assert(o.gapMs < 100); assert.equal(o.count, '1회');
  });
  await check('Fast out-of-range live result displays without changing valid BPM', async o => {
    await tapPage.locator('#tap-reset').click(); const prior = await tapPage.locator('#bpm').inputValue(); await tapAt(tapPage, point); const first = (await taps(tapPage)).at(-1); await tapAt(tapPage, point, first.epoch + 130);
    o.intervalMs = (await taps(tapPage)).at(-1).mono - first.mono; o.result = await measured(tapPage); o.bpm = await tapPage.locator('#bpm').inputValue(); o.prior = prior; o.disabled = await tapPage.locator('#tap-apply').isDisabled(); assert(o.result > 300); assert.equal(o.bpm, prior); assert(o.disabled); await shot(tapPage, 'tap-too-fast', 'Out-of-range result remains visible but is not applied.');
  });
  await check('Slow out-of-range interval under4seconds displays without changing BPM', async o => {
    await tapPage.locator('#tap-reset').click(); const prior = await tapPage.locator('#bpm').inputValue(); await tapAt(tapPage, point); const first = (await taps(tapPage)).at(-1); await tapAt(tapPage, point, first.epoch + 3500);
    o.intervalMs = (await taps(tapPage)).at(-1).mono - first.mono; o.result = await measured(tapPage); o.bpm = await tapPage.locator('#bpm').inputValue(); assert(o.intervalMs < 4000 && o.result < 20); assert.equal(o.bpm, prior); await shot(tapPage, 'tap-too-slow', '17BPM result remains visible while last valid tempo is retained.');
  });
  await tapContext.close(); recovery = p;
  await check('Legacyvolume0 migrates without muting and preserves song identity', async o => {
    legacyCase = await fresh(); const p = legacyCase.page;
    const settings = { bpm: 90, subdivision: 3, sound: 'melody', accents: [false, true, false, true], mute: false, volume: 0 };
    const song = { ...settings, bpm: 80, id: 'revision2-preserved-song', title: '기존 노래 music1' }; const encoded = Buffer.from(JSON.stringify({ settings, songs: [song] })).toString('base64');
    await p.evaluate(v => localStorage.setItem('pulse_metronome_v1', v), encoded); await p.reload(); await p.waitForFunction(() => !document.querySelector('#play').disabled); o.reloadBpm = await p.locator('#bpm').inputValue(); await play(p); await p.waitForFunction(() => window.__audio.gains[0].node.gain.value === 1); o.settingsMaster = (await audio(p)).gains[0].value; await stop(p);
    await nav(p, 'library'); await p.locator('.song-load').click(); o.songBpm = await p.locator('#bpm').inputValue(); o.restoredAccents = await p.locator('[data-beat]').evaluateAll(e => e.map(n => n.getAttribute('aria-pressed'))); assert.deepEqual(o.restoredAccents, ['false', 'true', 'false', 'true']); await play(p); await p.waitForFunction(() => window.__audio.gains[0].node.gain.value === 1); o.songMaster = (await audio(p)).gains[0].value; await stop(p); await pause(250);
    o.saved = await p.evaluate(() => JSON.parse(new TextDecoder().decode(Uint8Array.from(atob(localStorage.getItem('pulse_metronome_v1')), c => c.charCodeAt(0))))); assert.equal(o.saved.songs[0].id, song.id); assert.equal(o.saved.songs[0].title, song.title); assert(!('volume' in o.saved.settings) && !('volume' in o.saved.songs[0])); assert.deepEqual([o.reloadBpm, o.songBpm, o.settingsMaster, o.songMaster], ['90', '80', 1, 1]); await nav(p, 'library'); await shot(p, 'legacy-song', 'Legacy saved song identity and full Unicode title retained.');
  });
  await check('Slow native writes serialize save/currentsettings/delete and reload', async o => {
    const context = await browser.newContext({ viewport: { width: 240, height: 282 } }); const saved = new Map(); const writes = []; let active = 0; let peak = 0;
    await context.exposeFunction('qaRead', key => saved.get(key) ?? null); await context.exposeFunction('qaWrite', async (key, value) => { active++; peak = Math.max(peak, active); writes.push(JSON.parse(Buffer.from(value, 'base64').toString('utf8'))); await pause(400); saved.set(key, value); active--; });
    await context.addInitScript(() => { window.creationStorage = { plain: { getItem: key => window.qaRead(key), setItem: (key, value) => window.qaWrite(key, value) } }; });
    const n = await context.newPage(); await n.goto(url); await n.waitForFunction(() => !document.querySelector('#play').disabled); await bpm(n, 80); await nav(n, 'library'); await n.locator('#song-title').fill('느린 새 곡'); await n.locator('#save-song').click(); o.busy = await n.locator('#save-song').isDisabled(); await shot(n, 'slow-save', 'Native bridge400ms write disables conflicting song actions.'); await nav(n, 'home'); await bpm(n, 140); await pause(1400); o.afterSave = JSON.parse(Buffer.from(saved.get('pulse_metronome_v1'), 'base64').toString('utf8')); assert.equal(o.afterSave.settings.bpm, 140); assert.equal(o.afterSave.songs[0].bpm, 80);
    await nav(n, 'library'); await n.locator('.song-delete').click(); await n.locator('.song-delete').click(); await nav(n, 'home'); await bpm(n, 160); await pause(1400); await n.reload(); await n.waitForFunction(() => !document.querySelector('#play').disabled); o.reloadBpm = await n.locator('#bpm').inputValue(); o.final = JSON.parse(Buffer.from(saved.get('pulse_metronome_v1'), 'base64').toString('utf8')); o.peakWrites = peak; o.writes = writes; o.localStorage = await n.evaluate(() => localStorage.length); assert.equal(peak, 1); assert.equal(o.final.songs.length, 0); assert.equal(o.reloadBpm, '160'); assert.equal(o.localStorage, 0); await context.close();
  });
  await check('Real delayed resume cancels stale start; pagehide stops fresh playback', async o => {
    const d = await fresh(() => { const real = new AudioContext(); window.__real = real; window.__release = []; window.__resumes = 0; const resume = real.resume.bind(real); real.resume = async () => { window.__resumes++; await resume(); await new Promise(r => window.__release.push(r)); }; window.AudioContext = class { constructor() { return real; } }; });
    await d.page.evaluate(() => window.__real.suspend()); await d.page.locator('#plus').click(); await d.page.evaluate(() => window.dispatchEvent(new Event('sideClick'))); await d.page.waitForFunction(() => window.__release.length === 1); o.pending = await d.page.locator('#play').textContent(); await d.page.evaluate(() => { window.dispatchEvent(new Event('sideClick')); window.__release.splice(0).forEach(r => r()); }); await pause(100); o.stale = await d.page.locator('#play').getAttribute('aria-pressed'); assert.equal(o.stale, 'false'); await d.page.evaluate(() => window.dispatchEvent(new Event('sideClick'))); await d.page.waitForFunction(() => document.querySelector('#play').getAttribute('aria-pressed') === 'true'); await d.page.evaluate(() => window.dispatchEvent(new Event('pagehide'))); o.pagehide = await d.page.locator('#play').getAttribute('aria-pressed'); o.resumes = await d.page.evaluate(() => window.__resumes); assert.equal(o.pagehide, 'false'); assert.equal(o.resumes, 1); await d.context.close();
  });
  await check('Literal HTML title cannot inject DOM and deletion retains other song identity', async o => {
    const p = legacyCase.page;
    await nav(p, 'library'); const title = '<img src=x onerror=alert(1)>'; await p.locator('#song-title').fill(title); await p.locator('#save-song').click(); await p.waitForFunction(() => !document.querySelector('#save-song').disabled); o.images = await p.locator('#song-list img').count(); o.count = await p.locator('.song-load').count(); o.names = await p.locator('.song-load').evaluateAll(e => e.map(n => n.getAttribute('aria-label'))); assert.equal(o.images, 0); assert.equal(o.count, 2); assert(o.names.some(n => n.includes(title))); await shot(p, 'literal-html-title', 'HTML-looking title rendered as text, alongside retained legacy song.'); await p.locator('.song-delete').nth(1).click(); o.afterFirst = await p.locator('.song-load').count(); assert.equal(o.afterFirst, 2); await p.locator('.song-delete').nth(1).click(); await p.waitForFunction(() => document.querySelectorAll('.song-load').length === 1); o.remaining = await p.locator('.song-load').textContent(); assert(o.remaining.includes('기존 노래 music1'));
  });
  await main.context.close();
} catch (error) { rows.push({ name: 'Driver setup/execution', result: 'FAIL', observed: {}, error: error.stack }); console.error(error); }
finally { if (browser) await browser.close(); cleanup = true; await report(true); process.exitCode = rows.some(r => r.result === 'FAIL') ? 1 : 0; }
