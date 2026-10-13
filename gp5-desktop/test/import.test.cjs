'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const test = require('node:test');
const { parseGp5 } = require('../import-score.cjs');

test('imports real GP5 fixture title and all tracks without modifying its bytes', async () => {
  const bytes = await fs.readFile(path.join(__dirname, 'fixtures', 'QA Trio.gp5'));
  const original = Buffer.from(bytes);
  const source = parseGp5(bytes, 'QA Trio.gp5');
  assert.equal(source.title, 'GP5 Runtime QA');
  assert.deepEqual(source.trackNames, ['Electric Guitar', 'Bass Guitar', 'Drum Kit']);
  assert.deepEqual(bytes, original);
});

test('rejects arbitrary data renamed as a GP5 file', () => {
  assert.throws(() => parseGp5(Buffer.from('Not a GP5 score'), 'broken.gp5'), /GP5/);
});

test('rejects truncated GP5 data instead of returning an incomplete track list', async () => {
  const bytes = await fs.readFile(path.join(__dirname, 'fixtures', 'QA Trio.gp5'));
  assert.throws(() => parseGp5(bytes.subarray(0, 60), 'broken.gp5'), /GP5/);
});

test('rejects other extensions before parsing', async () => {
  const bytes = await fs.readFile(path.join(__dirname, 'fixtures', 'QA Trio.gp5'));
  assert.throws(() => parseGp5(bytes, 'score.gpx'), /GP5/);
});

test('decodes CP949 instrument names before PDF filenames are constructed', async () => {
  const bytes = await fs.readFile(path.join(__dirname, 'fixtures', 'QA Trio.gp5'));
  const offset = bytes.indexOf(Buffer.from('Electric Guitar'));
  bytes.fill(0, offset, offset + 40);
  bytes[offset - 1] = 4;
  Buffer.from('b1e2c5b8', 'hex').copy(bytes, offset);
  const original = Buffer.from(bytes);
  const source = parseGp5(bytes, '한글.gp5');
  assert.deepEqual(source.trackNames, ['기타', 'Bass Guitar', 'Drum Kit']);
  assert.equal(source.encoding, 'euc-kr');
  assert.deepEqual(bytes, original);
});
