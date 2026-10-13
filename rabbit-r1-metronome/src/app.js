import { DEFAULT_SETTINGS, MIN_BPM, MAX_BPM, parseBpm } from './core.js';
import { Repository } from './storage.js';
import { Metronome } from './audio.js';
import { TapController } from './tap.js';
import { Library } from './library.js';

const $ = selector => document.querySelector(selector);
const all = selector => document.querySelectorAll(selector);
const state = { settings: { ...DEFAULT_SETTINGS, accents: [...DEFAULT_SETTINGS.accents] }, songs: [] };
const repository = new Repository();
let page = 'home';
let ready = false;
let storageReady = false;
let saveTimer;
let statusTimer;
let flashTimer;
let pendingStart = false;
let startVersion = 0;
let bpmDraft = '120';

function notify(message) {
  $('#status').textContent = message;
  $('#status').hidden = false;
  clearTimeout(statusTimer);
  statusTimer = window.setTimeout(() => { $('#status').hidden = true; }, 3000);
}

const engine = new Metronome(state.settings, tick => {
  all('[data-beat]').forEach(button => {
    button.classList.toggle('playing', Number(button.dataset.beat) === tick.beat);
    button.classList.toggle('subbeat', Number(button.dataset.beat) === tick.beat && tick.part > 0);
  });
  if ((state.settings.mute || state.settings.flashWithSound) && tick.part === 0) {
    $('#app').classList.remove('flash');
    void $('#app').offsetWidth;
    $('#app').classList.add('flash');
    clearTimeout(flashTimer);
    flashTimer = window.setTimeout(() => $('#app').classList.remove('flash'), 110);
  }
}, message => { refreshTransport(); notify(message); });

function refreshTransport() {
  $('#app').classList.toggle('running', engine.playing);
  if (!engine.playing) {
    all('[data-beat]').forEach(button => button.classList.remove('playing', 'subbeat'));
    $('#app').classList.remove('flash');
  }
}

function stop() {
  startVersion++;
  pendingStart = false;
  engine.stop();
  refreshTransport();
}

async function togglePlayback() {
  if (!ready) return;
  if (engine.playing || pendingStart) { stop(); return; }
  if (tap.active) tap.reset();
  const version = ++startVersion;
  pendingStart = true;
  refreshTransport();
  try {
    await engine.unlock();
    if (version !== startVersion || document.hidden) return;
    await engine.start();
    if (version !== startVersion || document.hidden) { engine.stop(); return; }
    if (page !== 'home') notify('Playing');
  } catch (error) { if (version === startVersion) notify(error.message); }
  finally {
    if (version === startVersion) { pendingStart = false; refreshTransport(); }
  }
}

function selectPage(next) {
  if (page === 'tap' && next !== 'tap' && tap.active) tap.reset();
  if (next === 'tap' && page !== 'tap') stop();
  page = next;
  all('.page').forEach(section => { section.hidden = section.id !== next; });
  all('[data-page]').forEach(button => {
    if (button.dataset.page === next) button.setAttribute('aria-current', 'page');
    else button.removeAttribute('aria-current');
  });
  if (next !== 'library') library.confirming = null;
  if (next === 'library') library.render();
}

function refreshSettings() {
  const settings = state.settings;
  $('#bpm').value = settings.bpm;
  bpmDraft = $('#bpm').value;
  $('#bpm').removeAttribute('aria-invalid');
  all('[data-sub]').forEach(button => button.setAttribute('aria-pressed', String(Number(button.dataset.sub) === settings.subdivision)));
  all('[data-sound]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.sound === settings.sound)));
  all('[data-beat]').forEach(button => button.setAttribute('aria-pressed', String(settings.accents[Number(button.dataset.beat)])));
  $('#mute').setAttribute('aria-pressed', String(settings.mute));
  $('#mute').textContent = settings.mute ? 'Silent' : 'Sound';
  $('#flash-with-sound').checked = settings.flashWithSound;
}

function persist() {
  clearTimeout(saveTimer);
  if (!storageReady) return Promise.reject(new Error('Storage is unavailable.'));
  return repository.save(state);
}

function changeSettings(patch) {
  if (!ready) return;
  state.settings = { ...state.settings, ...patch };
  engine.configure(state.settings);
  if (!state.settings.mute && !state.settings.flashWithSound) {
    clearTimeout(flashTimer);
    $('#app').classList.remove('flash');
  }
  refreshSettings();
  clearTimeout(saveTimer);
  if (storageReady) saveTimer = window.setTimeout(() => { void persist().catch(() => notify('Could not save settings. Change a setting to retry.')); }, 150);
}

function bump(amount) {
  if (!ready) return;
  changeSettings({ bpm: Math.min(MAX_BPM, Math.max(MIN_BPM, state.settings.bpm + amount)) });
}

function applyInput() {
  const bpm = parseBpm($('#bpm').value);
  if (bpm === null) {
    $('#bpm').setAttribute('aria-invalid', 'true');
    notify('Enter a whole BPM from 20 to 300.');
    return;
  }
  changeSettings({ bpm });
}

const tap = new TapController(bpm => changeSettings({ bpm }), () => selectPage('home')); 
const library = new Library(state, persist, song => {
  const { bpm, subdivision, sound, accents, mute, flashWithSound } = song;
  changeSettings({ bpm, subdivision, sound, accents: [...accents], mute, flashWithSound });
  selectPage('home');
}, notify);

$('#minus').addEventListener('click', () => bump(-1));
$('#plus').addEventListener('click', () => bump(1));
$('#bpm').addEventListener('change', applyInput);
$('#bpm').addEventListener('keydown', event => {
  if (!event.ctrlKey && !event.metaKey && event.key.length === 1 && /[^0-9]/.test(event.key)) event.preventDefault();
  if (event.key === 'Enter') { applyInput(); $('#bpm').blur(); }
});
$('#bpm').addEventListener('beforeinput', event => { if (event.data && /[^0-9]/.test(event.data)) event.preventDefault(); });
$('#bpm').addEventListener('paste', event => { if (/[^0-9]/.test(event.clipboardData.getData('text'))) event.preventDefault(); });
$('#bpm').addEventListener('input', event => {
  const input = event.target;
  if (input.validity.badInput || !/^[0-9]{0,3}$/.test(input.value)) input.value = bpmDraft;
  else bpmDraft = input.value;
});
all('[data-page]').forEach(button => button.addEventListener('click', () => selectPage(button.dataset.page)));
all('[data-sub]').forEach(button => button.addEventListener('click', () => {
  const subdivision = Number(button.dataset.sub);
  changeSettings({ subdivision, accents: subdivision === 1 ? [true, false, false, false] : [true, true, true, true] });
}));
all('[data-sound]').forEach(button => button.addEventListener('click', () => changeSettings({ sound: button.dataset.sound })));
all('[data-beat]').forEach(button => button.addEventListener('click', () => {
  const accents = [...state.settings.accents];
  const beat = Number(button.dataset.beat);
  accents[beat] = !accents[beat];
  changeSettings({ accents });
}));
$('#mute').addEventListener('click', () => changeSettings({ mute: !state.settings.mute }));
$('#flash-with-sound').addEventListener('change', event => changeSettings({ flashWithSound: event.target.checked }));
window.addEventListener('scrollUp', () => bump(-1));
window.addEventListener('scrollDown', () => bump(1));
window.addEventListener('sideClick', () => void togglePlayback());
window.addEventListener('keydown', event => {
  if (event.target.closest('input, textarea, select, [contenteditable=true]') || event.repeat) return;
  if (event.key === 'ArrowUp' || event.key === 'ArrowDown') { event.preventDefault(); bump(event.key === 'ArrowUp' ? 1 : -1); }
});
$('#home').addEventListener('wheel', event => { event.preventDefault(); if (event.deltaY) bump(event.deltaY < 0 ? -1 : 1); }, { passive: false });
function suspend() {
  stop();
  if (tap.active) tap.reset();
  if (saveTimer && storageReady) void persist().catch(() => notify('Could not save the latest settings.'));
}
document.addEventListener('visibilitychange', () => { if (document.hidden) suspend(); });
window.addEventListener('pagehide', suspend);

try {
  const loaded = await repository.load();
  state.settings = loaded.settings;
  state.songs = loaded.songs;
  storageReady = true;
} catch {
  storageReady = false;
  $('#save-song').disabled = true;
  notify('Could not read storage. Reload and try again.');
}
engine.configure(state.settings);
ready = true;
$('#app').dataset.ready = 'true';
$('#save-song').disabled = !storageReady;
refreshSettings();
refreshTransport();
library.render();
