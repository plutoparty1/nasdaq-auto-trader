import { tickAt } from './core.js';

export class Metronome {
  context = null;
  master = null;
  playing = false;
  nodes = new Set();
  visuals = [];
  timer = null;
  frame = null;
  step = 0;
  constructor(settings, onTick, onFailure) {
    this.settings = settings;
    this.onTick = onTick;
    this.onFailure = onFailure;
  }
  now() { return this.context ? this.context.currentTime : performance.now() / 1000; }
  async unlock() {
    const Audio = window.AudioContext || window.webkitAudioContext;
    if (!Audio) {
      if (!this.settings.mute) throw new Error('Sound is unavailable on this device. Select Silent mode.');
      return;
    }
    if (!this.context) {
      this.context = new Audio({ latencyHint: 'interactive' });
      this.master = this.context.createGain();
      this.master.connect(this.context.destination);
      this.context.onstatechange = () => {
        if (this.playing && this.context.state !== 'running') {
          this.stop();
          this.onFailure('Audio stopped. Press the side button to play again.');
        }
      };
    }
    if (this.context.state !== 'running') await this.context.resume();
    if (this.context.state !== 'running') throw new Error('Could not start sound. Press the side button to retry.');
  }
  async start() {
    await this.unlock();
    this.stop();
    this.playing = true;
    this.step = 0;
    this.nextAt = this.now() + 0.035;
    this.updateMute();
    this.schedule();
    this.timer = window.setInterval(() => this.schedule(), 25);
    this.draw();
  }
  updateMute() {
    if (this.master) this.master.gain.setValueAtTime(this.settings.mute ? 0 : 1, this.now());
  }
  configure(settings) {
    const timingChanged = settings.bpm !== this.settings.bpm || settings.subdivision !== this.settings.subdivision
      || settings.sound !== this.settings.sound || settings.accents.some((accent, i) => accent !== this.settings.accents[i]);
    this.settings = settings;
    this.updateMute();
    if (this.playing && timingChanged) {
      this.clearNotes();
      this.step = 0;
      this.nextAt = this.now() + 0.035;
      this.schedule();
    }
  }
  schedule() {
    if (!this.playing) return;
    const now = this.now();
    if (this.nextAt < now - 0.05) {
      this.visuals = [];
      this.nextAt = now + 0.035;
      this.step = 0;
    }
    while (this.nextAt < now + 0.08) {
      const tick = tickAt(this.settings, this.step++);
      this.visuals.push({ ...tick, time: this.nextAt });
      if (this.context) this.sound(tick, this.nextAt);
      this.nextAt += tick.interval;
    }
  }
  sound(tick, time) {
    const context = this.context;
    const envelope = context.createGain();
    envelope.connect(this.master);
    const source = context.createOscillator();
    const drum = this.settings.sound === 'drum';
    source.type = drum ? 'triangle' : 'sine';
    const pitch = drum ? (tick.accented ? 150 : 1000) : (tick.accented ? 1320 : 660);
    source.frequency.setValueAtTime(pitch, time);
    const length = drum && tick.accented ? 0.08 : 0.045;
    if (drum && tick.accented) source.frequency.exponentialRampToValueAtTime(45, time + length);
    source.connect(envelope);
    source.onended = () => { envelope.disconnect(); source.disconnect(); this.nodes.delete(source); };
    envelope.gain.setValueAtTime(0.0001, time);
    envelope.gain.exponentialRampToValueAtTime(tick.accented ? 0.65 : 0.3, time + 0.002);
    envelope.gain.exponentialRampToValueAtTime(0.0001, time + length);
    this.nodes.add(source);
    source.start(time);
    source.stop(time + length + 0.005);
  }
  draw() {
    if (!this.playing) return;
    let latest;
    while (this.visuals[0]?.time <= this.now()) latest = this.visuals.shift();
    if (latest) this.onTick(latest);
    this.frame = requestAnimationFrame(() => this.draw());
  }
  clearNotes() {
    this.visuals = [];
    for (const node of this.nodes) node.stop();
    this.nodes.clear();
  }
  stop() {
    this.playing = false;
    clearInterval(this.timer);
    cancelAnimationFrame(this.frame);
    this.clearNotes();
  }
}
