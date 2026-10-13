import { test, expect } from '@playwright/test';
import { mkdir } from 'node:fs/promises';
import { decodeState } from '../src/core.js';

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
  await expect(page.locator('#bpm')).toHaveValue('81');
  await page.evaluate(() => window.dispatchEvent(new Event('scrollDown')));
  await expect(page.locator('#bpm')).toHaveValue('80');
  await setBpm(page, 300);
  await page.evaluate(() => window.dispatchEvent(new Event('scrollUp')));
  await expect(page.locator('#bpm')).toHaveValue('300');
  await setBpm(page, 20);
  await page.locator('#minus').click();
  await expect(page.locator('#bpm')).toHaveValue('20');
  await page.locator('#bpm').fill('abc');
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
  await page.locator('#mute-setting').check();
  await page.locator('#volume').fill('42');
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
  await expect(page.locator('[data-beat="2"]')).toHaveAttribute('aria-pressed', 'true');
  await nav(page, 'settings');
  await expect(page.locator('[data-sound="melody"]')).toHaveAttribute('aria-pressed', 'true');
  await expect(page.locator('#mute-setting')).toBeChecked();
  await expect(page.locator('#volume')).toHaveValue('42');
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

test('ten real seconds of tapping produces and applies about 80 BPM', async ({ page }) => {
  await nav(page, 'tap');
  const began = Date.now();
  await page.locator('#tap-pad').click();
  for (let i = 0; i < 13; i++) {
    await new Promise(resolve => setTimeout(resolve, Math.max(0, began + (i + 1) * 750 - Date.now())));
    await page.locator('#tap-pad').click();
  }
  await expect(page.locator('#tap-time')).toContainText('측정 완료');
  const duration = Date.now() - began;
  expect(duration).toBeGreaterThanOrEqual(9900);
  expect(duration).toBeLessThan(12500);
  const measured = Number(await page.locator('#tap-pad strong').textContent());
  expect(measured).toBeGreaterThanOrEqual(78);
  expect(measured).toBeLessThanOrEqual(82);
  await page.screenshot({ path: 'qa/screens/tap-result.png' });
  await page.locator('#tap-apply').click();
  await expect(page.locator('#bpm')).toHaveValue(String(measured));
});

test('leaving the tap screen cancels measurement', async ({ page }) => {
  await nav(page, 'tap');
  await page.locator('#tap-pad').click();
  await expect(page.locator('#tap-time')).toContainText('남음');
  await nav(page, 'home');
  await nav(page, 'tap');
  await expect(page.locator('#tap-time')).toHaveText('10초 측정');
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
    description: '4/4, 8비트, 셋잇단음표, 10초 탭 템포와 곡 저장', iconUrl: '', themeColor: '#FE5000',
  });
  const downloaded = page.waitForEvent('download');
  await page.locator('#download-qr').click();
  expect((await downloaded).suggestedFilename()).toBe('pulse-r1-install-qr.png');
  await page.screenshot({ path: 'qa/screens/install-qr.png' });
});
