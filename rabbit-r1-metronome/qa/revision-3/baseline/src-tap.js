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
    this.count.textContent = `${this.session.count}회`;
    this.pad.querySelector('strong').textContent = this.result === null ? 'TAP' : String(this.result);
    this.time.textContent = this.result === null ? '한 번 더 탭하세요' : 'BPM · 실시간';
    const usable = this.result !== null && parseBpm(this.result) !== null;
    this.applyButton.disabled = !usable;
    this.instruction.textContent = this.result === null ? '같은 간격으로 계속 탭하세요.'
      : usable ? '탭할 때마다 템포가 반영돼요.' : '측정값은 20–300 BPM 밖입니다.';
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
    this.count.textContent = '0회';
    this.instruction.textContent = '원하는 박자로 계속 탭하세요.';
    this.pad.querySelector('strong').textContent = 'TAP';
    this.time.textContent = '실시간 BPM 측정';
    this.pad.classList.remove('hit');
    this.applyButton.disabled = true;
  }
}
