export const MIN_BPM = 20;
export const MAX_BPM = 300;
export const DEFAULT_SETTINGS = Object.freeze({
  bpm: 120, subdivision: 1, sound: 'drum',
  accents: Object.freeze([true, false, false, false]), mute: false,
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
  count = 0;
  add(now) {
    const last = this.times.at(-1);
    if (last !== undefined && now - last < 100) return false;
    if (last !== undefined && now - last > 4000) { this.times = []; this.count = 0; }
    this.times.push(now);
    if (this.times.length > 5) this.times.shift();
    this.count++;
    return true;
  }
  result() {
    if (this.times.length < 2) return null;
    const intervals = this.times.length - 1;
    return Math.round(60000 * intervals / (this.times.at(-1) - this.times[0]));
  }
}

function validSettings(value) {
  return value && Number.isInteger(value.bpm) && parseBpm(value.bpm) === value.bpm && [1, 2, 3].includes(value.subdivision)
    && ['drum', 'melody'].includes(value.sound) && typeof value.mute === 'boolean'
    && Array.isArray(value.accents) && value.accents.length === 4 && value.accents.every(item => typeof item === 'boolean');
}

function settingsOnly(value) {
  const { bpm, subdivision, sound, accents, mute } = value;
  return { bpm, subdivision, sound, accents: [...accents], mute };
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
  return { settings: settingsOnly(value.settings), songs: value.songs.map(song => ({ ...settingsOnly(song), id: song.id, title: song.title })) };
}
