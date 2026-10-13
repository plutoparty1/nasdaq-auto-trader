'use strict';

const assert = require('node:assert/strict');
const { test } = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const { importer, Settings } = require('@coderline/alphatab');
const { detectGp5Encoding } = require('../encoding.cjs');
const { makeKoreanGp5 } = require('./fixtures/korean-score.cjs');

function load(bytes, encoding) {
  const settings = new Settings();
  settings.importer.encoding = encoding;
  return importer.ScoreLoader.loadScoreFromBytes(bytes, settings);
}

function assertDecoded(fixture, expectedEncoding) {
  const encoding = detectGp5Encoding(fixture.bytes);
  assert.equal(encoding, expectedEncoding);
  const score = load(fixture.bytes, encoding);
  assert.equal(score.title, fixture.title);
  assert.deepEqual(score.tracks.map(track => track.name), fixture.trackNames);
  assert.equal(score.tracks[0].staves[0].bars[0].voices[0].beats[0].text, fixture.beatText);
  assert.equal(score.masterBars.length, 1);
}

test('ASCII GP5 remains UTF-8', () => {
  const bytes = fs.readFileSync(path.join(__dirname, 'fixtures/QA Trio.gp5'));
  assert.equal(detectGp5Encoding(bytes), 'utf-8');
});

test('CP949 title, track names and beat text decode without replacement characters', () => {
  assertDecoded(makeKoreanGp5('euc-kr'), 'euc-kr');
});

test('extended CP949 syllables are supported by the bundled Electron runtime', () => {
  assertDecoded(makeKoreanGp5('euc-kr', { trackNames: ['리드 기타 뷁', '베이스', '드럼'] }), 'euc-kr');
});

test('valid UTF-8 Korean title, track names and beat text remain UTF-8', () => {
  assertDecoded(makeKoreanGp5('utf-8'), 'utf-8');
});

test('literal U+FFFD and emoji in valid UTF-8 are preserved', () => {
  assertDecoded(makeKoreanGp5('utf-8', {
    title: '한글 제목 � 😀', trackNames: ['기타 �', '베이스', '드럼'],
  }), 'utf-8');
});

test('derived shortName cannot invalidate an intact UTF-8 track name', () => {
  const fixture = makeKoreanGp5('utf-8', { trackNames: ['가나다라마바사아자차', '베이스', '드럼'] });
  const probe = load(fixture.bytes, 'windows-1252');
  assert.equal(probe.tracks[0].shortName.length, 10);
  assertDecoded(fixture, 'utf-8');
});

test('Korean beat text alone can identify CP949 when headings are ASCII', () => {
  assertDecoded(makeKoreanGp5('euc-kr', {
    title: 'ASCII title', trackNames: ['Guitar', 'Bass', 'Drums'],
  }), 'euc-kr');
});

test('legacy Western text does not trigger a Korean fallback', () => {
  const fixture = makeKoreanGp5('windows-1252', {
    title: 'Café Élégant', trackNames: ['Guitàr', 'Bass', 'Drums'], beatText: 'Western text',
  });
  assert.equal(detectGp5Encoding(fixture.bytes), 'utf-8');
});
