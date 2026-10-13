import { test, expect } from '@playwright/test';
import { mkdir } from 'node:fs/promises';
import { DEFAULT_SETTINGS, decodeState, encodeState } from '../src/core.js';

test.beforeEach(async ({ page }) => {
  await page.goto('/');
  await expect(page.locator('#app')).toHaveAttribute('data-ready', 'true');
});
const setBpm = async (page, bpm) => {
  await page.locator('#bpm').fill(String(bpm));
  await page.locator('#bpm').press('Enter');
};
const nav = async (page, name) => page.locator('[data-page="' + name + '"]').click();

test('requested labels and hardware-only transport appear on r1', async ({ page }) => {
  await expect(page.locator('#play, #song-label, .wheel-hint')).toHaveCount(0);
  await expect(page.locator('.subdivision button')).toHaveText(['♩', '♪', '3']);
  await expect(page.locator('nav button')).toHaveText(['Tempo', 'Tap', 'Setting', '★']);
  await nav(page, 'settings');
  await expect(page.locator('.sound button')).toHaveText(['Drum', 'Melody']);
  await expect(page.locator('#settings .page-title, #settings .field-label')).toHaveCount(0);
  await nav(page, 'library');
  await expect(page.locator('#library h1')).toHaveText('★');
});

test('screens fit r1 and desktop preview sizes with Korean song titles', async ({ page }) => {
  await mkdir('qa/screens', { recursive: true });
  await setBpm(page, 80);
  await nav(page, 'library');
  await page.locator('#song-title').fill('봄날 music1');
  await page.locator('#save-song').click();
  await expect(page.locator('#song-count')).toHaveText('1 song');
  await expect(page.locator('#status')).toContainText('Saved');
  await page.locator('#status').evaluate(element => { element.hidden = true; });
  for (const width of [240, 375, 768, 1280]) {
    await page.setViewportSize({ width, height: width === 240 ? 282 : 800 });
    for (const screen of ['home', 'tap', 'settings', 'library']) {
      await nav(page, screen);
      expect(await page.locator('#app').evaluate(element => ({ width: element.clientWidth, height: element.clientHeight }))).toEqual({ width: 240, height: 282 });
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await page.screenshot({ path: 'qa/screens/' + width + '-' + screen + '.png' });
    }
  }
});

test('native wheel, input, keyboard and tempo boundaries', async ({ page }) => {
  await setBpm(page, 80);
  await page.evaluate(() => window.dispatchEvent(new Event('scrollUp')));
  await expect(page.locator('#bpm')).toHaveValue('79');
  await page.evaluate(() => window.dispatchEvent(new Event('scrollDown')));
  await expect(page.locator('#bpm')).toHaveValue('80');
  await page.mouse.move(120, 100);
  await page.mouse.wheel(0, 100);
  await expect(page.locator('#bpm')).toHaveValue('81');
  await page.mouse.wheel(0, -100);
  await expect(page.locator('#bpm')).toHaveValue('80');
  await page.locator('body').press('ArrowUp');
  await expect(page.locator('#bpm')).toHaveValue('81');
  await page.locator('body').press('ArrowDown');
  await expect(page.locator('#bpm')).toHaveValue('80');
  await setBpm(page, 300);
  await page.evaluate(() => window.dispatchEvent(new Event('scrollDown')));
  await expect(page.locator('#bpm')).toHaveValue('300');
  await setBpm(page, 20);
  await page.locator('#minus').click();
  await expect(page.locator('#bpm')).toHaveValue('20');
  await page.locator('#bpm').fill('19');
  await page.locator('#bpm').press('Enter');
  await expect(page.locator('#status')).toContainText('whole BPM');
  await expect(page.locator('#bpm')).toHaveAttribute('aria-invalid', 'true');
  await page.locator('#plus').click();
  await expect(page.locator('#bpm')).toHaveValue('21');
});

test('side button transport and silent visual beats on every page', async ({ page }) => {
  await page.locator('#mute').click();
  await page.evaluate(() => window.dispatchEvent(new Event('sideClick')));
  await expect(page.locator('#app')).toHaveClass(/running/);
  await expect.poll(() => page.locator('.beats .playing').count()).toBe(1);
  await page.screenshot({ path: 'qa/screens/silent-playing.png' });
  await page.evaluate(() => window.dispatchEvent(new Event('sideClick')));
  await expect(page.locator('#app')).not.toHaveClass(/running/);
  await expect(page.locator('.beats .playing')).toHaveCount(0);
  await nav(page, 'settings');
  await page.evaluate(() => window.dispatchEvent(new Event('sideClick')));
  await expect(page.locator('#app')).toHaveClass(/running/);
  await expect(page.locator('#status')).toContainText('Playing');
});

test('all song settings restore after reload and selection', async ({ page }) => {
  await setBpm(page, 80);
  await page.locator('[data-sub="3"]').click();
  await page.locator('[data-beat="2"]').click();
  await nav(page, 'settings');
  await page.locator('[data-sound="melody"]').click();
  await page.locator('#mute').click();
  await nav(page, 'library');
  await page.locator('#song-title').fill('한국어 music1');
  await page.locator('#save-song').click();
  await expect(page.locator('.song-load')).toContainText('80-한국어 music1');
  await expect(page.locator('#status')).toContainText('Saved');
  await page.reload();
  await expect(page.locator('#bpm')).toHaveValue('80');
  await expect(page.locator('[data-sub="3"]')).toHaveAttribute('aria-pressed', 'true');
  await setBpm(page, 120);
  await nav(page, 'library');
  await page.locator('.song-load').click();
  await expect(page.locator('#bpm')).toHaveValue('80');
  await expect(page.locator('[data-beat="2"]')).toHaveAttribute('aria-pressed', 'false');
  await nav(page, 'settings');
  await expect(page.locator('[data-sound="melody"]')).toHaveAttribute('aria-pressed', 'true');
  await expect(page.locator('#mute')).toHaveAttribute('aria-pressed', 'true');
  await expect(page.locator('#volume, #mute-setting')).toHaveCount(0);
});

test('delete confirmation and HTML injection resistance', async ({ page }) => {
  await nav(page, 'library');
  await page.locator('#song-title').fill('<img src=x onerror=alert(1)>');
  await page.locator('#save-song').click();
  await expect(page.locator('#status')).toContainText('Saved');
  await expect(page.locator('#song-list img')).toHaveCount(0);
  await page.locator('.song-delete').click();
  await expect(page.locator('.song-load')).toHaveCount(1);
  await expect(page.locator('.song-delete')).toHaveText('Confirm');
  await page.screenshot({ path: 'qa/screens/delete-confirmation.png' });
  await page.locator('.song-delete').click();
  await expect(page.locator('.song-load')).toHaveCount(0);
  await page.reload();
  await nav(page, 'library');
  await expect(page.locator('#library-empty')).toBeVisible();
});

test('live taps immediately show and apply BPM, then follow a faster tempo', async ({ page }) => {
  await nav(page, 'tap');
  await page.evaluate(() => { window.pulseTapTimes = []; document.querySelector('#tap-pad').addEventListener('pointerdown', () => window.pulseTapTimes.push(performance.timeOrigin + performance.now()), { capture: true }); });
  const pad = await page.locator('#tap-pad').boundingBox();
  const tapPoint = { x: pad.x + pad.width / 2, y: pad.y + pad.height / 2 };
  await page.mouse.click(tapPoint.x, tapPoint.y);
  await expect(page.locator('#tap-count')).toHaveText('1 tap');
  await expect(page.locator('#tap-apply')).toBeDisabled();
  let target = await page.evaluate(() => window.pulseTapTimes[0]);
  for (let i = 0; i < 3; i++) {
    target += 750;
    await new Promise(resolve => setTimeout(resolve, Math.max(0, target - Date.now())));
    await page.mouse.click(tapPoint.x, tapPoint.y);
    const measured = Number(await page.locator('#tap-pad strong').textContent());
    const taps = await page.evaluate(() => window.pulseTapTimes);
    const recent = taps.slice(-5);
    expect(measured).toBe(Math.round(60000 * (recent.length - 1) / (recent.at(-1) - recent[0])));
    expect(measured).toBeGreaterThanOrEqual(78);
    expect(measured).toBeLessThanOrEqual(82);
    await expect(page.locator('#bpm')).toHaveValue(String(measured));
  }
  await expect(page.locator('#tap-time')).toHaveText('BPM');
  for (let i = 0; i < 4; i++) {
    target += 500;
    await new Promise(resolve => setTimeout(resolve, Math.max(0, target - Date.now())));
    await page.mouse.click(tapPoint.x, tapPoint.y);
  }
  const measured = Number(await page.locator('#tap-pad strong').textContent());
  expect(measured).toBeGreaterThanOrEqual(118);
  expect(measured).toBeLessThanOrEqual(122);
  await expect(page.locator('#bpm')).toHaveValue(String(measured));
  await expect(page.locator('#tap-count')).toHaveText('8 taps');
  await page.screenshot({ path: 'qa/screens/tap-result.png' });
  await page.locator('#tap-apply').click();
  await expect(page.locator('#home')).toBeVisible();
  await expect(page.locator('#bpm')).toHaveValue(String(measured));
});

test('leaving the tap screen cancels measurement', async ({ page }) => {
  await nav(page, 'tap');
  await page.locator('#tap-pad').click();
  await expect(page.locator('#tap-time')).toContainText('Tap again');
  await nav(page, 'home');
  await nav(page, 'tap');
  await expect(page.locator('#tap-time')).toHaveText('');
  await expect(page.locator('#tap-apply')).toBeDisabled();
});

test('a save cannot overwrite old songs while native storage is still loading', async ({ page }) => {
  const saved = new Map([['pulse_metronome_v1', encodeState({ settings: DEFAULT_SETTINGS, songs: [{ ...DEFAULT_SETTINGS, id: 'old-song', title: '기존 곡', bpm: 84 }] })]]);
  let finishRead;
  const blockedRead = new Promise(resolve => { finishRead = resolve; });
  let firstRead = true;
  await page.exposeFunction('pulseSlowRead', async key => {
    if (firstRead) { firstRead = false; return blockedRead; }
    return saved.get(key) ?? null;
  });
  await page.exposeFunction('pulseSlowWrite', (key, value) => { saved.set(key, value); });
  await page.addInitScript(() => {
    window.creationStorage = { plain: { getItem: key => window.pulseSlowRead(key), setItem: (key, value) => window.pulseSlowWrite(key, value) } };
  });
  await page.reload({ waitUntil: 'domcontentloaded' });
  await nav(page, 'library');
  await page.locator('#song-title').fill('새 곡');
  await expect(page.locator('#save-song')).toBeDisabled();
  finishRead(saved.get('pulse_metronome_v1'));
  await expect(page.locator('.song-load')).toContainText('84-기존 곡');
  await expect(page.locator('#save-song')).toBeEnabled();
  await page.locator('#save-song').click();
  await expect(page.locator('#status')).toContainText('Saved');
  expect(decodeState(saved.get('pulse_metronome_v1')).songs.map(song => song.title)).toEqual(['기존 곡', '새 곡']);
});

test('late storage bridge loads songs even before other r1 globals are injected', async ({ page }) => {
  const saved = new Map([['pulse_metronome_v1', encodeState({ settings: DEFAULT_SETTINGS, songs: [{ ...DEFAULT_SETTINGS, id: 'late-song', title: '늦게 연결된 곡', bpm: 96 }] })]]);
  await page.exposeFunction('pulseNoMarkerRead', key => saved.get(key) ?? null);
  await page.exposeFunction('pulseNoMarkerWrite', (key, value) => { saved.set(key, value); });
  await page.addInitScript(() => {
    setTimeout(() => {
      window.creationStorage = { plain: { getItem: key => window.pulseNoMarkerRead(key), setItem: (key, value) => window.pulseNoMarkerWrite(key, value) } };
    }, 100);
  });
  await page.reload();
  await nav(page, 'library');
  await expect(page.locator('.song-load')).toContainText('96-늦게 연결된 곡');
});

test('r1 waits for a late native storage bridge before loading saved songs', async ({ page }) => {
  const saved = new Map();
  saved.set('pulse_metronome_v1', encodeState({ settings: DEFAULT_SETTINGS, songs: [{ ...DEFAULT_SETTINGS, id: 'older-song', title: '기존 곡', bpm: 84 }] }));
  await page.exposeFunction('pulseReadLate', key => saved.get(key) ?? null);
  await page.exposeFunction('pulseWriteLate', (key, value) => { saved.set(key, value); });
  await page.addInitScript(() => {
    window.PluginMessageHandler = { postMessage() {} };
    setTimeout(() => {
      window.creationStorage = { plain: { getItem: key => window.pulseReadLate(key), setItem: (key, value) => window.pulseWriteLate(key, value) } };
    }, 100);
  });
  await page.reload();
  await nav(page, 'library');
  await expect(page.locator('.song-load')).toContainText('84-기존 곡');
  await page.locator('#song-title').fill('새 곡');
  await page.locator('#save-song').click();
  await expect(page.locator('#status')).toContainText('Saved');
  expect(decodeState(saved.get('pulse_metronome_v1')).songs.map(song => song.title)).toEqual(['기존 곡', '새 곡']);
});

test('native storage restores songs previously saved in browser storage', async ({ page }) => {
  const saved = new Map();
  await page.exposeFunction('pulseReadMigration', key => saved.get(key) ?? null);
  await page.exposeFunction('pulseWriteMigration', (key, value) => { saved.set(key, value); });
  await page.addInitScript(() => {
    window.creationStorage = { plain: { getItem: key => window.pulseReadMigration(key), setItem: (key, value) => window.pulseWriteMigration(key, value) } };
  });
  const legacy = encodeState({ settings: DEFAULT_SETTINGS, songs: [{ ...DEFAULT_SETTINGS, id: 'local-song', title: '복구할 곡', bpm: 92 }] });
  await page.evaluate(value => localStorage.setItem('pulse_metronome_v1', value), legacy);
  await page.reload();
  await nav(page, 'library');
  await expect(page.locator('.song-load')).toContainText('92-복구할 곡');
  expect(decodeState(saved.get('pulse_metronome_v1')).songs[0].title).toBe('복구할 곡');
});

test('blocked browser cleanup does not resurrect a deleted migrated song', async ({ page }) => {
  const saved = new Map();
  await page.exposeFunction('pulseCleanupRead', key => saved.get(key) ?? null);
  await page.exposeFunction('pulseCleanupWrite', (key, value) => { saved.set(key, value); });
  await page.addInitScript(() => {
    const remove = Storage.prototype.removeItem;
    Storage.prototype.removeItem = function (key) {
      if (key === 'pulse_metronome_v1') throw new Error('cleanup blocked');
      return remove.call(this, key);
    };
    window.creationStorage = { plain: { getItem: key => window.pulseCleanupRead(key), setItem: (key, value) => window.pulseCleanupWrite(key, value) } };
  });
  await page.evaluate(value => localStorage.setItem('pulse_metronome_v1', value), encodeState({ settings: DEFAULT_SETTINGS, songs: [{ ...DEFAULT_SETTINGS, id: 'old-local', title: '복구 후 삭제', bpm: 88 }] }));
  await page.reload();
  await nav(page, 'library');
  await expect(page.locator('.song-load')).toContainText('88-복구 후 삭제');
  await page.locator('.song-delete').click();
  await page.locator('.song-delete').click();
  await expect(page.locator('#status')).toContainText('Song deleted');
  await page.reload();
  await nav(page, 'library');
  await expect(page.locator('.song-load')).toHaveCount(0);
});

test('r1 does not claim songs are saved while device storage is unavailable', async ({ page }) => {
  await page.addInitScript(() => { window.PluginMessageHandler = { postMessage() {} }; });
  await page.reload();
  await expect(page.locator('#status')).toContainText('Could not read storage');
  await nav(page, 'library');
  await expect(page.locator('#save-song')).toBeDisabled();
  expect(await page.evaluate(() => localStorage.getItem('pulse_metronome_v1'))).toBeNull();
});

test('native Base64 storage persists Korean without writing localStorage', async ({ page }) => {
  const saved = new Map();
  await page.exposeFunction('pulseRead', key => saved.get(key) ?? null);
  await page.exposeFunction('pulseWrite', (key, value) => { saved.set(key, value); });
  await page.addInitScript(() => {
    window.creationStorage = { plain: { getItem: key => window.pulseRead(key), setItem: (key, value) => window.pulseWrite(key, value) } };
  });
  await page.reload();
  await expect(page.locator('#app')).toHaveAttribute('data-ready', 'true');
  await setBpm(page, 80);
  await nav(page, 'library');
  await page.locator('#song-title').fill('기기 저장 music1');
  await page.locator('#save-song').click();
  await expect(page.locator('#status')).toContainText('Saved');
  expect(decodeState(saved.get('pulse_metronome_v1')).songs[0].title).toBe('기기 저장 music1');
  expect(await page.evaluate(() => localStorage.length)).toBe(0);
  await page.reload();
  await nav(page, 'library');
  await expect(page.locator('.song-load')).toContainText('80-기기 저장 music1');
});

test('failed native saves show errors and remove the unsaved row', async ({ page }) => {
  await page.addInitScript(() => {
    window.creationStorage = { plain: { getItem: async () => null, setItem: async () => { throw new Error('storage unavailable'); } } };
  });
  await page.reload();
  await expect(page.locator('#app')).toHaveAttribute('data-ready', 'true');
  await nav(page, 'library');
  await page.locator('#song-title').fill('실패할 곡');
  await page.locator('#save-song').click();
  await expect(page.locator('#status')).toContainText('Could not save song');
  await expect(page.locator('.song-load')).toHaveCount(0);
});

test('corrupt saved data is never overwritten automatically', async ({ page }) => {
  let writes = 0;
  await page.exposeFunction('countWrite', () => { writes++; });
  await page.addInitScript(() => {
    window.creationStorage = { plain: { getItem: async () => 'corrupt', setItem: async () => window.countWrite() } };
  });
  await page.reload();
  await expect(page.locator('#status')).toContainText('Could not read storage');
  await page.locator('#plus').click();
  await nav(page, 'library');
  await expect(page.locator('#save-song')).toBeDisabled();
  await new Promise(resolve => setTimeout(resolve, 300));
  expect(writes).toBe(0);
});

test('installation QR uses official JSON and downloads a PNG', async ({ page }) => {
  await page.setViewportSize({ width: 768, height: 900 });
  await page.goto('/install.html');
  await page.locator('#app-url').fill('http://localhost:4173/');
  await page.locator('button[type=submit]').click();
  await expect(page.locator('#message')).toContainText('공개 HTTPS');
  await page.locator('#app-url').fill('https://example.com/pulse/');
  await page.locator('button[type=submit]').click();
  await expect(page.locator('#qr canvas')).toBeVisible();
  expect(JSON.parse(await page.locator('#payload').textContent())).toEqual({
    title: 'PULSE 메트로놈', url: 'https://example.com/pulse/',
    description: '4/4, 8비트, 셋잇단음표, 실시간 탭 템포와 곡 저장', iconUrl: '', themeColor: '#FE5000',
  });
  const downloaded = page.waitForEvent('download');
  await page.locator('#download-qr').click();
  expect((await downloaded).suggestedFilename()).toBe('pulse-r1-install-qr.png');
  await page.screenshot({ path: 'qa/screens/install-qr.png' });
});

test('legacy saved volume is ignored and removed when settings are saved', async ({ page }) => {
  const song = { ...DEFAULT_SETTINGS, bpm: 80, volume: 0, id: 'legacy-song', title: '기존 노래' };
  await page.evaluate(encoded => localStorage.setItem('pulse_metronome_v1', encoded), encodeState({ settings: { ...DEFAULT_SETTINGS, volume: 0, bpm: 90 }, songs: [song] }));
  await page.reload();
  await expect(page.locator('#bpm')).toHaveValue('90');
  await nav(page, 'library');
  await page.locator('.song-load').click();
  await expect(page.locator('#bpm')).toHaveValue('80');
  await expect.poll(async () => {
    const encoded = await page.evaluate(() => localStorage.getItem('pulse_metronome_v1'));
    const saved = JSON.parse(Buffer.from(encoded, 'base64').toString('utf8'));
    return { bpm: saved.settings.bpm, settingsVolume: 'volume' in saved.settings, songVolume: 'volume' in saved.songs[0] };
  }).toEqual({ bpm: 80, settingsVolume: false, songVolume: false });
  await nav(page, 'settings');
  await expect(page.locator('#volume, #volume-label, #mute-setting')).toHaveCount(0);
});

test('actual Web Audio uses exactly accent and regular pitches in both triplet modes', async ({ page }) => {
  await page.addInitScript(() => {
    const NativeAudio = window.AudioContext;
    window.pulseTones = [];
    window.pulseBuffers = 0;
    window.AudioContext = class extends NativeAudio {
      createOscillator() {
        const oscillator = super.createOscillator();
        const original = oscillator.frequency.setValueAtTime.bind(oscillator.frequency);
        oscillator.frequency.setValueAtTime = (pitch, time) => {
          window.pulseTones.push({ pitch, time });
          return original(pitch, time);
        };
        return oscillator;
      }
      createBufferSource() { window.pulseBuffers++; return super.createBufferSource(); }
    };
  });
  await page.reload();
  await expect(page.locator('#app')).toHaveAttribute('data-ready', 'true');
  await setBpm(page, 300);
  await page.locator('[data-sub="3"]').click();
  await page.evaluate(() => window.dispatchEvent(new Event('sideClick')));
  await expect.poll(() => page.evaluate(() => window.pulseTones.length)).toBeGreaterThanOrEqual(12);
  const drum = await page.evaluate(() => window.pulseTones.slice(0, 12).map(tone => tone.pitch));
  expect(drum).toEqual(Array.from({ length: 12 }, (_, index) => index % 3 === 0 ? 150 : 1000));
  expect(await page.evaluate(() => window.pulseBuffers)).toBe(0);
  await page.evaluate(() => window.dispatchEvent(new Event('sideClick')));
  await nav(page, 'settings');
  await page.locator('[data-sound="melody"]').click();
  await page.evaluate(() => { window.pulseTones = []; });
  await page.evaluate(() => window.dispatchEvent(new Event('sideClick')));
  await expect.poll(() => page.evaluate(() => window.pulseTones.length)).toBeGreaterThanOrEqual(12);
  expect(await page.evaluate(() => window.pulseTones.slice(0, 12).map(tone => tone.pitch))).toEqual(Array.from({ length: 12 }, (_, index) => index % 3 === 0 ? 1320 : 660));
});

test('silent pulse is strong, quarter-only and behind accessible controls', async ({ page }) => {
  await setBpm(page, 120);
  await page.locator('[data-sub="3"]').click();
  await page.locator('#mute').click();
  const snapshot = page.evaluate(() => new Promise(resolve => {
    const app = document.querySelector('#app');
    const observer = new MutationObserver(() => {
      if (!app.classList.contains('flash')) return;
      requestAnimationFrame(() => {
        const style = getComputedStyle(app, '::after');
        observer.disconnect();
        resolve({ opacity: Number(style.opacity), duration: style.animationDuration, pointer: style.pointerEvents, layer: Number(style.zIndex), pageLayer: Number(getComputedStyle(document.querySelector('#home')).zIndex), color: style.backgroundColor, secondaryText: getComputedStyle(document.querySelector('.tempo-number > span')).color, top: style.top, bottom: style.bottom });
      });
    });
    observer.observe(app, { attributes: true, attributeFilter: ['class'] });
  }));
  await page.evaluate(() => window.dispatchEvent(new Event('sideClick')));
  expect(await snapshot).toEqual({ opacity: 0.62, duration: '0.11s', pointer: 'none', layer: 0, pageLayer: 1, color: 'rgb(254, 80, 0)', secondaryText: 'rgb(249, 249, 249)', top: '32px', bottom: '40px' });
  const pulses = await page.evaluate(() => new Promise(resolve => {
    const app = document.querySelector('#app');
    let flashes = 0;
    let flashing = app.classList.contains('flash');
    const observer = new MutationObserver(() => {
      const next = app.classList.contains('flash');
      if (next && !flashing) flashes++;
      flashing = next;
    });
    observer.observe(app, { attributes: true, attributeFilter: ['class'] });
    setTimeout(() => { observer.disconnect(); resolve(flashes); }, 1100);
  }));
  expect(pulses).toBeGreaterThanOrEqual(2);
  expect(pulses).toBeLessThanOrEqual(3);
  await page.locator('#mute').click();
  await expect(page.locator('#mute')).toHaveAttribute('aria-pressed', 'false');
  await page.evaluate(() => window.dispatchEvent(new Event('sideClick')));
  await expect(page.locator('#app')).not.toHaveClass(/flash/);
});


test('subdivision presets accent each pair or triplet and remain editable', async ({ page }) => {
  for (const sub of [2, 3]) {
    await page.locator('[data-sub="' + sub + '"]').click();
    for (const beat of [0, 1, 2, 3]) await expect(page.locator('[data-beat="' + beat + '"]')).toHaveAttribute('aria-pressed', 'true');
    await page.locator('[data-beat="1"]').click();
    await expect(page.locator('[data-beat="1"]')).toHaveAttribute('aria-pressed', 'false');
  }
  await page.locator('[data-sub="1"]').click();
  await expect(page.locator('[data-beat="0"]')).toHaveAttribute('aria-pressed', 'true');
  await expect(page.locator('[data-beat="1"]')).toHaveAttribute('aria-pressed', 'false');
});

test('BPM requests number keyboard and ignores alphabetic or mixed insertion', async ({ page }) => {
  const input = page.locator('#bpm');
  await expect(input).toHaveAttribute('type', 'number');
  await expect(input).toHaveAttribute('inputmode', 'numeric');
  await setBpm(page, 80);
  await input.click();
  await input.press('ControlOrMeta+A');
  await input.pressSequentially('musicE+-.');
  await expect(input).toHaveValue('80');
  await input.pressSequentially('90');
  await input.press('Enter');
  await expect(input).toHaveValue('90');
  const pasteAccepted = await input.evaluate(element => {
    const clipboard = new DataTransfer(); clipboard.setData('text/plain', '120music');
    return element.dispatchEvent(new ClipboardEvent('paste', { clipboardData: clipboard, cancelable: true }));
  });
  expect(pasteAccepted).toBe(false);
  await expect(input).toHaveValue('90');
  await nav(page, 'tap');
  await expect(page.locator('#tap-time')).toHaveText('');
  await page.locator('#tap-pad').click();
  await page.locator('#tap-reset').click();
  await expect(page.locator('#tap-time')).toHaveText('');
});


test('sound flash checkbox preserves audio and persists independently of mute', async ({ page }) => {
  await page.addInitScript(() => {
    const NativeAudio = window.AudioContext;
    window.pulseFlashMaster = null;
    window.AudioContext = class extends NativeAudio {
      constructor(...args) { super(...args); window.pulseFlashAudio = this; }
      createGain() { const gain = super.createGain(); window.pulseFlashMaster ??= gain; return gain; }
    };
  });
  await page.reload();
  await expect(page.locator('#app')).toHaveAttribute('data-ready', 'true');
  await setBpm(page, 120);
  await page.locator('[data-sub="3"]').click();
  await nav(page, 'settings');
  const option = page.getByRole('checkbox', { name: 'Flash with sound' });
  await expect(option).toBeVisible({ timeout: 1000 });
  await expect(option).not.toBeChecked();
  await page.evaluate(() => {
    window.pulseFlashCount = 0; let prior = false;
    new MutationObserver(() => { const next = document.querySelector('#app').classList.contains('flash'); if (next && !prior) window.pulseFlashCount++; prior = next; }).observe(document.querySelector('#app'), { attributes: true, attributeFilter: ['class'] });
    window.dispatchEvent(new Event('sideClick'));
  });
  await expect(page.locator('#app')).toHaveClass(/running/);
  await page.waitForTimeout(650);
  expect(await page.evaluate(() => window.pulseFlashCount)).toBe(0);
  await option.check();
  await expect.poll(() => page.evaluate(() => window.pulseFlashCount)).toBeGreaterThan(0);
  expect(await page.evaluate(() => ({ state: window.pulseFlashAudio.state, gain: window.pulseFlashMaster.gain.value }))).toEqual({ state: 'running', gain: 1 });
  await option.uncheck();
  await expect(page.locator('#app')).not.toHaveClass(/flash/);
  const stoppedCount = await page.evaluate(() => window.pulseFlashCount);
  await page.waitForTimeout(650);
  expect(await page.evaluate(() => window.pulseFlashCount)).toBe(stoppedCount);
  await page.locator('#mute').click();
  await expect.poll(() => page.evaluate(() => window.pulseFlashCount)).toBeGreaterThan(stoppedCount);
  await expect.poll(() => page.evaluate(() => window.pulseFlashMaster.gain.value)).toBe(0);
  await option.check();
  await page.locator('#mute').click();
  await expect.poll(() => page.evaluate(() => window.pulseFlashMaster.gain.value)).toBe(1);
  await page.evaluate(() => window.dispatchEvent(new Event('sideClick')));
  await nav(page, 'library');
  await page.locator('#song-title').fill('소리 화면 함께');
  await page.locator('#save-song').click();
  await expect(page.locator('#status')).toContainText('Saved');
  await page.reload();
  await nav(page, 'settings');
  await expect(option).toBeChecked();
  await option.uncheck();
  await nav(page, 'library');
  await page.locator('.song-load').click();
  await nav(page, 'settings');
  await expect(option).toBeChecked();
  await expect(page.locator('#mute')).toHaveAttribute('aria-pressed', 'false');
});
