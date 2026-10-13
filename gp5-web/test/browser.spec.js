import { test, expect } from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { unzipSync } from 'fflate';
import fixture from './fixtures/korean-score.cjs';

const qa = path.resolve('qa');
const runtimeErrors = new WeakMap();
const names = ['리드 기타 뷁', '베이스', '드럼'];
const sample = encoding => fixture.makeKoreanGp5(encoding, { trackNames: names });
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
const slug = value => value.replace(/[^a-z0-9]+/gi, '-').toLowerCase();
const id = info => `${info.project.name}-${slug(info.title)}`;
const checks = page => page.locator('.track-check');
const states = page => page.locator('.track-state');
const idle = page => expect(page.locator('#convert')).toBeEnabled();

async function load(page, encoding = 'euc-kr') {
  const data = sample(encoding);
  const sourcePath = path.join(qa, `web-runtime-source-${encoding}`, '한글 악보 뷁.gp5');
  await fs.mkdir(path.dirname(sourcePath), { recursive: true });
  await fs.writeFile(sourcePath, data.bytes);
  await page.locator('#file-input').setInputFiles(sourcePath);
  await expect(checks(page)).toHaveCount(3);
  await idle(page);
  return { ...data, sourcePath };
}
async function subset(page) { await checks(page).nth(1).uncheck(); }
async function capture(page, info, state) {
  await page.evaluate(() => document.fonts.ready);
  const metrics = await page.evaluate(() => ({ width: innerWidth, height: innerHeight,
    overflow: document.documentElement.scrollWidth > innerWidth + 1,
    text: document.body.innerText, focused: document.activeElement?.id || document.activeElement?.className,
    focusOutline: getComputedStyle(document.activeElement).outlineWidth,
    progress: document.querySelector('#progress')?.value,
    progressMax: document.querySelector('#progress')?.max,
    buttons: [...document.querySelectorAll('button,.button,.track-option,.select-all')].filter(el => el.getBoundingClientRect().width).map(el => ({
      id: el.id || el.className, width: el.getBoundingClientRect().width, height: el.getBoundingClientRect().height })) }));
  expect(metrics.overflow).toBe(false);
  expect(metrics.text).not.toContain('\ufffd');
  expect(metrics.buttons.every(button => button.height >= 44)).toBe(true);
  const prefix = path.join(qa, `web-runtime-${id(info)}-${state}`);
  await page.screenshot({ path: `${prefix}.png`, fullPage: true });
  await fs.writeFile(`${prefix}.json`, JSON.stringify(metrics, null, 2));
}
async function zip(page, info, suffix, indices) {
  await expect(page.locator('#download')).toBeVisible();
  const pending = page.waitForEvent('download');
  await page.locator('#download').click();
  const download = await pending;
  const folder = path.join(qa, `web-runtime-${id(info)}-${suffix}`);
  await fs.mkdir(folder, { recursive: true });
  const archive = path.join(folder, 'parts.zip');
  await download.saveAs(archive);
  expect(await download.failure()).toBeNull();
  const entries = unzipSync(await fs.readFile(archive));
  const filenames = Object.keys(entries);
  expect(filenames).toHaveLength(indices.length);
  const pdfs = [];
  for (const index of indices) {
    const expected = `${String(index + 1).padStart(2, '0')} - ${names[index]}.pdf`;
    const name = filenames.find(value => value.endsWith(expected));
    expect(name).toBeTruthy();
    expect(name).toBe(path.basename(name));
    expect(Buffer.from(entries[name]).subarray(0, 5).toString()).toBe('%PDF-');
    const output = path.join(folder, name);
    await fs.writeFile(output, entries[name]);
    pdfs.push({ index, name, path: output, sha256: hash(entries[name]) });
  }
  await fs.writeFile(path.join(folder, 'manifest.json'), JSON.stringify({ browser: info.project.name,
    archive, suggestedFilename: download.suggestedFilename(), selectedIndices: indices, pdfs }, null, 2));
  return { archive, pdfs };
}
async function convert(page) { await page.locator('#convert').click(); await idle(page); }

test.beforeEach(async ({ page }) => {
  runtimeErrors.set(page, []);
  page.on('pageerror', error => runtimeErrors.get(page).push(error.message));
  await fs.mkdir(qa, { recursive: true }); await page.goto('./');
});
test.afterEach(async ({ page }, info) => {
  expect(runtimeErrors.get(page)).toEqual([]);
  if (info.status !== info.expectedStatus) await page.screenshot({ path: path.join(qa, `web-runtime-${id(info)}-failure.png`), fullPage: true }).catch(() => {});
});

test('01 native file chooser opens and loads GP5', async ({ page }, info) => {
  await expect(page.locator('#convert')).toBeDisabled();
  const pending = page.waitForEvent('filechooser');
  await page.locator('#choose').click();
  await (await pending).setFiles({ name: 'chooser.gp5', mimeType: 'application/octet-stream', buffer: sample('euc-kr').bytes });
  await expect(checks(page)).toHaveCount(3);
  await capture(page, info, 'loaded');
});
for (const encoding of ['euc-kr', 'utf-8']) {
  test(`02 ${encoding} Korean metadata and default selection`, async ({ page }) => {
    await load(page, encoding);
    expect(await page.evaluate(() => new TextDecoder('euc-kr', { fatal: true }).decode(Uint8Array.of(0x94, 0xee)))).toBe('뷁');
    for (const name of names) await expect(page.locator('#tracks')).toContainText(name);
    await expect(page.locator('body')).toContainText('한글 악보 제목');
    await expect(page.locator('.track-check:checked')).toHaveCount(3);
    await expect(page.locator('#select-all')).toBeChecked();
  });
  test(`03 ${encoding} subset actual PDF ZIP`, async ({ page }, info) => {
    await load(page, encoding); await subset(page); await convert(page);
    await expect(states(page).nth(1)).toHaveText('선택 안 함');
    await expect(page.locator('#progress')).toHaveAttribute('max', '2');
    expect(await page.locator('#progress').evaluate(el => el.value)).toBe(2);
    await zip(page, info, 'download', [0, 2]); await capture(page, info, 'complete');
  });
}
test('04 keyboard selects original indices and empty disables export', async ({ page }, info) => {
  await load(page); await checks(page).nth(1).focus(); await page.keyboard.press('Space');
  await expect(page.locator('#select-all')).toHaveJSProperty('indeterminate', true);
  await expect(page.locator('#track-count')).toContainText('2');
  expect(await page.locator('.track-check:checked').evaluateAll(els => els.map(el => Number(el.value)))).toEqual([0, 2]);
  await capture(page, info, 'focus');
  await page.locator('#select-all').check(); await page.locator('#select-all').uncheck();
  await expect(page.locator('#convert')).toBeDisabled();
  await page.locator('#select-all').focus(); await page.keyboard.press('Space');
  await expect(page.locator('.track-check:checked')).toHaveCount(3);
});
test('05 all tracks export includes bass and drum', async ({ page }, info) => {
  await load(page); await convert(page); await zip(page, info, 'all', [0, 1, 2]);
});
test('06 repeated export preserves downloaded files and source', async ({ page }, info) => {
  const before = await load(page); await subset(page); await convert(page);
  const first = await zip(page, info, 'first', [0, 2]);
  await convert(page); await zip(page, info, 'repeat', [0, 2]);
  for (const pdf of first.pdfs) expect(hash(await fs.readFile(pdf.path))).toBe(pdf.sha256);
  expect(hash(await fs.readFile(before.sourcePath))).toBe(hash(before.bytes));
});
test('07 busy locks and immediate cancel settle safely', async ({ page }, info) => {
  let release; const latch = new Promise(resolve => { release = resolve; });
  await page.route('**/assets/fonts/**', async route => { await latch; await route.continue().catch(() => {}); });
  await load(page); await page.locator('#convert').click();
  for (const selector of ['#convert', '#choose', '#file-input', '#select-all', '.track-check']) {
    for (const item of await page.locator(selector).all()) await expect(item).toBeDisabled();
  }
  await expect(page.locator('#cancel')).toBeEnabled(); await capture(page, info, 'busy');
  await page.locator('#cancel').click(); release(); await idle(page);
  await expect(page.locator('#download')).toBeHidden(); await capture(page, info, 'cancelled');
});
test('08 partial cancellation retains exactly completed PDF', async ({ page }, info) => {
  await load(page); await subset(page);
  await page.evaluate(() => {
    const observer = new MutationObserver(() => {
      if (document.querySelector('#progress').value >= 1) { observer.disconnect(); document.querySelector('#cancel').click(); }
    });
    observer.observe(document.querySelector('main'), { subtree: true, attributes: true, childList: true });
  });
  await convert(page); await zip(page, info, 'partial', [0]);
  await expect(states(page).nth(1)).toHaveText('선택 안 함');
  await expect(states(page).nth(2)).toHaveText('미완료'); await capture(page, info, 'partial');
});
test('09 malformed GP5 reports error then recovers', async ({ page }, info) => {
  await page.locator('#file-input').setInputFiles({ name: 'broken.gp5', mimeType: 'application/octet-stream', buffer: Buffer.from('not a GP5 score') });
  await expect(page.locator('#status')).toContainText(/파일|실패|오류|지원|형식/u);
  await expect(page.locator('#convert')).toBeDisabled(); await capture(page, info, 'error');
  await load(page); await subset(page); await convert(page); await zip(page, info, 'recovered', [0, 2]);
});
test('10 failed font loading reports error and retry works', async ({ page }, info) => {
  await page.route('**/assets/fonts/**', route => route.fulfill({ status: 503, body: 'QA asset unavailable' }));
  await load(page); await subset(page); await convert(page);
  await expect(page.locator('#error')).toContainText(/글꼴|실패|오류/u);
  await expect(page.locator('#download')).toBeHidden(); await capture(page, info, 'asset-error');
  await page.unroute('**/assets/fonts/**'); await convert(page); await zip(page, info, 'recovered', [0, 2]);
});
test('11 production subpath uses same origin GET only', async ({ page }, info) => {
  const requests = []; const errors = [];
  page.on('request', req => requests.push({ url: req.url(), method: req.method(), bytes: req.postDataBuffer()?.length ?? 0 }));
  page.on('pageerror', error => errors.push(error.message));
  await page.reload(); await load(page); await subset(page); await convert(page); await zip(page, info, 'private', [0, 2]);
  const origin = new URL(page.url()).origin;
  expect(new URL(page.url()).pathname).toBe(new URL(info.project.use.baseURL).pathname);
  expect(requests.filter(req => /^https?:/u.test(req.url)).every(req => new URL(req.url).origin === origin && req.method === 'GET' && req.bytes === 0)).toBe(true);
  expect(errors).toEqual([]);
  await fs.writeFile(path.join(qa, `web-runtime-${id(info)}-network.json`), JSON.stringify(requests, null, 2));
});
test('12 cancelling replacement picker preserves subset', async ({ page }) => {
  await load(page); await subset(page);
  await page.locator('#file-input').evaluate(el => el.dispatchEvent(new Event('cancel', { bubbles: true })));
  expect(await page.locator('.track-check:checked').evaluateAll(els => els.map(el => Number(el.value)))).toEqual([0, 2]);
  await idle(page);
});
for (const width of [320, 390, 1440]) {
  test(`13 responsive ${width} states and focus`, async ({ page }, info) => {
    await page.setViewportSize({ width, height: 844 }); await capture(page, info, 'empty');
    await load(page); await checks(page).nth(1).focus(); await page.keyboard.press('Space');
    await capture(page, info, 'selected-focus');
    let release; const latch = new Promise(resolve => { release = resolve; });
    await page.route('**/assets/fonts/**', async route => { await latch; await route.continue(); });
    await page.locator('#convert').click(); await expect(page.locator('#cancel')).toBeEnabled();
    await capture(page, info, 'busy'); release(); await idle(page); await capture(page, info, 'complete');
    await page.locator('#select-all').check(); await page.locator('#select-all').uncheck();
    await expect(page.locator('#convert')).toBeDisabled(); await capture(page, info, 'zero-selection');
    await page.locator('#file-input').setInputFiles({ name: 'invalid.gp5', mimeType: 'application/octet-stream', buffer: Buffer.from('invalid') });
    await expect(page.locator('#error')).toBeVisible(); await capture(page, info, 'error');
  });
}
test('14 stalled PDF module cancels before network resumes then retries', async ({ page }, info) => {
  let requested = false; let release;
  const latch = new Promise(resolve => { release = resolve; });
  await page.route(/\/assets\/pdf-[^/]+\.js$/u, async route => {
    requested = true; await latch; await route.continue().catch(() => {});
  });
  await load(page); await subset(page); await page.locator('#convert').click();
  try {
    await expect.poll(() => requested).toBe(true);
    await page.locator('#cancel').click();
    await expect(page.locator('#convert')).toBeEnabled({ timeout: 5000 });
    await expect(page.locator('#download')).toBeHidden();
    await expect(states(page).nth(0)).toHaveText('미완료');
    await capture(page, info, 'cancelled-before-module-release');
  } finally { release(); }
  await convert(page); await zip(page, info, 'recovered', [0, 2]);
  await capture(page, info, 'recovered');
});
