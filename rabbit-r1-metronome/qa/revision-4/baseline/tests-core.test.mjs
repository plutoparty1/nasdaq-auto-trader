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
test('live tap reports from the second tap and converges on a new tempo within four intervals', () => {
  const tap = new TapSession();
  tap.add(0);
  assert.equal(tap.result(), null);
  tap.add(750);
  assert.equal(tap.result(), 80);
  for (const time of [1500, 2250, 3000]) tap.add(time);
  for (const time of [3500, 4000, 4500, 5000]) tap.add(time);
  assert.equal(tap.result(), 120);
  assert.equal(tap.count, 9);
  assert.equal(tap.times.length, 5);
});
test('live tapping continues beyond ten seconds with bounded timing history', () => {
  const tap = new TapSession();
  for (let time = 0; time <= 20000; time += 500) assert.equal(tap.add(time), true);
  assert.equal(tap.count, 41);
  assert.equal(tap.result(), 120);
  assert.equal(tap.times.length, 5);
});
test('duplicate taps are ignored and a pause longer than four seconds starts a new series', () => {
  const tap = new TapSession();
  tap.add(0); tap.add(750);
  assert.equal(tap.add(800), false);
  assert.equal(tap.count, 2);
  assert.equal(tap.result(), 80);
  assert.equal(tap.add(4750), true);
  assert.equal(tap.count, 3);
  assert.equal(tap.add(8751), true);
  assert.equal(tap.count, 1);
  assert.equal(tap.result(), null);
  tap.add(9251);
  assert.equal(tap.result(), 120);
});
test('tap estimates outside playback range are measurable but rejected as playback BPM', () => {
  const tap = new TapSession();
  tap.add(0); tap.add(100);
  assert.equal(tap.result(), 600);
  assert.equal(parseBpm(tap.result()), null);
});
test('native Base64 storage round-trips Korean and symbols without corrupting titles', () => {
  const value = { settings: DEFAULT_SETTINGS, songs: [{ id: 'one', title: '봄날 🎵 <music1>', ...DEFAULT_SETTINGS, bpm: 80 }] };
  assert.deepEqual(decodeState(encodeState(value)), value);
});
test('legacy volume is removed without losing settings or saved song identity', () => {
  const song = { id: 'old-song', title: '기존 곡', ...DEFAULT_SETTINGS, bpm: 80, volume: 0 };
  const decoded = decodeState(encodeState({ settings: { ...DEFAULT_SETTINGS, volume: 0.42 }, songs: [song] }));
  assert.equal('volume' in decoded.settings, false);
  assert.equal('volume' in decoded.songs[0], false);
  assert.deepEqual(decoded.songs[0], { id: 'old-song', title: '기존 곡', ...DEFAULT_SETTINGS, bpm: 80 });
});
test('untrusted saved data is rejected rather than used as runtime settings', () => {
  for (const bad of ['garbage', encodeState({ settings: { bpm: -1 }, songs: [] }),
    encodeState({ settings: { ...DEFAULT_SETTINGS, bpm: null }, songs: [] }),
    encodeState({ settings: DEFAULT_SETTINGS, songs: [{ ...DEFAULT_SETTINGS, bpm: null, id: 'bad', title: '손상된 곡' }] }),
    encodeState({ settings: DEFAULT_SETTINGS, songs: [{}] })]) {
    assert.throws(() => decodeState(bad));
  }
});
