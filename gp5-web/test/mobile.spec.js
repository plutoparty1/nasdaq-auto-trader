import { test, expect } from '@playwright/test';
import fs from 'node:fs/promises';
import { unzipSync } from 'fflate';
import fixture from './fixtures/korean-score.cjs';

const names = ['리드 기타 뷁', '베이스', '드럼'];
const source = fixture.makeKoreanGp5('euc-kr', { trackNames: names });
const rows = page => page.locator('#outputs .output-file');
const checks = page => page.locator('.track-check');
const idle = page => expect(page.locator('#convert')).toBeEnabled();
const payload = (name = '한글 악보 뷁.GP5', buffer = source.bytes) => ({ name, mimeType: 'application/octet-stream', buffer });

async function load(page) {
  await page.locator('#file-input').setInputFiles(payload());
  await expect(checks(page)).toHaveCount(3);
  await idle(page);
}
async function convert(page) { await page.locator('#convert').tap(); await idle(page); }
async function download(page, locator, info, name) {
  const pending = page.waitForEvent('download');
  await locator.tap();
  const result = await pending;
  const destination = info.outputPath(name);
  await result.saveAs(destination);
  expect(await result.failure()).toBeNull();
  return { name: result.suggestedFilename(), bytes: await fs.readFile(destination) };
}
async function downloadBytesAt(page, href) {
  const pending = page.waitForEvent('download');
  await page.locator(`a[download][href="${href}"]`).tap();
  const result = await pending;
  const stream = await result.createReadStream();
  expect(stream).not.toBeNull();
  const chunks = [];
  for await (const chunk of stream) chunks.push(chunk);
  expect(await result.failure()).toBeNull();
  return Buffer.concat(chunks);
}
async function screenshot(page, info, state) {
  await page.evaluate(() => document.fonts.ready);
  const metrics = await page.evaluate(() => ({
    width: innerWidth, overflow: document.documentElement.scrollWidth > innerWidth + 1,
    text: document.body.innerText,
    targets: [...document.querySelectorAll('button,.button,.track-option,.select-all,.output-actions a')]
      .map(element => ({ id: element.id || element.className, width: element.getBoundingClientRect().width,
        height: element.getBoundingClientRect().height })).filter(rect => rect.width > 0 && rect.height > 0),
  }));
  expect(metrics.overflow).toBe(false);
  expect(metrics.text).not.toContain('\ufffd');
  for (const target of metrics.targets) {
    expect(target.width, `${target.id} touch width`).toBeGreaterThanOrEqual(44);
    expect(target.height, `${target.id} touch height`).toBeGreaterThanOrEqual(44);
  }
  await page.screenshot({ path: info.outputPath(`${state}.png`), fullPage: true });
  await info.attach(`${state}-layout`, { body: JSON.stringify(metrics, null, 2), contentType: 'application/json' });
}

test.beforeEach(async ({ page }) => {
  // Only the operating-system share sheet is mocked; rendering, files, Blob URLs and downloads are real.
  await page.addInitScript(() => {
    const qa = { mode: 'success', canShare: true, shares: [], created: [], revoked: [], errors: [] };
    window.__mobileQa = qa;
    addEventListener('error', event => qa.errors.push(event.message));
    addEventListener('unhandledrejection', event => qa.errors.push(String(event.reason)));
    const create = URL.createObjectURL.bind(URL);
    const revoke = URL.revokeObjectURL.bind(URL);
    URL.createObjectURL = blob => { const url = create(blob); qa.created.push({ url, type: blob.type }); return url; };
    URL.revokeObjectURL = url => { qa.revoked.push(url); revoke(url); };
    Object.defineProperty(navigator, 'canShare', { configurable: true,
      value: data => qa.canShare && Array.isArray(data.files) && data.files.every(file => file instanceof File) });
    Object.defineProperty(navigator, 'share', { configurable: true, value: async data => {
      const call = { active: navigator.userActivation.isActive, files: [], mode: qa.mode };
      qa.shares.push(call);
      call.files = await Promise.all(data.files.map(async file => ({ name: file.name, type: file.type,
        bytes: [...new Uint8Array(await file.arrayBuffer())] })));
      if (call.mode === 'pending') await new Promise(resolve => { qa.finishShare = resolve; });
      else if (call.mode !== 'success') throw new DOMException('Native share sheet test response', call.mode);
    } });
  });
  await page.goto('./');
});
test.afterEach(async ({ page }) => {
  expect(await page.evaluate(() => window.__mobileQa.errors)).toEqual([]);
});

test('mobile picker exposes GP5 as a general file and validates content and extension', async ({ page }, info) => {
  expect(await page.locator('#file-input').getAttribute('accept')).toBe('.gp5,application/octet-stream');
  await screenshot(page, info, 'empty');
  for (const file of [payload('wrong.txt'), payload('broken.gp5', Buffer.from('not a guitar pro file'))]) {
    await page.locator('#file-input').setInputFiles(file);
    await expect(page.locator('#error')).toBeVisible();
    await expect(page.locator('#convert')).toBeDisabled();
  }
  const chooser = page.waitForEvent('filechooser');
  await page.locator('#choose').tap();
  await (await chooser).setFiles(payload());
  await expect(checks(page)).toHaveCount(3);
  await idle(page);
  for (const name of names) await expect(page.locator('#tracks')).toContainText(name);
  await page.locator('.track-option').nth(1).tap();
  expect(await page.locator('.track-check:checked').evaluateAll(inputs => inputs.map(input => Number(input.value)))).toEqual([0, 2]);
  await expect(page.locator('#select-all')).toHaveJSProperty('indeterminate', true);
  await page.locator('#file-input').dispatchEvent('cancel');
  await expect(checks(page).nth(1)).not.toBeChecked();
  await page.locator('#select-all-control').tap();
  await expect(page.locator('.track-check:checked')).toHaveCount(3);
  await page.locator('#select-all-control').tap();
  await expect(page.locator('#convert')).toBeDisabled();
  await page.locator('.track-option').nth(2).tap();
  await idle(page);
  await screenshot(page, info, 'touch-selection');
});

test('individual PDFs equal ZIP entries, share with activation, and survive cached pagehide', async ({ page, context }, info) => {
  info.annotations.push({ type: 'native-share', description: 'navigator.share/canShare are stubbed; the OS share sheet is not automated.' });
  await load(page);
  await page.locator('.track-option').nth(1).tap();
  await convert(page);
  await expect(rows(page)).toHaveCount(2);
  const archive = await download(page, page.locator('#download'), info, 'parts.zip');
  const entries = unzipSync(archive.bytes);
  expect(Object.keys(entries)).toHaveLength(2);
  for (const [ordinal, index] of [0, 2].entries()) {
    const row = rows(page).nth(ordinal);
    const name = await row.locator('.output-name').innerText();
    expect(name).toContain(`${String(index + 1).padStart(2, '0')} - ${names[index]}.pdf`);
    const pdf = await download(page, row.locator('.pdf-download'), info, `track-${index}.pdf`);
    expect(pdf.name).toBe(name);
    expect(pdf.bytes.subarray(0, 5).toString()).toBe('%PDF-');
    expect(pdf.bytes).toEqual(Buffer.from(entries[name]));
    const href = await row.locator('.pdf-download').getAttribute('href');
    expect(href).toMatch(/^blob:/u);
    await expect(row.locator('.pdf-open')).toHaveAttribute('href', href);
    await expect(row.locator('.pdf-open')).toHaveAttribute('target', '_blank');
    expect(await downloadBytesAt(page, href)).toEqual(pdf.bytes);
  }
  const popupEvent = context.waitForEvent('page');
  await rows(page).first().locator('.pdf-open').tap();
  const popup = await popupEvent;
  await info.attach('pdf-open', { body: JSON.stringify({ href: await rows(page).first().locator('.pdf-open').getAttribute('href'),
    popupUrl: popup.url(), limitation: 'Headless popup behavior does not verify the native PDF viewer.' }), contentType: 'application/json' });
  await popup.close();
  await rows(page).first().locator('.pdf-share').tap();
  await expect.poll(() => page.evaluate(() => window.__mobileQa.shares[0]?.files.length)).toBe(1);
  const call = await page.evaluate(() => window.__mobileQa.shares[0]);
  expect(call.active).toBe(true);
  expect(call.files[0].type).toBe('application/pdf');
  expect(Buffer.from(call.files[0].bytes)).toEqual(Buffer.from(entries[call.files[0].name]));
  await expect(page.locator('#share-zip')).toBeVisible();
  await page.locator('#share-zip').tap();
  await expect.poll(() => page.evaluate(() => window.__mobileQa.shares[1]?.files.length)).toBe(1);
  const zipShare = await page.evaluate(() => window.__mobileQa.shares[1]);
  expect(zipShare.active).toBe(true);
  expect(zipShare.files[0].type).toBe('application/zip');
  expect(zipShare.files[0].name).toBe(archive.name);
  expect(Buffer.from(zipShare.files[0].bytes)).toEqual(archive.bytes);
  for (const width of [320, 375, 768, 1280]) {
    await page.setViewportSize({ width, height: 900 });
    await screenshot(page, info, `complete-${width}`);
  }
  const urls = await page.locator('.pdf-download,#download').evaluateAll(links => links.map(link => link.href));
  const busy = await page.evaluate(bytes => {
    const transfer = new DataTransfer();
    transfer.items.add(new File([new Uint8Array(bytes)], 'replacement.gp5', { type: 'application/octet-stream' }));
    const input = document.querySelector('#file-input');
    input.files = transfer.files;
    input.dispatchEvent(new Event('change', { bubbles: true }));
    const snapshot = { anchors: [...document.querySelectorAll('.pdf-download,.pdf-open,#download')].map(link => ({
      href: link.getAttribute('href'), disabled: link.getAttribute('aria-disabled') })),
    shareDisabled: [...document.querySelectorAll('.pdf-share,#share-zip')].every(button => button.disabled) };
    document.querySelector('#cancel').click();
    return snapshot;
  }, [...source.bytes]);
  expect(busy.anchors).toHaveLength(5);
  expect(busy.anchors.every(anchor => anchor.href === null && anchor.disabled === 'true')).toBe(true);
  expect(busy.shareDisabled).toBe(true);
  await idle(page);
  expect(await page.locator('.pdf-download,#download').evaluateAll(links => links.map(link => link.href))).toEqual(urls);
  await page.evaluate(() => dispatchEvent(new PageTransitionEvent('pagehide', { persisted: true })));
  for (const url of urls) expect((await downloadBytesAt(page, url)).length).toBeGreaterThan(0);
  expect(await page.evaluate(values => values.filter(url => window.__mobileQa.revoked.includes(url)), urls)).toEqual([]);
  await page.evaluate(() => { window.__mobileQa.mode = 'pending'; });
  await rows(page).first().locator('.pdf-share').tap();
  await expect.poll(() => page.evaluate(() => typeof window.__mobileQa.finishShare)).toBe('function');
  await page.locator('.track-option').nth(2).tap();
  await expect(page.locator('#result')).toBeHidden();
  for (const url of urls) expect(await page.evaluate(value => window.__mobileQa.revoked.includes(value), url)).toBe(true);
  await convert(page);
  await expect(rows(page)).toHaveCount(1);
  await page.evaluate(async () => { window.__mobileQa.finishShare(); await new Promise(resolve => setTimeout(resolve, 0)); });
  await expect(page.locator('#share-status')).toHaveText('');
  const replacements = await page.locator('.pdf-download,#download').evaluateAll(links => links.map(link => link.href));
  expect(replacements.every(url => !urls.includes(url))).toBe(true);
  await page.evaluate(() => dispatchEvent(new PageTransitionEvent('pagehide', { persisted: false })));
  for (const url of replacements) {
    expect(await page.evaluate(value => window.__mobileQa.revoked.includes(value), url)).toBe(true);
  }
  await expect(page.locator('.pdf-download[href],.pdf-open[href],#download[href]')).toHaveCount(0);
});

test('partial cancellation keeps completed PDF through dismissed and rejected share sheets', async ({ page }, info) => {
  await load(page);
  await page.locator('.track-option').nth(1).tap();
  await page.evaluate(() => {
    const observer = new MutationObserver(() => {
      if (document.querySelector('#progress').value >= 1) {
        observer.disconnect(); document.querySelector('#cancel').click();
      }
    });
    observer.observe(document.querySelector('main'), { subtree: true, attributes: true, childList: true });
  });
  await convert(page);
  await expect(rows(page)).toHaveCount(1);
  await expect(page.locator('.track-state').nth(2)).toHaveText('미완료');
  await expect(page.locator('.track-state').nth(1)).toHaveText('선택 안 함');
  const archive = await download(page, page.locator('#download'), info, 'partial.zip');
  const entries = unzipSync(archive.bytes);
  const filename = await rows(page).first().locator('.output-name').innerText();
  expect(Object.keys(entries)).toEqual([filename]);
  expect(filename).toContain(`01 - ${names[0]}.pdf`);
  const status = await page.locator('#status').innerText();
  const href = await rows(page).first().locator('.pdf-download').getAttribute('href');
  for (const [index, mode] of ['AbortError', 'NotAllowedError'].entries()) {
    await page.evaluate(value => { window.__mobileQa.mode = value; }, mode);
    await rows(page).first().locator('.pdf-share').tap();
    await expect.poll(() => page.evaluate(() => window.__mobileQa.shares.length)).toBe(index + 1);
    if (mode === 'AbortError') await expect(page.locator('#share-status')).toHaveText('');
    else await expect(page.locator('#share-status')).toContainText(/저장|열기/u);
    await expect(page.locator('#status')).toHaveText(status);
    await expect(rows(page).first().locator('.pdf-download')).toHaveAttribute('href', href);
    await expect(rows(page).first().locator('.pdf-share')).toBeEnabled();
    expect(await downloadBytesAt(page, href)).toEqual(Buffer.from(entries[filename]));
  }
  const pdf = await download(page, rows(page).first().locator('.pdf-download'), info, 'partial.pdf');
  expect(pdf.bytes).toEqual(Buffer.from(entries[filename]));
  await screenshot(page, info, 'partial-share-error');
});

test('unsupported file sharing leaves PDF save and open available', async ({ page }, info) => {
  await page.evaluate(() => { window.__mobileQa.canShare = false; });
  await load(page);
  await page.locator('#select-all-control').tap();
  await page.locator('.track-option').first().tap();
  await convert(page);
  await expect(rows(page)).toHaveCount(1);
  await expect(page.locator('.pdf-share')).toBeHidden();
  await expect(page.locator('#share-zip')).toBeHidden();
  await expect(rows(page).first().locator('.pdf-open')).toBeVisible();
  const pdf = await download(page, rows(page).first().locator('.pdf-download'), info, 'unsupported-share.pdf');
  expect(pdf.bytes.subarray(0, 5).toString()).toBe('%PDF-');
  expect(await page.evaluate(() => window.__mobileQa.shares)).toEqual([]);
  await screenshot(page, info, 'unsupported-share');
});
