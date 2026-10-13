export const MIN_BPM = 20;
export const MAX_BPM = 300;
export const DEFAULT_SETTINGS = Object.freeze({
  bpm: 120, subdivision: 1, sound: 'drum',
  accents: Object.freeze([true, false, false, false]), mute: false, volume: 0.65,
});

export function parseBpm(value) {
  const text = String(value).trim();
  if (!/^\d+$/.test(text)) return null;
  const bpm = Number(text);
  return Number.isInteger(bpm) && bpm >= MIN_BPM && bpm <= MAX_BPM ? bpm : null;
}

export function tickAt(settings, step) {
  const position = step % (4 * settings.subdivision);
  const beat = Math.floor(position / settings.subdivision);
  const part = position % settings.subdivision;
  return { beat, part, accented: part === 0 && settings.accents[beat], interval: 60 / settings.bpm / settings.subdivision };
}

export class TapSession {
  times = [];
  get count() { return this.times.length; }
  add(now) {
    if (this.finished(now) || (this.count && now - this.times.at(-1) < 100)) return false;
    this.times.push(now);
    return true;
  }
  remaining(now) {
    return this.count ? Math.max(0, (this.times[0] + 10000 - now) / 1000) : 10;
  }
  finished(now) { return this.count > 0 && now >= this.times[0] + 10000; }
  result() {
    if (this.count < 4) return null;
    const intervals = this.times.slice(1).map((time, index) => time - this.times[index]);
    const sorted = [...intervals].sort((a, b) => a - b);
    const middle = Math.floor(sorted.length / 2);
    const median = sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
    const steady = intervals.filter(interval => Math.abs(interval - median) / median < 0.2);
    if (steady.length < 3 || steady.length < intervals.length / 2) return null;
    return Math.round(60000 / (steady.reduce((sum, interval) => sum + interval, 0) / steady.length));
  }
}

function validSettings(value) {
  return value && parseBpm(value.bpm) === value.bpm && [1, 2, 3].includes(value.subdivision)
    && ['drum', 'melody'].includes(value.sound) && typeof value.mute === 'boolean'
    && Number.isFinite(value.volume) && value.volume >= 0 && value.volume <= 1
    && Array.isArray(value.accents) && value.accents.length === 4 && value.accents.every(item => typeof item === 'boolean');
}

export function encodeState(value) {
  const bytes = new TextEncoder().encode(JSON.stringify(value));
  return btoa(Array.from(bytes, byte => String.fromCharCode(byte)).join(''));
}

export function decodeState(encoded) {
  const bytes = Uint8Array.from(atob(encoded), char => char.charCodeAt(0));
  const value = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(bytes));
  if (!validSettings(value.settings) || !Array.isArray(value.songs) || value.songs.length > 100) {
    throw new Error('저장된 설정을 읽을 수 없습니다.');
  }
  const ids = new Set();
  for (const song of value.songs) {
    if (!validSettings(song) || typeof song.title !== 'string' || !song.title.trim() || song.title.length > 40
      || typeof song.id !== 'string' || !song.id || song.id.length > 100 || ids.has(song.id)) {
      throw new Error('저장된 곡을 읽을 수 없습니다.');
    }
    ids.add(song.id);
  }
  return value;
}
