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
      if (!this.settings.mute) throw new Error('이 기기에서 소리를 사용할 수 없습니다. 무음 모드를 선택하세요.');
      return;
    }
    if (!this.context) {
      this.context = new Audio({ latencyHint: 'interactive' });
      this.master = this.context.createGain();
      this.master.connect(this.context.destination);
      const length = Math.floor(this.context.sampleRate * 0.04);
      this.noise = this.context.createBuffer(1, length, this.context.sampleRate);
      const data = this.noise.getChannelData(0);
      for (let i = 0; i < data.length; i++) data[i] = Math.random() * 2 - 1;
      this.context.onstatechange = () => {
        if (this.playing && this.context.state !== 'running') {
          this.stop();
          this.onFailure('오디오가 중단되었습니다. 다시 재생하세요.');
        }
      };
    }
    if (this.context.state !== 'running') await this.context.resume();
    if (this.context.state !== 'running') throw new Error('소리를 시작할 수 없습니다. 다시 재생하세요.');
  }
  async start() {
    await this.unlock();
    this.stop();
    this.playing = true;
    this.step = 0;
    this.nextAt = this.now() + 0.035;
    this.updateVolume();
    this.schedule();
    this.timer = window.setInterval(() => this.schedule(), 25);
    this.draw();
  }
  updateVolume() {
    if (this.master) this.master.gain.setValueAtTime(this.settings.mute ? 0 : this.settings.volume, this.now());
  }
  configure(settings) {
    const timingChanged = settings.bpm !== this.settings.bpm || settings.subdivision !== this.settings.subdivision
      || settings.sound !== this.settings.sound || settings.accents.some((accent, i) => accent !== this.settings.accents[i]);
    this.settings = settings;
    this.updateVolume();
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
    let source;
    let length;
    if (this.settings.sound === 'drum' && tick.part > 0) {
      source = context.createBufferSource();
      source.buffer = this.noise;
      const highpass = context.createBiquadFilter();
      highpass.type = 'highpass';
      highpass.frequency.value = 7000;
      source.connect(highpass);
      highpass.connect(envelope);
      length = 0.035;
      source.onended = () => { highpass.disconnect(); envelope.disconnect(); source.disconnect(); this.nodes.delete(source); };
    } else {
      source = context.createOscillator();
      source.type = this.settings.sound === 'melody' ? 'sine' : 'triangle';
      const pitch = this.settings.sound === 'melody' ? [523.25, 659.25, 783.99, 659.25][tick.beat] : (tick.accented ? 150 : 1000);
      source.frequency.setValueAtTime(tick.part ? pitch * 0.5 : pitch, time);
      length = this.settings.sound === 'drum' && tick.accented ? 0.08 : 0.045;
      if (this.settings.sound === 'drum' && tick.accented) source.frequency.exponentialRampToValueAtTime(45, time + length);
      source.connect(envelope);
      source.onended = () => { envelope.disconnect(); source.disconnect(); this.nodes.delete(source); };
    }
    const level = tick.accented ? 0.65 : tick.part ? 0.12 : 0.3;
    envelope.gain.setValueAtTime(0.0001, time);
    envelope.gain.exponentialRampToValueAtTime(level, time + 0.002);
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
