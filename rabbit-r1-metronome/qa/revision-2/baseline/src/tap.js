import { TapSession, parseBpm } from './core.js';

export class TapController {
  session = new TapSession();
  active = false;
  result = null;
  constructor(apply) {
    this.apply = apply;
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
    this.applyButton.addEventListener('click', () => { if (this.result !== null) this.apply(this.result); });
  }
  add() {
    if (this.session.finished(performance.now())) {
      if (this.active) this.finish();
      return;
    }
    if (!this.session.add(performance.now())) return;
    if (!this.active) {
      this.active = true;
      this.instruction.textContent = '같은 간격으로 계속 탭하세요.';
      this.pad.querySelector('strong').textContent = 'TAP';
      this.timer = window.setInterval(() => this.update(), 100);
      this.deadline = window.setTimeout(() => this.finish(), 10000);
    }
    this.count.textContent = `${this.session.count}회`;
    this.pad.classList.add('hit');
    clearTimeout(this.hitTimer);
    this.hitTimer = window.setTimeout(() => this.pad.classList.remove('hit'), 80);
    this.update();
  }
  update() {
    if (this.session.finished(performance.now())) { this.finish(); return; }
    this.time.textContent = `${this.session.remaining(performance.now()).toFixed(1)}초 남음`;
  }
  finish() {
    if (!this.active) return;
    this.active = false;
    clearInterval(this.timer);
    clearTimeout(this.deadline);
    this.result = this.session.result();
    this.pad.querySelector('strong').textContent = this.result === null ? '다시 탭' : String(this.result);
    this.time.textContent = this.result === null ? '4회 이상 일정하게 탭하세요' : 'BPM · 측정 완료';
    const usable = this.result !== null && parseBpm(this.result) !== null;
    this.applyButton.disabled = !usable;
    this.instruction.textContent = this.result === null ? '충분한 일정 간격을 측정하지 못했어요.'
      : usable ? '측정한 템포를 적용할 수 있어요.' : '측정값은 재생 범위 20–300 BPM 밖입니다.';
  }
  reset() {
    clearInterval(this.timer);
    clearTimeout(this.deadline);
    clearTimeout(this.hitTimer);
    this.session = new TapSession();
    this.active = false;
    this.result = null;
    this.count.textContent = '0회';
    this.instruction.textContent = '첫 탭부터 10초간 박자를 탭하세요.';
    this.pad.querySelector('strong').textContent = 'TAP';
    this.time.textContent = '10초 측정';
    this.pad.classList.remove('hit');
    this.applyButton.disabled = true;
  }
}
