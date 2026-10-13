import assert from 'node:assert/strict';
import { getEventListeners } from 'node:events';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import { unzipSync } from 'fflate';
import { loadGp5 } from '../src/import-score.js';
import { createExporter, createLazyRenderer } from '../src/export-score.js';
import koreanFixture from './fixtures/korean-score.cjs';

const { makeKoreanGp5 } = koreanFixture;
const fixtureFile = (fixture, name = '악보.gp5') => new File([fixture.bytes], name);
const source = { name: 'Song.gp5', score: {}, trackNames: ['Guitar', 'Bass', 'Drums'] };
const pdfBytes = (index) => new TextEncoder().encode(`%PDF-1.7\ntrack=${index}\n`);
const renderer = async ({ trackIndex }) => new Blob([pdfBytes(trackIndex)], { type: 'application/pdf' });

test('imports a real GP5 File with its complete title and original track order', async () => {
  const bytes = await readFile(new URL('./fixtures/QA Trio.gp5', import.meta.url));
  const result = await loadGp5(new File([bytes], 'QA Trio.GP5'));
  assert.equal(result.title, 'GP5 Runtime QA');
  assert.equal(result.encoding, 'utf-8');
  assert.deepEqual(result.trackNames, ['Electric Guitar', 'Bass Guitar', 'Drum Kit']);
  assert.equal(result.score.masterBars.length, 1);
});

for (const [label, encoding, options] of [
  ['CP949 Korean title, tracks and beat text', 'euc-kr', {}],
  ['UTF-8 Korean text', 'utf-8', {}],
  ['literal UTF-8 replacement character and emoji', 'utf-8', { title: '한글 제목 � 😀', trackNames: ['기타 �', '베이스', '드럼'] }],
  ['UTF-8 name truncated only in derived shortName', 'utf-8', { trackNames: ['가나다라마바사아자차', '베이스', '드럼'] }],
  ['CP949 beat text with ASCII headings', 'euc-kr', { title: 'ASCII title', trackNames: ['Guitar', 'Bass', 'Drums'] }],
]) {
  test(`preserves ${label} when importing a GP5 File`, async () => {
    const fixture = makeKoreanGp5(encoding, options);
    const result = await loadGp5(fixtureFile(fixture));
    assert.equal(result.encoding, encoding);
    assert.equal(result.title, fixture.title);
    assert.deepEqual(result.trackNames, fixture.trackNames);
    assert.equal(result.score.tracks[0].staves[0].bars[0].voices[0].beats[0].text, fixture.beatText);
    assert.deepEqual(new Uint8Array(await fixtureFile(fixture).arrayBuffer()), new Uint8Array(fixture.bytes));
  });
}

test('malformed, renamed, truncated and oversized files reject without returning a score', async () => {
  const fixture = makeKoreanGp5('utf-8');
  class OversizedFile extends File {
    get size() { return 64 * 1024 * 1024 + 1; }
    arrayBuffer() { throw new Error('Oversized file must not be read'); }
  }
  for (const file of [
    new File(['not a GP5'], 'broken.gp5'),
    new File([fixture.bytes], 'score.gpx'),
    new File([fixture.bytes.subarray(0, 60)], 'broken.gp5'),
    new OversizedFile([], 'large.gp5'),
  ]) await assert.rejects(loadGp5(file), /GP5|64/);
});

test('exports only selected original indices with numbered ZIP entries and selected progress', async () => {
  const calls = [];
  const progress = [];
  const exportSelected = createExporter(async (request) => {
    calls.push(request.trackIndex);
    assert.equal(request.score, source.score);
    request.onProgress({ page: 1 });
    return renderer(request);
  });
  const indices = [2, 0];
  const pending = exportSelected({ source, indices, onProgress: (event) => progress.push(event) });
  indices[1] = 1;
  const result = await pending;
  assert.equal(result.cancelled, false);
  assert.equal(result.error, null);
  assert.equal(result.blob.type, 'application/zip');
  assert.deepEqual(calls, [2, 0]);
  assert.deepEqual(result.files, ['Song - 03 - Drums.pdf', 'Song - 01 - Guitar.pdf']);
  const entries = unzipSync(new Uint8Array(await result.blob.arrayBuffer()));
  assert.deepEqual(Object.keys(entries), result.files);
  assert.deepEqual(entries[result.files[0]], pdfBytes(2));
  assert.deepEqual(entries[result.files[1]], pdfBytes(0));
  assert.deepEqual(result.pdfs.map(file => file.name), result.files);
  for (const pdf of result.pdfs) {
    assert.ok(pdf instanceof File);
    assert.equal(pdf.type, 'application/pdf');
    assert.deepEqual(new Uint8Array(await pdf.arrayBuffer()), entries[pdf.name]);
  }
  assert.deepEqual(progress.filter((event) => event.status === 'saved').map((event) => [event.current, event.total, event.trackIndex]), [[1, 2, 2], [2, 2, 0]]);
  assert.equal(progress.find((event) => event.page === 1).trackIndex, 2);
});

test('invalid selections produce no render call, progress, or ZIP download', async () => {
  let calls = 0;
  const exportSelected = createExporter(async () => { calls += 1; return new Blob(); });
  for (const indices of [undefined, [], [0, 0], [-1], [3], [0.5], ['0'], new Array(1), [0, , 2], '0']) {
    const result = await exportSelected({ source, indices, onProgress: () => { calls += 1; } });
    assert.equal(result.blob, null);
    assert.equal(result.files.length, 0);
    assert.deepEqual(result.pdfs, []);
    assert.equal(typeof result.error, 'string');
  }
  assert.equal(calls, 0);
});

test('cancellation preserves completed PDFs as a partial ZIP', async () => {
  const controller = new AbortController();
  const result = await createExporter(renderer)({
    source, indices: [2, 0], signal: controller.signal,
    onProgress: (event) => { if (event.status === 'saved') controller.abort(); },
  });
  assert.equal(result.cancelled, true);
  assert.equal(result.error, null);
  assert.match(result.filename, /partial\.zip$/);
  assert.deepEqual(result.files, ['Song - 03 - Drums.pdf']);
  assert.deepEqual(result.pdfs.map(file => file.name), result.files);
  assert.deepEqual(new Uint8Array(await result.pdfs[0].arrayBuffer()), pdfBytes(2));
  assert.deepEqual(Object.keys(unzipSync(new Uint8Array(await result.blob.arrayBuffer()))), result.files);
});

test('a cancelled operation with no completed PDFs does not offer an empty ZIP', async () => {
  const controller = new AbortController();
  controller.abort();
  const result = await createExporter(renderer)({ source, indices: [0], signal: controller.signal });
  assert.equal(result.cancelled, true);
  assert.equal(result.error, null);
  assert.equal(result.blob, null);
  assert.deepEqual(result.files, []);
  assert.deepEqual(result.pdfs, []);
});

test('cancel settles while the shared PDF module is stalled and later retry remains usable', async (t) => {
  let completeModule;
  let rendered = 0;
  const ready = new Promise((resolve) => { completeModule = resolve; });
  const module = { renderTrackPdf: async (request) => { rendered += 1; return renderer(request); } };
  const exportSelected = createExporter(createLazyRenderer(() => ready));
  const controller = new AbortController();
  const pending = exportSelected({ source, indices: [0], signal: controller.signal });
  t.after(async () => { completeModule(module); await pending; });
  controller.abort();
  const result = await Promise.race([
    pending,
    new Promise((resolve) => setImmediate(() => resolve({ pending: true }))),
  ]);
  assert.equal(result.pending, undefined, 'Cancel must settle before the PDF module becomes ready');
  assert.equal(result.cancelled, true);
  assert.equal(result.blob, null);
  assert.equal(rendered, 0);
  assert.equal(getEventListeners(controller.signal, 'abort').length, 0);
  completeModule(module);
  const retryController = new AbortController();
  const retry = await exportSelected({ source, indices: [2], signal: retryController.signal });
  assert.equal(retry.error, null);
  assert.equal(retry.cancelled, false);
  assert.deepEqual(retry.files, ['Song - 03 - Drums.pdf']);
  assert.equal(rendered, 1);
  assert.equal(getEventListeners(retryController.signal, 'abort').length, 0);
});

test('render failure preserves previous PDFs and reports a partial ZIP honestly', async () => {
  const result = await createExporter(async (request) => {
    if (request.trackIndex === 0) throw new Error('Printer failed');
    return renderer(request);
  })({ source, indices: [2, 0] });
  assert.equal(result.cancelled, false);
  assert.match(result.error, /Printer failed/);
  assert.match(result.filename, /partial\.zip$/);
  assert.deepEqual(result.files, ['Song - 03 - Drums.pdf']);
  assert.deepEqual(result.pdfs.map(file => file.name), result.files);
  assert.deepEqual(new Uint8Array(await result.pdfs[0].arrayBuffer()), pdfBytes(2));
  assert.equal(Object.keys(unzipSync(new Uint8Array(await result.blob.arrayBuffer()))).length, 1);
});

test('ZIP packaging failure preserves every completed individual PDF', async () => {
  const result = await createExporter(renderer, () => { throw new Error('ZIP allocation failed'); })({ source, indices: [2, 0] });
  assert.equal(result.blob, null);
  assert.equal(result.cancelled, false);
  assert.match(result.error, /ZIP allocation failed/);
  assert.deepEqual(result.pdfs.map(file => file.name), ['Song - 03 - Drums.pdf', 'Song - 01 - Guitar.pdf']);
  assert.deepEqual(result.files, result.pdfs.map(file => file.name));
  assert.deepEqual(new Uint8Array(await result.pdfs[0].arrayBuffer()), pdfBytes(2));
  assert.deepEqual(new Uint8Array(await result.pdfs[1].arrayBuffer()), pdfBytes(0));
});

test('ZIP input read failure preserves already rendered PDF files', async (t) => {
  const read = t.mock.method(File.prototype, 'arrayBuffer', async () => { throw new Error('Read allocation failed'); });
  const result = await createExporter(renderer)({ source, indices: [2, 0] });
  read.mock.restore();
  assert.equal(result.blob, null);
  assert.match(result.error, /Read allocation failed/);
  assert.deepEqual(result.pdfs.map(file => file.name), result.files);
  assert.equal(result.pdfs.length, 2);
  assert.deepEqual(new Uint8Array(await result.pdfs[0].arrayBuffer()), pdfBytes(2));
  assert.deepEqual(new Uint8Array(await result.pdfs[1].arrayBuffer()), pdfBytes(0));
});

test('generated PDF budget rejects overflow before reading it and preserves earlier outputs', async () => {
  class OversizedPdf extends Blob {
    get size() { return 128 * 1024 * 1024 + 1; }
    arrayBuffer() { throw new Error('Over-budget PDF must not be read'); }
  }
  const result = await createExporter(async (request) => request.trackIndex === 0 ? new OversizedPdf() : renderer(request))({ source, indices: [2, 0] });
  assert.match(result.error, /128/);
  assert.deepEqual(result.files, ['Song - 03 - Drums.pdf']);
  assert.deepEqual(result.pdfs.map(file => file.name), result.files);
  assert.ok(result.blob instanceof Blob);
});

test('ZIP filenames sanitize path traversal, reserved names, and long Unicode tracks', async () => {
  const result = await createExporter(renderer)({
    source: { ...source, name: 'CON.gp5', trackNames: ['../AUX:<x>|?*\\ . ', '🎸베이스'.repeat(100), 'Drums'] },
    indices: [0, 1],
  });
  assert.equal(result.error, null);
  assert.match(result.filename, /^_CON/);
  assert.deepEqual(result.pdfs.map(file => file.name), result.files);
  for (const file of result.files) {
    assert.doesNotMatch(file, /[<>:"/\\|?*\u0000-\u001f]/);
    assert.ok(new TextEncoder().encode(file).length < 240);
  }
});
