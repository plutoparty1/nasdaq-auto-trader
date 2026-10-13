import { decodeState, encodeState, DEFAULT_SETTINGS } from './core.js';

const KEY = 'pulse_metronome_v1';
const MIGRATED_KEY = 'pulse_metronome_v1_local_migrated';
const onR1 = () => Boolean(window.PluginMessageHandler || window.closeWebView || window.TouchEventHandler
  || (/Android/i.test(navigator.userAgent) && window.innerWidth <= 240));

async function nativeStorage() {
  if (window.creationStorage?.plain) return window.creationStorage.plain;
  const deadline = performance.now() + (onR1() ? 2000 : 200);
  while (performance.now() < deadline) {
    await new Promise(resolve => setTimeout(resolve, 25));
    if (window.creationStorage?.plain) return window.creationStorage.plain;
  }
  if (onR1()) throw new Error('r1 저장소가 준비되지 않았습니다.');
  return null;
}

async function finishMigration(native) {
  try { window.localStorage.removeItem(KEY); }
  catch { await native.setItem(MIGRATED_KEY, btoa('1')); }
}

export class Repository {
  queue = Promise.resolve();
  native = null;
  async load() {
    this.native = await nativeStorage();
    let local = null;
    try { local = window.localStorage.getItem(KEY); }
    catch (error) { if (!this.native) throw error; }
    const stored = this.native ? await this.native.getItem(KEY) : local;
    if (this.native && local) {
      if (stored && await this.native.getItem(MIGRATED_KEY)) return decodeState(stored);
      const current = stored ? decodeState(stored) : null;
      let old;
      try { old = decodeState(local); }
      catch (error) { if (!current) throw error; }
      const songs = current ? [...current.songs] : [];
      for (const song of old?.songs ?? []) {
        if (!songs.some(saved => saved.id === song.id)) songs.push(song);
      }
      if (songs.length > 100) throw new Error('저장된 곡이 100곡을 넘습니다.');
      if (old && (!current || songs.length !== current.songs.length)) {
        const merged = { settings: current?.settings ?? old.settings, songs };
        await this.native.setItem(KEY, encodeState(merged));
        await finishMigration(this.native);
        return merged;
      }
      if (old) await finishMigration(this.native);
    }
    return stored ? decodeState(stored) : { settings: { ...DEFAULT_SETTINGS, accents: [...DEFAULT_SETTINGS.accents] }, songs: [] };
  }
  save(value) {
    const encoded = encodeState(value);
    const write = this.queue.then(async () => {
      if (this.native) await this.native.setItem(KEY, encoded);
      else window.localStorage.setItem(KEY, encoded);
    });
    this.queue = write.catch(() => undefined);
    return write;
  }
}
