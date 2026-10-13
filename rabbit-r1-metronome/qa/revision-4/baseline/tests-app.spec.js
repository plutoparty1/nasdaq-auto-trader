import { test, expect } from '@playwright/test';
import { mkdir } from 'node:fs/promises';
import { DEFAULT_SETTINGS, decodeState, encodeState } from '../src/core.js';

test.beforeEach(async ({ page }) => {
  await page.goto('/');
  await expect(page.locator('#play')).toBeEnabled();
});
const setBpm = async (page, bpm) => {
  await page.locator('#bpm').fill(String(bpm));
  await page.locator('#bpm').press('Enter');
};
const nav = async (page, name) => page.locator('[data-page="' + name + '"]').click();

test('screens fit r1 and desktop preview sizes with Korean song titles', async ({ page }) => {
  await mkdir('qa/screens', { recursive: true });
  await setBpm(page, 80);
  await nav(page, 'library');
  await page.locator('#song-title').fill('봄날 music1');
  await page.locator('#save-song').click();
  await expect(page.locator('#status')).toContainText('저장 완료');
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
  await expect(page.locator('#status')).toContainText('정수 BPM');
  await expect(page.locator('#bpm')).toHaveAttribute('aria-invalid', 'true');
  await page.locator('#plus').click();
  await expect(page.locator('#bpm')).toHaveValue('21');
});

test('side button transport and silent visual beats on every page', async ({ page }) => {
  await page.locator('#mute').click();
  await page.evaluate(() => window.dispatchEvent(new Event('sideClick')));
  await expect(page.locator('#play')).toHaveText('일시정지');
  await expect.poll(() => page.locator('.beats .playing').count()).toBe(1);
  await page.screenshot({ path: 'qa/screens/silent-playing.png' });
  await page.evaluate(() => window.dispatchEvent(new Event('sideClick')));
  await expect(page.locator('#play')).toContainText('재생');
  await expect(page.locator('.beats .playing')).toHaveCount(0);
  await nav(page, 'settings');
  await page.evaluate(() => window.dispatchEvent(new Event('sideClick')));
  await expect(page.locator('#play')).toHaveText('일시정지');
  await expect(page.locator('#status')).toContainText('재생 중');
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
  await expect(page.locator('#status')).toContainText('저장 완료');
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
  await expect(page.locator('#status')).toContainText('저장 완료');
  await expect(page.locator('#song-list img')).toHaveCount(0);
  await page.locator('.song-delete').click();
  await expect(page.locator('.song-load')).toHaveCount(1);
  await expect(page.locator('.song-delete')).toHaveText('확인');
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
  await expect(page.locator('#tap-count')).toHaveText('8회');
  await page.screenshot({ path: 'qa/screens/tap-result.png' });
  await page.locator('#tap-apply').click();
  await expect(page.locator('#home')).toBeVisible();
  await expect(page.locator('#bpm')).toHaveValue(String(measured));
});

test('leaving the tap screen cancels measurement', async ({ page }) => {
  await nav(page, 'tap');
  await page.locator('#tap-pad').click();
  await expect(page.locator('#tap-time')).toContainText('한 번 더');
  await nav(page, 'home');
  await nav(page, 'tap');
  await expect(page.locator('#tap-time')).toHaveText('');
  await expect(page.locator('#tap-apply')).toBeDisabled();
});

test('native Base64 storage persists Korean without writing localStorage', async ({ page }) => {
  const saved = new Map();
  await page.exposeFunction('pulseRead', key => saved.get(key) ?? null);
  await page.exposeFunction('pulseWrite', (key, value) => { saved.set(key, value); });
  await page.addInitScript(() => {
    window.creationStorage = { plain: { getItem: key => window.pulseRead(key), setItem: (key, value) => window.pulseWrite(key, value) } };
  });
  await page.reload();
  await expect(page.locator('#play')).toBeEnabled();
  await setBpm(page, 80);
  await nav(page, 'library');
  await page.locator('#song-title').fill('기기 저장 music1');
  await page.locator('#save-song').click();
  await expect(page.locator('#status')).toContainText('저장 완료');
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
  await expect(page.locator('#play')).toBeEnabled();
  await nav(page, 'library');
  await page.locator('#song-title').fill('실패할 곡');
  await page.locator('#save-song').click();
  await expect(page.locator('#status')).toContainText('저장하지 못했습니다');
  await expect(page.locator('.song-load')).toHaveCount(0);
});

test('corrupt saved data is never overwritten automatically', async ({ page }) => {
  let writes = 0;
  await page.exposeFunction('countWrite', () => { writes++; });
  await page.addInitScript(() => {
    window.creationStorage = { plain: { getItem: async () => 'corrupt', setItem: async () => window.countWrite() } };
  });
  await page.reload();
  await expect(page.locator('#status')).toContainText('저장소를 읽지 못했습니다');
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
  await setBpm(page, 300);
  await page.locator('[data-sub="3"]').click();
  await page.locator('#play').click();
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
  await page.locator('#play').click();
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
