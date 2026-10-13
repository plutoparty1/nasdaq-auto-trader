import assert from 'node:assert/strict';
import test from 'node:test';
import { DEFAULT_SETTINGS, parseBpm, tickAt, TapSession, encodeState, decodeState } from '../src/core.js';

test('tempo accepts whole BPM from 20 to 300 and rejects invalid text', () => {
  for (const bpm of [20, 80, 120, 300]) assert.equal(parseBpm(String(bpm)), bpm);
  for (const bad of ['', ' ', '0', '19', '301', '80.5', '8e1', 'abc']) assert.equal(parseBpm(bad), null);
});
test('4/4 quarter, eighth, triplet ticks preserve the quarter tempo and accents', () => {
  for (const subdivision of [1, 2, 3]) {
    const settings = { ...DEFAULT_SETTINGS, bpm: 80, subdivision, accents: [true, false, true, false] };
    const ticks = Array.from({ length: 4 * subdivision }, (_, step) => tickAt(settings, step));
    assert.equal(ticks.length, 4 * subdivision);
    assert.equal(ticks.filter(t => t.accented).length, 2);
    assert.equal(ticks[0].interval * subdivision, 0.75);
    assert.equal(ticks.at(-1).beat, 3);
    assert.equal(tickAt(settings, ticks.length).beat, 0);
  }
});
test('tap window lasts ten seconds from first tap and measures 80 BPM', () => {
  const tap = new TapSession();
  for (let time = 1000; time < 11000; time += 750) tap.add(time);
  assert.equal(tap.remaining(1000), 10);
  assert.equal(tap.finished(10999), false);
  assert.equal(tap.finished(11000), true);
  assert.equal(tap.add(11000), false);
  assert.equal(tap.result(), 80);
});
test('insufficient taps and duplicate taps do not create a misleading result', () => {
  const tap = new TapSession();
  assert.equal(tap.result(), null);
  tap.add(0); tap.add(500); tap.add(530); tap.add(1000);
  assert.equal(tap.count, 3);
  assert.equal(tap.result(), null);
  tap.add(1500);
  assert.equal(tap.result(), 120);
});
test('a missed tap or accidental tap is excluded using the median interval', () => {
  const tap = new TapSession();
  for (const time of [0, 750, 1500, 3000, 3750, 3900, 4500, 5250, 6000]) tap.add(time);
  assert.equal(tap.result(), 80);
});
test('native Base64 storage round-trips Korean and symbols without corrupting titles', () => {
  const value = { settings: DEFAULT_SETTINGS, songs: [{ id: 'one', title: '봄날 🎵 <music1>', ...DEFAULT_SETTINGS, bpm: 80 }] };
  assert.deepEqual(decodeState(encodeState(value)), value);
});
test('untrusted saved data is rejected rather than used as runtime settings', () => {
  for (const bad of ['garbage', encodeState({ settings: { bpm: -1 }, songs: [] }), encodeState({ settings: DEFAULT_SETTINGS, songs: [{}] })]) {
    assert.throws(() => decodeState(bad));
  }
});
