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
  const text = `# Revision 4 independent manual QA\n\nVerdict: **${verdict}**. ${rows.length - fails.length}/${rows.length} scenarios passed.\n\n` +
    `Started ${started}; updated ${new Date().toISOString()}; Chrome ${browser?.version() ?? 'not launched'}; Node ${process.version}. Tested ${url} in private disposable contexts.\n\n` +
    `dist/index.html: ${build.length} bytes, SHA-256 \`${hash}\`. Current SHA-256 \`${currentHash}\`. Build stable: **${hash === currentHash}**.\n\n` +
    `Actual Web Audio contexts/nodes run with transparent method forwarding, not an audio replacement. Gain reads wait for a processing quantum. Keyboard checks use real Chrome key events. Checkbox inputs use actual browser label clicks, native checkbox changes and real keyboard Space/Tab. Pulse observations come from live runtime playback; no artificial flash class is applied. Audio scheduling and gain are measured from the running native context. Persisted malformed/legacy data use isolated fixtures. Physical r1 OS keyboard, wheel/button wiring, native storage implementation, speaker/perceived timbre and installation remain unverified. Headless installed Chrome, no new packages or Lighthouse.\n\n` +
    `## Executed scenarios\n\n| # | Scenario | Result | Exact observed values |\n|---|---|---|---|\n` +
    rows.map((row, i) => `| ${i + 1} | ${row.name} | ${row.result} | ${JSON.stringify(row.observed).replaceAll('|', '\\|')} |`).join('\n') +
    `\n\n## Fresh screenshot evidence\n\n` + captures.map(c => `- [${c.file}](./${c.file}): ${c.description}`).join('\n') +
    `\n\n## Failures and reproduction\n\n` + (fails.length ? fails.map(f => `### ${f.name}\n\n${f.error}\n\nObserved: \`${JSON.stringify(f.observed)}\`\n`).join('\n') : 'No scenario failed.\n') +
    `\n## Browser errors\n\n\`\`\`json\n${JSON.stringify(errors, null, 2)}\n\`\`\`\n\n` +
    `## Cleanup and scope\n\n${cleanup ? 'All owned Chrome contexts and the browser were closed.' : 'Browser QA remains active.'} Reused root preview 4173 read-only; no server process was launched or terminated. Only qa/revision-4/manual-* files were created. No product, test, dependency or trader edits. Parent independent visual reviewers must consume these fresh captures for the complete visual gate.\n`;
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

const expectedHash = 'f5576f8abee85e62c294afaf9ca043d7033d1388eef4e46cee31f1f5f3eea39d';
assert.equal(hash, expectedHash);
const checkbox = p => p.locator('#flash-with-sound');
const flashLabel = '\uC18C\uB9AC \uC7AC\uC0DD \uC911\uC5D0\uB3C4 \uD654\uBA74 \uAE5C\uBE61\uC784';
async function muted(p, value) { if ((await p.locator('#mute').getAttribute('aria-pressed') === 'true') !== value) await p.locator('#mute').click(); }
async function setting(p, value) { await nav(p, 'settings'); await checkbox(p).setChecked(value); }
async function configure(p, sub, sound, mute, flash) {
  await nav(p, 'home');
  if (await p.locator('#play').getAttribute('aria-pressed') === 'true') await stop(p);
  await bpm(p, 240); await p.locator('[data-sub="' + sub + '"]').click();
  await nav(p, 'settings'); await p.locator('[data-sound="' + sound + '"]').click();
  await checkbox(p).setChecked(flash); await muted(p, mute); await nav(p, 'home');
}
async function watch(p) {
  await p.evaluate(() => {
    window.__pulseObserver?.disconnect();
    window.__pulses = []; window.__pulsePeaks = []; let prior = false;
    const app = document.querySelector('#app');
    window.__pulseObserver = new MutationObserver(() => {
      const next = app.classList.contains('flash');
      if (next !== prior) {
        window.__pulses.push({ now: performance.now(), flash: next });
        if (next) requestAnimationFrame(() => {
          const s = getComputedStyle(app, '::after');
          window.__pulsePeaks.push({ opacity: s.opacity, duration: s.animationDuration, top: s.top, bottom: s.bottom, layer: s.zIndex, pointer: s.pointerEvents, labelColor: getComputedStyle(document.querySelector('#song-label')).color });
        });
      }
      prior = next;
    }); window.__pulseObserver.observe(app, { attributes: true, attributeFilter: ['class'] });
  });
}
async function pulseData(p) {
  return p.evaluate(() => ({ events: window.__pulses, peaks: window.__pulsePeaks }));
}
async function stored(p) {
  return p.evaluate(() => {
    const value = localStorage.getItem('pulse_metronome_v1');
    return value ? JSON.parse(new TextDecoder().decode(Uint8Array.from(atob(value), c => c.charCodeAt(0)))) : null;
  });
}
async function persistWait(p, value) {
  await p.waitForFunction(value => {
    const encoded = localStorage.getItem('pulse_metronome_v1');
    if (!encoded) return false;
    const decoded = JSON.parse(new TextDecoder().decode(Uint8Array.from(atob(encoded), c => c.charCodeAt(0))));
    return decoded.settings.flashWithSound === value;
  }, value);
}
async function fixture(value) {
  const context = await browser.newContext({ viewport: { width: 240, height: 282 } });
  const encoded = Buffer.from(JSON.stringify(value)).toString('base64');
  await context.addInitScript(encoded => { if (!sessionStorage.getItem('qa-seeded')) { localStorage.setItem('pulse_metronome_v1', encoded); sessionStorage.setItem('qa-seeded', 'yes'); } }, encoded);
  await context.addInitScript(observeAudio);
  const page = await context.newPage(); page.on('pageerror', e => errors.push({ message: e.message, url: page.url() }));
  await page.goto(url); await page.waitForFunction(() => !document.querySelector('#play').disabled);
  return { page, context };
}
try {
  browser = await chromium.launch({ channel: 'chrome', headless: true });
  const main = await fresh(); const p = main.page; recovery = p;
  await check('Default is one native unchecked accessible checkbox', async o => {
    await nav(p, 'settings');
    o.type = await checkbox(p).getAttribute('type'); o.checked = await checkbox(p).isChecked();
    o.count = await p.getByRole('checkbox', { name: flashLabel, exact: true }).count();
    o.label = await p.locator('.flash-option span').textContent();
    assert.equal(o.type, 'checkbox'); assert.equal(o.checked, false); assert.equal(o.count, 1); assert.equal(o.label, flashLabel);
  });
  await check('Settings pane fits240x282 with single-line44px label row', async o => {
    o.layout = await p.evaluate(() => {
      const pane = document.querySelector('#settings'), row = document.querySelector('.flash-option'), span = row.querySelector('span');
      const rect = row.getBoundingClientRect(), text = span.getBoundingClientRect();
      return { docWidth: document.documentElement.scrollWidth, width: document.querySelector('#app').clientWidth, height: document.querySelector('#app').clientHeight, paneHeight: pane.clientHeight, paneScroll: pane.scrollHeight, rowHeight: rect.height, rowBottom: rect.bottom, labelHeight: text.height, lineHeight: Number.parseFloat(getComputedStyle(span).lineHeight), rowWidth: rect.width, labelWidth: text.width };
    });
    assert.equal(o.layout.docWidth, 240); assert.equal(o.layout.width, 240); assert.equal(o.layout.height, 282); assert(o.layout.rowHeight >= 44); assert(o.layout.labelHeight <= o.layout.lineHeight + 1); assert(o.layout.paneScroll <= o.layout.paneHeight); assert(o.layout.rowBottom < 242);
    await shot(p, 'checkbox-default', 'Default native unchecked option; complete settings pane at240x282.');
  });
  await check('Clicking label text checks option without starting paused playback', async o => {
    await p.locator('.flash-option span').click(); o.checked = await checkbox(p).isChecked(); o.running = await p.locator('#play').getAttribute('aria-pressed'); o.flash = await p.locator('#app').evaluate(e => e.classList.contains('flash'));
    assert(o.checked); assert.equal(o.running, 'false'); assert.equal(o.flash, false);
  });
  await check('Real Space toggles checkbox with visible keyboard focus', async o => {
    await checkbox(p).focus(); await p.keyboard.press('Space');
    o.checked = await checkbox(p).isChecked(); o.focus = await checkbox(p).evaluate(e => ({ active: document.activeElement === e, visible: e.matches(':focus-visible'), outline: getComputedStyle(e).outlineStyle, width: getComputedStyle(e).outlineWidth }));
    assert.equal(o.checked, false); assert(o.focus.active && o.focus.visible); assert.equal(o.focus.outline, 'solid'); assert.equal(o.focus.width, '2px'); await shot(p, 'checkbox-focus', 'Native checkbox focused after actual keyboard Space, with2px outline.');
  });
  await check('Real Tab reaches checkbox and next navigation control', async o => {
    await p.locator('[data-sound="melody"]').focus(); await p.keyboard.press('Tab'); o.first = await p.evaluate(() => document.activeElement.id); await p.keyboard.press('Tab'); o.next = await p.evaluate(() => document.activeElement.dataset.page);
    assert.equal(o.first, 'flash-with-sound'); assert.equal(o.next, 'home');
  });
  await check('Checked option stays visually quiet while transport is paused', async o => {
    await setting(p, true); await watch(p); await pause(350); o.pulses = (await pulseData(p)).events; o.running = await p.locator('#play').getAttribute('aria-pressed'); o.contexts = (await audio(p)).contexts.length; assert.equal(o.pulses.length, 0); assert.equal(o.running, 'false'); assert.equal(o.contexts, 0);
  });
  for (const sound of ['drum', 'melody']) for (const mute of [false, true]) for (const flash of [false, true]) {
    await check(sound + ' sound, mute=' + mute + ', flashWithSound=' + flash + ' branch', async o => {
      await configure(p, 1, sound, mute, flash); await watch(p); const first = (await audio(p)).sources.length;
      await play(p); await pause(740); const a = await audio(p); const d = await pulseData(p);
      o.context = a.contexts[0]; o.master = a.gains[0].value; o.pulseOnsets = d.events.filter(e => e.flash).map(e => e.now); o.pitches = a.sources.slice(first).map(n => n.frequencies[0].args[0]); o.checked = await checkbox(p).isChecked();
      assert.equal(o.context.state, 'running'); assert.equal(o.master, mute ? 0 : 1); assert(o.pitches.length >= 3); assert.equal(o.checked, flash);
      if (mute || flash) assert(o.pulseOnsets.length >= 2); else assert.equal(o.pulseOnsets.length, 0);
      await stop(p);
    });
  }
  for (const sub of [1, 2, 3]) {
    await check('Audible checked subdivision' + sub + ' flashes on quarter ticks only', async o => {
      await configure(p, sub, 'melody', false, true); await watch(p); const first = (await audio(p)).sources.length; await play(p); await pause(930);
      const a = await audio(p), d = await pulseData(p); const on = d.events.filter(e => e.flash);
      o.onsets = on.map(e => e.now); o.pulseIntervals = on.slice(1).map((e, i) => e.now - on[i].now); o.audioIntervals = a.sources.slice(first + 1).map((n, i) => n.start[0].args[0] - a.sources[first + i].start[0].args[0]); o.master = a.gains[0].value; o.context = a.contexts[0]; o.peaks = d.peaks;
      assert(o.pulseIntervals.length >= 2); assert(o.pulseIntervals.every(v => v > 185 && v < 315)); assert(o.audioIntervals.every(v => Math.abs(v - 0.25 / sub) < 0.000001)); assert.equal(o.master, 1); assert.equal(o.context.state, 'running');
      assert(o.peaks.some(v => Number(v.opacity) === 0.62)); assert(o.peaks.every(v => v.duration === '0.11s' && v.top === '32px' && v.bottom === '40px' && v.layer === '0' && v.pointer === 'none'));
      if (sub === 3) { await p.waitForFunction(() => document.querySelector('#app').classList.contains('flash') && Number(getComputedStyle(document.querySelector('#app'), '::after').opacity) > 0.6); await shot(p, 'audible-pulse', 'Real running unmuted melody triplets: checked option flashes only at quarter onset.'); }
      await stop(p);
    });
  }
  await check('Toggling checked option retains AudioContext, gain1 and continuous triplet schedule', async o => {
    await configure(p, 3, 'melody', false, false); const first = (await audio(p)).sources.length; await play(p); await pause(150); const before = await audio(p);
    await setting(p, true); await pause(180); await checkbox(p).uncheck(); await pause(180); await checkbox(p).check(); await pause(380);
    const a = await audio(p); const notes = a.sources.slice(first); o.contexts = a.contexts.length; o.beforeTime = before.contexts[0].time; o.afterTime = a.contexts[0].time; o.state = a.contexts[0].state; o.master = a.gains[0].value; o.running = await p.locator('#play').getAttribute('aria-pressed'); o.intervals = notes.slice(1).map((n, i) => n.start[0].args[0] - notes[i].start[0].args[0]); o.cancellations = notes.filter(n => n.stop.length > 1).length;
    assert.equal(o.contexts, 1); assert(o.afterTime > o.beforeTime); assert.equal(o.state, 'running'); assert.equal(o.master, 1); assert.equal(o.running, 'true'); assert(o.intervals.length >= 8); assert(o.intervals.every(v => Math.abs(v - 1 / 12) < 0.000001)); assert.equal(o.cancellations, 0); await stop(p);
  });
  await check('Unchecking during audible pulse clears synchronously without muting', async o => {
    await configure(p, 3, 'drum', false, true); await play(p); await nav(p, 'settings');
    await p.evaluate(() => { window.__clearEvents = []; document.addEventListener('change', e => { if (e.target.id !== 'flash-with-sound') return; const item = { before: document.querySelector('#app').classList.contains('flash'), trusted: e.isTrusted, checked: e.target.checked, started: performance.now() }; window.__clearEvents.push(item); queueMicrotask(() => { item.captureMicrotask = document.querySelector('#app').classList.contains('flash'); }); }, { capture: true }); document.addEventListener('change', e => { if (e.target.id !== 'flash-with-sound') return; const item = window.__clearEvents.at(-1); item.after = document.querySelector('#app').classList.contains('flash'); item.elapsed = performance.now() - item.started; setTimeout(() => { item.nextTask = document.querySelector('#app').classList.contains('flash'); }, 0); }); });
    for (let i = 0; i < 3; i++) {
      await p.waitForFunction(() => document.querySelector('#app').classList.contains('flash')); await checkbox(p).uncheck({ force: true });
      if ((await p.evaluate(() => window.__clearEvents.at(-1))).before) break;
      await checkbox(p).check();
    }
    await pause(25); o.change = await p.evaluate(() => window.__clearEvents.filter(e => !e.checked).at(-1)); const a = await audio(p); o.master = a.gains[0].value; o.state = a.contexts[0].state; o.running = await p.locator('#play').getAttribute('aria-pressed');
    assert(o.change.before && o.change.trusted); assert.equal(o.change.after, false); assert.equal(o.change.nextTask, false); assert(o.change.elapsed < 20); assert.equal(o.master, 1); assert.equal(o.state, 'running'); assert.equal(o.running, 'true'); await stop(p);
  });
  await check('Pause clears checked audible pulse and current beat immediately', async o => {
    await configure(p, 3, 'melody', false, true); await play(p); await p.waitForFunction(() => document.querySelector('#app').classList.contains('flash')); await stop(p);
    o.state = await p.evaluate(() => ({ flash: document.querySelector('#app').classList.contains('flash'), running: document.querySelector('#play').getAttribute('aria-pressed'), playingBeats: document.querySelectorAll('.beats .playing').length, opacity: getComputedStyle(document.querySelector('#app'), '::after').opacity }));
    assert.deepEqual(o.state, { flash: false, running: 'false', playingBeats: 0, opacity: '0' }); await shot(p, 'paused-cleared', 'Stopping audible checked playback clears pulse and current beat.');
  });
  for (const value of [true, false]) {
    await check('Settings persist and reload flashWithSound=' + value, async o => {
      await setting(p, value); await persistWait(p, value); o.saved = (await stored(p)).settings; await p.reload(); await p.waitForFunction(() => !document.querySelector('#play').disabled); await nav(p, 'settings'); o.checked = await checkbox(p).isChecked(); o.mute = await p.locator('#mute').getAttribute('aria-pressed'); assert.equal(o.checked, value); assert.equal(o.saved.flashWithSound, value); assert.equal(o.mute, 'false');
    });
  }
  await check('Saved true and false songs restore option and keep identities', async o => {
    await setting(p, true); await nav(p, 'library'); await p.locator('#song-title').fill('Flash on song'); await p.locator('#save-song').click(); await p.waitForFunction(() => document.querySelectorAll('.song-load').length === 1);
    await setting(p, false); await nav(p, 'library'); await p.locator('#song-title').fill('Flash off song'); await p.locator('#save-song').click(); await p.waitForFunction(() => document.querySelectorAll('.song-load').length === 2);
    o.before = (await stored(p)).songs.map(s => ({ id: s.id, title: s.title, flashWithSound: s.flashWithSound }));
    await p.locator('.song-load').nth(0).click(); await nav(p, 'settings'); o.trueRestored = await checkbox(p).isChecked(); assert.equal(o.trueRestored, true);
    await nav(p, 'library'); await p.locator('.song-load').nth(1).click(); await nav(p, 'settings'); o.falseRestored = await checkbox(p).isChecked(); assert.equal(o.falseRestored, false); await persistWait(p, false);
    o.after = (await stored(p)).songs.map(s => ({ id: s.id, title: s.title, flashWithSound: s.flashWithSound })); assert.deepEqual(o.after, o.before); assert.deepEqual(o.before.map(s => s.flashWithSound), [true, false]); await nav(p, 'library'); await shot(p, 'songs-preserved', 'Two saved songs preserve separate true/false flash preferences and identities.');
  });
  await check('Legacy absent boolean defaults false while preserving old song', async o => {
    const settings = { bpm: 90, subdivision: 3, sound: 'melody', accents: [false, true, false, true], mute: false };
    const song = { ...settings, id: 'legacy-r4-song', title: 'Preserved old song', bpm: 80 };
    const f = await fixture({ settings, songs: [song] }); const q = f.page;
    o.settingsChecked = await checkbox(q).isChecked(); await nav(q, 'library'); await q.locator('.song-load').click(); o.songChecked = await checkbox(q).isChecked(); o.bpm = await q.locator('#bpm').inputValue(); o.accents = await q.locator('[data-beat]').evaluateAll(es => es.map(e => e.getAttribute('aria-pressed'))); await pause(250); o.saved = await stored(q);
    assert.equal(o.settingsChecked, false); assert.equal(o.songChecked, false); assert.equal(o.bpm, '80'); assert.deepEqual(o.accents, ['false', 'true', 'false', 'true']); assert.equal(o.saved.songs[0].id, song.id); assert.equal(o.saved.songs[0].title, song.title); assert.equal(o.saved.settings.flashWithSound, false); assert.equal(o.saved.songs[0].flashWithSound, false); await f.context.close();
  });
  await check('Wrong-type persisted option rejects both settings and song payloads', async o => {
    const base = { bpm: 90, subdivision: 1, sound: 'drum', accents: [true, false, false, false], mute: false, flashWithSound: false }; o.cases = [];
    for (const item of [{ field: 'settings', bad: 'true' }, { field: 'song', bad: 1 }]) {
      const value = { settings: { ...base }, songs: [{ ...base, id: 'bad-bool-song', title: 'Bad bool' }] };
      if (item.field === 'settings') value.settings.flashWithSound = item.bad; else value.songs[0].flashWithSound = item.bad;
      const f = await fixture(value); const q = f.page; await nav(q, 'library');
      const observed = { field: item.field, bad: item.bad, saveDisabled: await q.locator('#save-song').isDisabled(), songCount: await q.locator('.song-load').count(), checked: await checkbox(q).isChecked(), status: await q.locator('#status').textContent(), bpm: await q.locator('#bpm').inputValue() };
      o.cases.push(observed); assert(observed.saveDisabled); assert.equal(observed.songCount, 0); assert.equal(observed.checked, false); assert.equal(observed.bpm, '120'); assert(observed.status.length > 0); await f.context.close();
    }
  });
} finally {
  if (browser) await browser.close(); cleanup = true; await report(true);
}
const result = { verdict: rows.some(r => r.result === 'FAIL') ? 'FAIL' : 'PASS', passed: rows.filter(r => r.result === 'PASS').length, failed: rows.filter(r => r.result === 'FAIL').length, hash, bytes: build.length, captures: captures.length, errors };
console.log(JSON.stringify(result));
process.exitCode = result.failed || errors.length ? 1 : 0;
