'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const test = require('node:test');
const { createPdfWriter, writeTrackPdf } = require('../storage.cjs');

async function outputFor(t, overrides = {}) {
  const folder = await fs.mkdtemp(path.join(os.tmpdir(), 'gp5-storage-'));
  assert.equal(path.dirname(path.resolve(folder)), path.resolve(os.tmpdir()));
  t.after(() => fs.rm(folder, { recursive: true, force: true }));
  return { folder, sourceName: 'Song.gp5', trackName: 'Guitar', trackIndex: 0, ...overrides };
}

test('creates numbered files and preserves every existing output on repeated export', async (t) => {
  const output = await outputFor(t);
  const first = await writeTrackPdf(output, Buffer.from('first'));
  const second = await writeTrackPdf(output, Buffer.from('second'));
  assert.equal(path.basename(first), 'Song - 01 - Guitar.pdf');
  assert.equal(path.basename(second), 'Song - 01 - Guitar (2).pdf');
  assert.equal(await fs.readFile(first, 'utf8'), 'first');
  assert.equal(await fs.readFile(second, 'utf8'), 'second');
});

test('keeps duplicate track names distinct by their original track numbers', async (t) => {
  const output = await outputFor(t);
  const files = await Promise.all([
    writeTrackPdf(output, Buffer.from('first')),
    writeTrackPdf({ ...output, trackIndex: 1 }, Buffer.from('second')),
  ]);
  assert.deepEqual(files.map((file) => path.basename(file)), ['Song - 01 - Guitar.pdf', 'Song - 02 - Guitar.pdf']);
});

test('sanitizes reserved names and separators without escaping the source folder', async (t) => {
  const output = await outputFor(t, { sourceName: 'CON.gp5', trackName: '../AUX:<Bass>|?*\\ . ' });
  const file = await writeTrackPdf(output, Buffer.from('safe'));
  assert.equal(path.dirname(file), output.folder);
  assert.match(path.basename(file), /^_CON - 01 - /);
  assert.doesNotMatch(path.basename(file), /[<>:"/\\|?*\u0000-\u001f]/);
  assert.doesNotMatch(path.basename(file), /[ .]\.pdf$/);
});

test('bounds multilingual filenames to a portable byte length', async (t) => {
  const output = await outputFor(t, { sourceName: `${'가'.repeat(150)}.gp5`, trackName: '🎸베이스'.repeat(100) });
  const file = await writeTrackPdf(output, Buffer.from('safe'));
  assert.ok(Buffer.byteLength(path.basename(file)) < 240);
  assert.equal(path.dirname(file), output.folder);
});

test('exclusive creation handles concurrent exports without overwriting either file', async (t) => {
  const output = await outputFor(t);
  const files = await Promise.all([
    writeTrackPdf(output, Buffer.from('first')),
    writeTrackPdf(output, Buffer.from('second')),
  ]);
  assert.equal(new Set(files).size, 2);
  assert.deepEqual((await Promise.all(files.map((file) => fs.readFile(file, 'utf8')))).sort(), ['first', 'second']);
});

test('removes only its newly created partial file after a write failure', async (t) => {
  const output = await outputFor(t);
  const existing = path.join(output.folder, 'Song - 01 - Guitar.pdf');
  await fs.writeFile(existing, 'keep');
  const writer = createPdfWriter({
    ...fs,
    async open(file, flags) {
      const handle = await fs.open(file, flags);
      return {
        close: () => handle.close(),
        async writeFile() {
          await handle.writeFile('partial');
          throw Object.assign(new Error('Disk full'), { code: 'ENOSPC' });
        },
      };
    },
  });
  await assert.rejects(writer(output, Buffer.from('new')), /Disk full/);
  assert.deepEqual(await fs.readdir(output.folder), [path.basename(existing)]);
  assert.equal(await fs.readFile(existing, 'utf8'), 'keep');
});

test('creates no output when cancellation already occurred', async (t) => {
  const output = await outputFor(t);
  const controller = new AbortController();
  controller.abort();
  await assert.rejects(writeTrackPdf(output, Buffer.from('new'), controller.signal), { name: 'AbortError' });
  assert.deepEqual(await fs.readdir(output.folder), []);
});

test('removes current output when cancellation arrives during a write', async (t) => {
  const output = await outputFor(t);
  const controller = new AbortController();
  const writer = createPdfWriter({
    ...fs,
    async open(file, flags) {
      const handle = await fs.open(file, flags);
      return {
        close: () => handle.close(),
        async writeFile(bytes) {
          await handle.writeFile(bytes);
          controller.abort();
        },
      };
    },
  });
  await assert.rejects(writer(output, Buffer.from('new'), controller.signal), { name: 'AbortError' });
  assert.deepEqual(await fs.readdir(output.folder), []);
});

test('propagates directory write errors without deleting any existing file', async (t) => {
  const output = await outputFor(t);
  const existing = path.join(output.folder, 'keep.pdf');
  await fs.writeFile(existing, 'keep');
  await assert.rejects(writeTrackPdf({ ...output, folder: path.join(output.folder, 'missing') }, Buffer.from('new')), { code: 'ENOENT' });
  assert.equal(await fs.readFile(existing, 'utf8'), 'keep');
});
