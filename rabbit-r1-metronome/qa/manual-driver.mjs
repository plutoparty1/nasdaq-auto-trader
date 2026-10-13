import { chromium } from '@playwright/test';
import { spawn } from 'node:child_process';
import { readFile, writeFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { pathToFileURL } from 'node:url';
import assert from 'node:assert/strict';

const root = new URL('../', import.meta.url);
const url = 'http://127.0.0.1:4186/';
const rows = [];
const captures = [];
const consoleErrors = [];
const built = await readFile(new URL('dist/index.html', root));
const hash = createHash('sha256').update(built).digest('hex');
const server = spawn(process.execPath, ['scripts/serve.mjs'], {
  cwd: root, env: { ...process.env, PULSE_PORT: '4186' }, windowsHide: true,
  stdio: ['ignore', 'pipe', 'pipe'],
});
let browser;
let recoveryPage;
const started = new Date().toISOString();
const brief = value => JSON.stringify(value).replaceAll('|', '\\|');
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
const round = value => Number(value.toFixed(6));

async function report(final = false) {
  const failed = rows.filter(row => row.result === 'FAIL');
  const status = final ? failed.length ? 'FAIL' : 'PASS (desktop browser scope)' : 'WORKING';
  const currentHash = createHash('sha256').update(await readFile(new URL('dist/index.html', root))).digest('hex');
  const text = `# PULSE independent manual runtime QA\n\nVerdict: **${status}**. ${rows.length - failed.length}/${rows.length} completed scenarios passed.\n\n` +
    `Started: ${started}. Report generated: ${new Date().toISOString()}. Node: ${process.version}. Chrome: ${browser?.version() ?? 'not launched'}. Test URL: ${url}.\n\n` +
    `Tested dist/index.html SHA-256: \`${hash}\`. Current SHA-256: \`${currentHash}\`. Build stable during run: **${hash === currentHash}**.\n\n` +
    `## Evidence method and limits\n\nInstalled Chrome is driven by Playwright in an isolated disposable browser context. Actual Web Audio constructors and nodes execute; transparent method forwarding records source starts/stops, frequencies and gain automation. Audio output waveform, perceived timbre, physical r1 timing, wheel/button hardware, native storage implementation, installation and speaker output are not certified. The resumed-audio delay, missing AudioContext and asynchronous native-storage bridge are controlled fault injection, clearly identified per scenario. Browser uses headless installed Chrome; rendered screenshots are fresh captures of this build. The parent-level independent visual reviewers must consume these captures before claiming the complete visual gate.\n\n` +
    `## Scenario results\n\n| # | Scenario | Result | Exact observed values / evidence |\n|---|---|---|---|\n` +
    rows.map((r, i) => `| ${i + 1} | ${r.name} | ${r.result} | ${brief(r.observed)} |`).join('\n') +
    `\n\n## Screenshot evidence\n\n` + captures.map(c => `- [${c.name}](./${c.file}): ${c.description}`).join('\n') +
    `\n\n## Failures and reproduction\n\n` + (failed.length ? failed.map(r => `### ${r.name}\n\n${r.error}\n\nObserved: \`${brief(r.observed)}\`\n`).join('\n') : 'No completed scenario failed.\n') +
    `\n## Browser errors\n\n\`\`\`json\n${JSON.stringify(consoleErrors, null, 2)}\n\`\`\`\n\n` +
    `## Artifact and process ledger\n\nWrites were limited to qa/manual-review.md, qa/manual-driver.mjs, and listed qa/manual-*.png screenshots. No product/test edits. Owned preview child PID: ${server.pid}. Cleanup status: ${final ? 'browser/context closure and owned child termination executed in finally' : 'execution active'}. Root port 4173 was untouched.\n`;
  await writeFile(new URL('qa/manual-review.md', root), text);
}

async function scenario(name, run) {
  let observed = {};
  try {
    observed = await run();
    rows.push({ name, result: 'PASS', observed });
  } catch (error) {
    rows.push({ name, result: 'FAIL', observed, error: error.stack });
    if (recoveryPage && !recoveryPage.isClosed()) await recoveryPage.evaluate(() => {
      document.querySelector('[data-page="home"]').click();
      if (document.querySelector('#play').getAttribute('aria-pressed') === 'true') window.dispatchEvent(new Event('sideClick'));
    });
  }
  console.log(JSON.stringify(rows.at(-1)));
  await report();
}

function audioObserver() {
  const Native = window.AudioContext || window.webkitAudioContext;
  window.__audio = { contexts: [], sources: [], gains: [], events: [] };
  if (!Native) return;
  class ObservedAudioContext extends Native {
    constructor(options) {
      super(options);
      window.__audio.contexts.push(this);
    }
    createGain() {
      const gain = super.createGain();
      const entry = { id: window.__audio.gains.length, node: gain, events: [] };
      window.__audio.gains.push(entry);
      for (const method of ['setValueAtTime', 'exponentialRampToValueAtTime']) {
        const original = gain.gain[method].bind(gain.gain);
        gain.gain[method] = (...args) => {
          entry.events.push({ method, args, at: this.currentTime });
          return original(...args);
        };
      }
      return gain;
    }
    observeSource(source, kind) {
      const entry = { id: window.__audio.sources.length, kind, frequency: [], start: [], stop: [], ended: false };
      window.__audio.sources.push(entry);
      for (const method of ['start', 'stop']) {
        const original = source[method].bind(source);
        source[method] = (...args) => {
          entry[method].push({ args, at: this.currentTime });
          return original(...args);
        };
      }
      if (source.frequency) {
        for (const method of ['setValueAtTime', 'exponentialRampToValueAtTime']) {
          const original = source.frequency[method].bind(source.frequency);
          source.frequency[method] = (...args) => {
            entry.frequency.push({ method, args });
            return original(...args);
          };
        }
      }
      source.addEventListener('ended', () => { entry.ended = true; });
      return source;
    }
    createOscillator() { return this.observeSource(super.createOscillator(), 'oscillator'); }
    createBufferSource() { return this.observeSource(super.createBufferSource(), 'buffer'); }
  }
  window.AudioContext = ObservedAudioContext;
  window.webkitAudioContext = undefined;
}

async function fresh(options = {}, init) {
  const context = await browser.newContext({ viewport: { width: 240, height: 282 }, ...options });
  if (init) await context.addInitScript(init);
  const page = await context.newPage();
  page.on('pageerror', e => consoleErrors.push({ type: 'pageerror', message: e.message, page: page.url() }));
  page.on('console', m => { if (m.type() === 'error') consoleErrors.push({ type: 'console', message: m.text(), page: page.url() }); });
  await page.goto(url);
  await page.locator('#play').waitFor({ state: 'visible' });
  await page.waitForFunction(() => !document.querySelector('#play').disabled);
  return { context, page };
}
const nav = (page, id) => page.locator(`[data-page="${id}"]`).click();
async function bpm(page, value) { await page.locator('#bpm').fill(String(value)); await page.locator('#bpm').press('Enter'); }
async function play(page) { await page.locator('#play').click(); await page.waitForFunction(() => document.querySelector('#play').getAttribute('aria-pressed') === 'true'); }
async function stop(page) { await page.evaluate(() => window.dispatchEvent(new Event('sideClick'))); await page.waitForFunction(() => document.querySelector('#play').getAttribute('aria-pressed') === 'false'); }
async function shot(page, name, description) {
  const file = `manual-${name}.png`;
  await page.screenshot({ path: new URL(`qa/${file}`, root).pathname.replace(/^\/(\w:)/, '$1'), fullPage: true });
  captures.push({ name, file, description });
}
const audio = page => page.evaluate(() => ({
  states: window.__audio.contexts.map(c => ({ state: c.state, currentTime: c.currentTime, sampleRate: c.sampleRate })),
  sources: window.__audio.sources,
  gains: window.__audio.gains.map(g => ({ id: g.id, value: g.node.gain.value, events: g.events })),
}));

try {
  await new Promise((resolve, reject) => {
    server.stdout.once('data', resolve);
    server.once('error', reject);
    server.once('exit', code => reject(new Error(`owned server exited ${code}`)));
  });
  browser = await chromium.launch({ channel: 'chrome', headless: true });
  const { page, context } = await fresh({}, audioObserver);
  recoveryPage = page;
  await scenario('Real Chrome corrected single-file HTTP boot', async () => {
    const external = await page.evaluate(() => performance.getEntriesByType('resource').map(r => r.name));
    assert.equal(await page.locator('#bpm').inputValue(), '120');
    assert.equal(consoleErrors.length, 0);
    return { bpm: 120, resourceRequests: external, playEnabled: await page.locator('#play').isEnabled() };
  });
  await scenario('Real AudioContext quarter-note scheduling and accented drum frequencies', async () => {
    await bpm(page, 240); await play(page);
    await page.waitForFunction(() => window.__audio.sources.length >= 5);
    const a = await audio(page); await stop(page);
    const sources = a.sources.slice(0, 5);
    const times = sources.map(s => s.start[0].args[0]);
    const intervals = times.slice(1).map((t, i) => round(t - times[i]));
    assert(intervals.every(x => x === 0.25));
    assert.equal(sources[0].frequency[0].args[0], 150);
    assert.equal(sources[1].frequency[0].args[0], 1000);
    assert.equal(sources[4].frequency[0].args[0], 150);
    assert.equal(a.states[0].state, 'running');
    return { contexts: a.states, starts: times, intervals, frequencies: sources.map(s => s.frequency), master: a.gains[0].value };
  });
  await scenario('All four accents off keeps audible regular beats', async () => {
    await page.locator('[data-beat="0"]').click();
    const start = (await audio(page)).sources.length;
    await play(page); await page.waitForFunction(n => window.__audio.sources.length >= n + 5, start);
    const a = await audio(page); await stop(page);
    const sources = a.sources.slice(start, start + 5);
    assert(sources.every(s => s.frequency[0].args[0] === 1000));
    const pressed = await page.locator('[data-beat]').evaluateAll(e => e.map(x => x.getAttribute('aria-pressed')));
    assert(pressed.every(p => p === 'false'));
    await shot(page, 'all-accents-off', 'Regular beats remain available when every accent is disabled.');
    return { pressed, pitches: sources.map(s => s.frequency[0].args[0]) };
  });
  await scenario('Actual eighth-note drum subdivision uses noise sources', async () => {
    await page.locator('[data-sub="2"]').click();
    const start = (await audio(page)).sources.length;
    await play(page); await page.waitForFunction(n => window.__audio.sources.length >= n + 8, start);
    const a = await audio(page); await stop(page);
    const sources = a.sources.slice(start, start + 8);
    const kinds = sources.map(s => s.kind);
    assert.deepEqual(kinds, ['oscillator', 'buffer', 'oscillator', 'buffer', 'oscillator', 'buffer', 'oscillator', 'buffer']);
    const times = sources.map(s => s.start[0].args[0]);
    assert(times.slice(1).every((t, i) => Math.abs(t - times[i] - 0.125) < 0.000001));
    return { kinds, starts: times, scheduledInterval: 0.125 };
  });
  await scenario('Actual triplet melody frequencies cover a full four-beat bar', async () => {
    await page.locator('[data-sub="3"]').click(); await nav(page, 'settings');
    await page.locator('[data-sound="melody"]').click(); await nav(page, 'home');
    const start = (await audio(page)).sources.length;
    await play(page); await page.waitForFunction(n => window.__audio.sources.length >= n + 12, start);
    await shot(page, 'triplet-playing', 'Triplet playback with one current beat and subdivision marker.');
    const a = await audio(page); await stop(page);
    const sources = a.sources.slice(start, start + 12);
    const frequencies = sources.map(s => s.frequency[0].args[0]);
    assert.deepEqual(frequencies, [523.25, 261.625, 261.625, 659.25, 329.625, 329.625, 783.99, 391.995, 391.995, 659.25, 329.625, 329.625]);
    const times = sources.map(s => s.start[0].args[0]);
    assert(times.slice(1).every((t, i) => Math.abs(t - times[i] - 1 / 12) < 0.000001));
    return { frequencies, starts: times, intervals: times.slice(1).map((t, i) => round(t - times[i])) };
  });
  await scenario('Master mute applies immediately while visual beats continue', async () => {
    await play(page); await page.locator('#mute').click();
    const immediate = await audio(page);
    const last = immediate.gains[0].events.at(-1);
    assert.equal(last.args[0], 0); assert(Math.abs(last.args[1] - last.at) < 0.005);
    await page.waitForFunction(() => window.__audio.gains[0].node.gain.value === 0, null, { timeout: 1000 });
    const a = await audio(page);
    await page.waitForFunction(() => document.querySelectorAll('.beats .playing').length === 1);
    await shot(page, 'mute-playing', 'Muted playback retains a visible beat indicator.');
    await page.waitForFunction(() => document.querySelector('#app').classList.contains('flash'));
    await shot(page, 'mute-motion-mid', 'Silent quarter-note wash during its 160 ms pulse.');
    const opacity = await page.evaluate(async () => {
      for (let i = 0; i < 120; i++) {
        const value = Number(getComputedStyle(document.querySelector('#app'), '::after').opacity);
        if (value > 0.01) return value;
        await new Promise(requestAnimationFrame);
      }
      return 0;
    });
    assert(opacity > 0);
    await stop(page); await shot(page, 'mute-motion-settled', 'Pause clears playing marker and silent pulse.');
    return { immediateGainProperty: immediate.gains[0].value, processedGain: a.gains[0].value, automation: last, muteSelected: await page.locator('#mute').getAttribute('aria-pressed'), observedPulseOpacity: opacity, stoppedIndicators: await page.locator('.beats .playing').count() };
  });
  await scenario('Unmute and zero-volume range update real master gain', async () => {
    await play(page);
    await page.locator('#mute').click(); await nav(page, 'settings');
    await page.locator('#volume').fill('0');
    await page.waitForFunction(() => window.__audio.gains[0].node.gain.value === 0);
    const zero = (await audio(page)).gains[0].value;
    await page.locator('#volume').fill('42'); const immediatelyRestored = await audio(page);
    console.log('VOLUME_DIAGNOSTIC', JSON.stringify({ states: immediatelyRestored.states, master: immediatelyRestored.gains[0] }));
    await page.waitForFunction(() => Math.abs(window.__audio.gains[0].node.gain.value - 0.42) < 0.000001, null, { timeout: 1000 });
    const restored = (await audio(page)).gains[0].value;
    await nav(page, 'home');
    await stop(page);
    assert.equal(zero, 0); assert(Math.abs(restored - 0.42) < 0.000001);
    return { zeroMaster: zero, immediateRestore: immediatelyRestored.gains[0], restoredMaster: restored, volumeLabel: await page.locator('#volume-label').textContent() };
  });
  await scenario('Pause cancels scheduled playback sources and stops future scheduling', async () => {
    await bpm(page, 300); await play(page);
    await page.waitForFunction(() => window.__audio.sources.some(s => !s.ended));
    await stop(page); const immediate = await audio(page);
    await pause(150); const later = await audio(page);
    const cancelled = immediate.sources.filter(s => s.stop.some(e => e.args.length === 0));
    assert(cancelled.length > 0); assert.equal(later.sources.length, immediate.sources.length);
    return { immediateSourceCount: immediate.sources.length, after150msSourceCount: later.sources.length, cancelledSources: cancelled.map(s => ({ id: s.id, stops: s.stop })) };
  });
  await scenario('Timing change cancels old sources and restarts at beat one', async () => {
    await play(page); const snapshot = await audio(page); const before = snapshot.sources.length;
    await bpm(page, 120); const after = await audio(page);
    const cancelled = after.sources.filter(s => s.stop.some(e => e.args.length === 0 && e.at >= snapshot.states[0].currentTime));
    assert(cancelled.length > 0);
    const lastCancel = Math.max(...cancelled.flatMap(s => s.stop.filter(e => !e.args.length).map(e => e.at)));
    const newSource = after.sources.find(s => s.start[0].at >= lastCancel && !s.stop.some(e => !e.args.length));
    assert(newSource); assert.equal(newSource.frequency[0].args[0], 523.25);
    await stop(page);
    return { oldSourceCount: before, latestCancellationTime: lastCancel, newSource: { frequency: newSource.frequency, start: newSource.start }, oldImmediateStops: cancelled.length };
  });
  await scenario('Real AudioContext suspension stops transport and surfaces error', async () => {
    await play(page); await page.evaluate(() => window.__audio.contexts[0].suspend());
    await page.waitForFunction(() => document.querySelector('#play').getAttribute('aria-pressed') === 'false');
    const a = await audio(page); const status = await page.locator('#status').textContent();
    assert(status.includes('오디오가 중단'));
    return { contextState: a.states[0].state, transport: await page.locator('#play').textContent(), status };
  });
  await scenario('pagehide cancels playback and pending tap measurement', async () => {
    await play(page); await page.evaluate(() => window.dispatchEvent(new Event('pagehide')));
    assert.equal(await page.locator('#play').getAttribute('aria-pressed'), 'false');
    await nav(page, 'tap'); await page.locator('#tap-pad').click();
    await page.evaluate(() => window.dispatchEvent(new Event('pagehide')));
    const values = { tapCount: await page.locator('#tap-count').textContent(), tapTime: await page.locator('#tap-time').textContent(), applyDisabled: await page.locator('#tap-apply').isDisabled() };
    assert.equal(values.tapCount, '0회'); assert(values.applyDisabled);
    return values;
  });
  await scenario('Visibility hidden event stops playback', async () => {
    await nav(page, 'home'); await play(page);
    await page.evaluate(() => { Object.defineProperty(document, 'hidden', { configurable: true, value: true }); document.dispatchEvent(new Event('visibilitychange')); });
    const stopped = await page.locator('#play').getAttribute('aria-pressed');
    await page.evaluate(() => { delete document.hidden; });
    assert.equal(stopped, 'false');
    return { stopped, playingMarkers: await page.locator('.beats .playing').count(), eventInjection: 'document.hidden=true + visibilitychange (not physical app background)' };
  });
  await scenario('Keyboard focus ring, arrow tempo and button Space activation', async () => {
    await bpm(page, 120); await page.locator('#bpm').focus(); await page.keyboard.press('ArrowUp');
    assert.equal(await page.locator('#bpm').inputValue(), '120');
    await page.locator('#bpm').press('Tab'); await page.keyboard.press('ArrowUp');
    assert.equal(await page.locator('#bpm').inputValue(), '121');
    const focus = await page.evaluate(() => ({ id: document.activeElement.id, outline: getComputedStyle(document.activeElement).outlineStyle, width: getComputedStyle(document.activeElement).outlineWidth }));
    await shot(page, 'keyboard-focus', 'Keyboard focus ring on the tempo increment control.');
    await page.locator('#play').focus(); await page.keyboard.press('Space');
    await page.waitForFunction(() => document.querySelector('#play').getAttribute('aria-pressed') === 'true');
    await stop(page);
    assert.equal(focus.outline, 'solid');
    return { bpmAfterInputArrow: 120, bpmAfterButtonArrow: 121, focus, stoppedAfterOneSpaceStart: true };
  });
  await scenario('Space in song input does not start transport or change tempo', async () => {
    await nav(page, 'library'); await page.locator('#song-title').fill('밤 음악'); await page.locator('#song-title').focus();
    await page.keyboard.press('Space'); await page.keyboard.press('ArrowUp');
    const values = { input: await page.locator('#song-title').inputValue(), playing: await page.locator('#play').getAttribute('aria-pressed'), bpm: await page.locator('#bpm').inputValue() };
    assert.equal(values.playing, 'false'); assert.equal(values.bpm, '121'); assert.equal(values.input, '밤 음악 ');
    return values;
  });
  await scenario('Decimal and out-of-range tempo error states preserve last valid tempo', async () => {
    await nav(page, 'home'); await page.locator('#bpm').fill('19'); await page.locator('#bpm').press('Enter');
    const low = { invalid: await page.locator('#bpm').getAttribute('aria-invalid'), message: await page.locator('#status').textContent() };
    await shot(page, 'invalid-bpm', 'Visible Korean integer range error and invalid input color.');
    await page.locator('#plus').click(); const restored = await page.locator('#bpm').inputValue();
    await page.locator('#bpm').fill('1.5'); await page.locator('#bpm').press('Enter');
    const decimal = await page.locator('#bpm').getAttribute('aria-invalid');
    assert.equal(low.invalid, 'true'); assert.equal(decimal, 'true'); assert.equal(restored, '122');
    await bpm(page, 120);
    return { low, decimalInvalid: decimal, plusUsesPriorValidTempo: restored };
  });
  await scenario('Two real taps over ten seconds cannot apply insufficient result', async () => {
    await nav(page, 'tap'); await page.locator('#tap-reset').click();
    const begin = Date.now(); await page.locator('#tap-pad').click(); await pause(750); await page.locator('#tap-pad').click();
    await page.waitForFunction(() => document.querySelector('#tap-time').textContent.includes('4회 이상'), { timeout: 12000 });
    const observed = { elapsedMs: Date.now() - begin, count: await page.locator('#tap-count').textContent(), time: await page.locator('#tap-time').textContent(), result: await page.locator('#tap-pad strong').textContent(), applyDisabled: await page.locator('#tap-apply').isDisabled() };
    assert(observed.elapsedMs >= 9900); assert.equal(observed.count, '2회'); assert(observed.applyDisabled);
    await shot(page, 'insufficient-tap', 'Real ten-second measurement rejects two taps and disables Apply.');
    return observed;
  });
  await scenario('Tap keyboard Enter and Space each add exactly one tap', async () => {
    await page.locator('#tap-reset').click(); await page.locator('#tap-pad').focus(); await page.keyboard.press('Enter');
    const first = await page.locator('#tap-count').textContent(); await pause(130); await page.keyboard.press('Space');
    const second = await page.locator('#tap-count').textContent(); assert.equal(first, '1회'); assert.equal(second, '2회');
    await page.locator('#tap-reset').click(); return { afterEnter: first, afterSpace: second };
  });
  await scenario('Reduced motion disables silent wash while beat state remains', async () => {
    await context.addInitScript(() => {}); await page.emulateMedia({ reducedMotion: 'reduce' });
    await nav(page, 'home'); await page.locator('#mute').click(); await play(page);
    await page.waitForFunction(() => document.querySelectorAll('.beats .playing').length === 1);
    const style = await page.evaluate(() => ({ animation: getComputedStyle(document.querySelector('#app'), '::after').animationName, active: document.querySelectorAll('.beats .playing').length }));
    assert.equal(style.animation, 'none'); assert.equal(style.active, 1); await shot(page, 'reduced-motion', 'Reduced motion leaves a discrete current beat without the wash animation.');
    await stop(page); await page.emulateMedia({ reducedMotion: 'no-preference' }); return style;
  });
  await scenario('All four pages render at required responsive preview widths', async () => {
    const values = [];
    for (const width of [240, 375, 768, 1280]) {
      await page.setViewportSize({ width, height: width === 240 ? 282 : 800 });
      for (const screen of ['home', 'tap', 'settings', 'library']) {
        await nav(page, screen);
        const size = await page.evaluate(id => ({ width: innerWidth, docWidth: document.documentElement.scrollWidth, app: { width: document.querySelector('#app').clientWidth, height: document.querySelector('#app').clientHeight }, screen: id }), screen);
        assert.equal(size.app.width, 240); assert.equal(size.app.height, 282); assert(size.docWidth <= width);
        values.push(size); await shot(page, `${width}-${screen}`, `${screen} page at ${width}px viewport; same 240×282 device controls.`);
      }
    }
    return values;
  });
  await scenario('Compact keyboard viewport keeps nav visible and library form scrollable', async () => {
    await page.setViewportSize({ width: 240, height: 170 }); await nav(page, 'library'); await page.locator('#song-title').focus();
    const values = await page.evaluate(() => ({ viewport: innerHeight, app: document.querySelector('#app').getBoundingClientRect().toJSON(), nav: document.querySelector('nav').getBoundingClientRect().toJSON(), page: { client: document.querySelector('#library').clientHeight, scroll: document.querySelector('#library').scrollHeight }, input: document.querySelector('#song-title').getBoundingClientRect().toJSON() }));
    assert(values.nav.bottom <= 170); assert(values.page.scroll > values.page.client);
    await page.locator('#save-song').scrollIntoViewIfNeeded(); await shot(page, 'compact-library', '170px keyboard-like viewport retains bottom navigation and scrollable form.');
    await page.setViewportSize({ width: 240, height: 282 }); return values;
  });
  await context.close();

  await scenario('Touch pointer plus compatibility click deduplicates TAP', async () => {
    const touch = await fresh({ hasTouch: true, isMobile: true });
    await nav(touch.page, 'tap'); await touch.page.locator('#tap-pad').tap();
    const one = await touch.page.locator('#tap-count').textContent();
    await pause(130); await touch.page.locator('#tap-pad').tap();
    const two = await touch.page.locator('#tap-count').textContent(); assert.equal(one, '1회'); assert.equal(two, '2회');
    await shot(touch.page, 'touch-tap', 'Two touch taps produce two accepted tap records.');
    await touch.context.close(); return { afterOneTouch: one, afterTwoTouches: two };
  });

  await scenario('Delayed real resume and rapid sideClick start-stop cannot resurrect playback', async () => {
    const delayed = await fresh({}, () => {
      const Native = window.AudioContext;
      window.__resumeCalls = 0; window.__releaseResume = [];
      const real = new Native({ latencyHint: 'interactive' });
      window.__delayedRealContext = real;
      const resume = real.resume.bind(real);
      real.resume = async () => { window.__resumeCalls++; await resume(); await new Promise(resolve => window.__releaseResume.push(resolve)); };
      window.AudioContext = class { constructor() { return real; } };
    });
    await delayed.page.evaluate(() => window.__delayedRealContext.suspend());
    const preStartState = await delayed.page.evaluate(() => window.__delayedRealContext.state);
    assert.equal(preStartState, 'suspended');
    await delayed.page.locator('#plus').click();
    await delayed.page.evaluate(() => window.dispatchEvent(new Event('sideClick')));
    await delayed.page.waitForFunction(() => window.__releaseResume.length === 1);
    const pending = { label: await delayed.page.locator('#play').textContent(), disabled: await delayed.page.locator('#play').isDisabled() };
    await delayed.page.evaluate(() => { window.dispatchEvent(new Event('sideClick')); window.__releaseResume.splice(0).forEach(r => r()); });
    await pause(120);
    const stopped = await delayed.page.locator('#play').getAttribute('aria-pressed'); assert.equal(stopped, 'false');
    await delayed.page.evaluate(() => window.dispatchEvent(new Event('sideClick')));
    await delayed.page.waitForFunction(() => document.querySelector('#play').getAttribute('aria-pressed') === 'true');
    const restarted = await delayed.page.locator('#play').getAttribute('aria-pressed'); await stop(delayed.page);
    const calls = await delayed.page.evaluate(() => window.__resumeCalls); await delayed.context.close();
    return { preStartState, pending, staleResumeStopped: stopped, freshRestart: restarted, realResumeCalls: calls };
  });

  await scenario('Slow native storage serializes concurrent settings/save/delete snapshots', async () => {
    const stored = new Map(); const writes = []; let active = 0; let peak = 0;
    const native = await browser.newContext({ viewport: { width: 240, height: 282 } });
    await native.exposeFunction('manualRead', key => stored.get(key) ?? null);
    await native.exposeFunction('manualWrite', async (key, value) => {
      active++; peak = Math.max(peak, active); const start = Date.now();
      const decoded = JSON.parse(Buffer.from(value, 'base64').toString('utf8'));
      writes.push({ start, bpm: decoded.settings.bpm, songs: decoded.songs.map(s => ({ title: s.title, bpm: s.bpm })) });
      await pause(450); stored.set(key, value); active--;
    });
    await native.addInitScript(() => { window.creationStorage = { plain: { getItem: k => window.manualRead(k), setItem: (k, v) => window.manualWrite(k, v) } }; });
    const p = await native.newPage(); await p.goto(url); await p.waitForFunction(() => !document.querySelector('#play').disabled);
    await bpm(p, 80); await nav(p, 'library'); await p.locator('#song-title').fill('느린 저장 music1'); await p.locator('#save-song').click();
    const busy = { saveDisabled: await p.locator('#save-song').isDisabled(), loadDisabled: await p.locator('.song-load').isDisabled() };
    await shot(p, 'native-save-busy', 'Slow native save disables song actions during its asynchronous write.');
    assert(busy.saveDisabled && busy.loadDisabled);
    await nav(p, 'home'); await bpm(p, 140);
    await pause(1600); const afterSave = JSON.parse(Buffer.from(stored.get('pulse_metronome_v1'), 'base64').toString('utf8'));
    assert.equal(afterSave.settings.bpm, 140); assert.equal(afterSave.songs.length, 1); assert.equal(afterSave.songs[0].bpm, 80);
    await nav(p, 'library'); await p.locator('.song-delete').click(); await p.locator('.song-delete').click();
    await nav(p, 'home'); await bpm(p, 160); await pause(1600);
    const afterDelete = JSON.parse(Buffer.from(stored.get('pulse_metronome_v1'), 'base64').toString('utf8'));
    assert.equal(afterDelete.songs.length, 0); assert.equal(afterDelete.settings.bpm, 160); assert.equal(peak, 1);
    await p.reload(); await p.waitForFunction(() => !document.querySelector('#play').disabled);
    assert.equal(await p.locator('#bpm').inputValue(), '160'); const browserStorage = await p.evaluate(() => localStorage.length);
    assert.equal(browserStorage, 0); await native.close();
    return { busy, maxConcurrentNativeWrites: peak, writes, afterSave: { bpm: afterSave.settings.bpm, song: afterSave.songs[0] }, afterDelete, reloadBpm: 160, localStorageEntries: browserStorage };
  });

  await scenario('Unavailable AudioContext gives actionable error and silent fallback runs', async () => {
    const silent = await fresh({}, () => { window.AudioContext = undefined; window.webkitAudioContext = undefined; });
    await silent.page.locator('#play').click();
    await silent.page.waitForFunction(() => !document.querySelector('#play').disabled);
    const failedStart = { status: await silent.page.locator('#status').textContent(), pressed: await silent.page.locator('#play').getAttribute('aria-pressed') };
    assert(failedStart.status.includes('무음 모드')); assert.equal(failedStart.pressed, 'false');
    await silent.page.locator('#mute').click(); await play(silent.page);
    await silent.page.waitForFunction(() => document.querySelectorAll('.beats .playing').length === 1);
    const running = await silent.page.locator('.beats .playing').count();
    await shot(silent.page, 'no-audio-silent-fallback', 'No AudioContext: user-selected silent playback still displays beats.');
    await stop(silent.page); await silent.context.close(); return { failedStart, silentPlayingIndicators: running };
  });

  await scenario('Single file boots directly through file URL without external dependencies', async () => {
    const fileContext = await browser.newContext({ viewport: { width: 240, height: 282 } });
    const p = await fileContext.newPage(); const requests = []; const errors = [];
    p.on('request', request => requests.push(request.url())); p.on('pageerror', error => errors.push(error.message));
    const target = pathToFileURL(new URL('dist/index.html', root).pathname.replace(/^\/(\w:)/, '$1')).href;
    await p.goto(target); await p.waitForFunction(() => !document.querySelector('#play').disabled);
    await p.locator('#mute').click(); await play(p); await p.waitForFunction(() => document.querySelectorAll('.beats .playing').length === 1);
    await stop(p); await shot(p, 'file-url-boot', 'Direct file:// self-contained app starts and operates without network assets.');
    assert.equal(errors.length, 0); assert(requests.every(r => r.startsWith('file:')));
    const observed = { target, requests, pageErrors: errors, bpm: await p.locator('#bpm').inputValue(), appSize: await p.locator('#app').evaluate(e => [e.clientWidth, e.clientHeight]) };
    await fileContext.close(); return observed;
  });
} catch (error) {
  rows.push({ name: 'Driver setup/execution failure', result: 'FAIL', observed: {}, error: error.stack });
  console.error(error);
} finally {
  if (browser) await browser.close();
  if (server.exitCode === null) server.kill();
  await report(true);
  process.exitCode = rows.some(row => row.result === 'FAIL') ? 1 : 0;
}
