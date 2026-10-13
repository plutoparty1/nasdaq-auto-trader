import { TapSession, parseBpm } from './core.js';

export class TapController {
  session = new TapSession();
  active = false;
  result = null;
  constructor(updateTempo, complete) {
    this.updateTempo = updateTempo;
    this.pad = document.querySelector('#tap-pad');
    this.time = document.querySelector('#tap-time');
    this.instruction = document.querySelector('#tap-instruction');
    this.count = document.querySelector('#tap-count');
    this.applyButton = document.querySelector('#tap-apply');
    this.pad.addEventListener('pointerdown', event => {
      if (event.isPrimary && event.button === 0) { event.preventDefault(); this.add(); }
    });
    this.pad.addEventListener('click', event => { if (event.detail === 0) this.add(); });
    document.querySelector('#tap-reset').addEventListener('click', () => this.reset());
    this.applyButton.addEventListener('click', () => { if (!this.applyButton.disabled) complete(); });
  }
  add() {
    if (!this.session.add(performance.now())) return;
    this.active = true;
    this.result = this.session.result();
    this.count.textContent = `${this.session.count} ${this.session.count === 1 ? 'tap' : 'taps'}`;
    this.pad.querySelector('strong').textContent = this.result === null ? 'TAP' : String(this.result);
    this.time.textContent = this.result === null ? 'Tap again' : 'BPM';
    const usable = this.result !== null && parseBpm(this.result) !== null;
    this.applyButton.disabled = !usable;
    this.instruction.textContent = this.result === null ? 'Keep a steady beat.'
      : usable ? 'Tempo updates with every tap.' : 'Tempo is outside 20–300 BPM.';
    if (usable) this.updateTempo(this.result);
    this.pad.classList.add('hit');
    clearTimeout(this.hitTimer);
    this.hitTimer = window.setTimeout(() => this.pad.classList.remove('hit'), 80);
  }
  reset() {
    clearTimeout(this.hitTimer);
    this.session = new TapSession();
    this.active = false;
    this.result = null;
    this.count.textContent = '0 taps';
    this.instruction.textContent = 'Tap steadily to set the tempo.';
    this.pad.querySelector('strong').textContent = 'TAP';
    this.time.textContent = '';
    this.pad.classList.remove('hit');
    this.applyButton.disabled = true;
  }
}
