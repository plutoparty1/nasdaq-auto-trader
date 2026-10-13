import QRCode from 'qrcode';
const form = document.querySelector('#install-form');
const message = document.querySelector('#message');
const download = document.querySelector('#download-qr');
let canvas;
form.addEventListener('submit', async event => {
  event.preventDefault();
  const title = document.querySelector('#creation-title').value.trim();
  let url;
  try { url = new URL(document.querySelector('#app-url').value.trim()); }
  catch { message.textContent = '올바른 HTTPS 주소를 입력하세요.'; return; }
  if (url.protocol !== 'https:' || ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname) || url.username || url.password) {
    message.textContent = 'r1에서 접속할 수 있는 공개 HTTPS 주소를 입력하세요.';
    return;
  }
  if (!title) { message.textContent = '앱 이름을 입력하세요.'; return; }
  const payload = { title, url: url.href, description: '4/4, 8비트, 셋잇단음표, 10초 탭 템포와 곡 저장', iconUrl: '', themeColor: '#FE5000' };
  try {
    const next = document.createElement('canvas');
    await QRCode.toCanvas(next, JSON.stringify(payload), { width: 300, margin: 4, errorCorrectionLevel: 'M', color: { dark: '#000000', light: '#ffffff' } });
    canvas = next;
    canvas.setAttribute('role', 'img');
    canvas.setAttribute('aria-label', 'rabbit r1 Creation 설치 QR 코드');
    document.querySelector('#qr').replaceChildren(canvas);
    document.querySelector('#payload').textContent = JSON.stringify(payload, null, 2);
    message.textContent = 'r1의 creations에서 add via QR code를 선택해 스캔하세요.';
    download.disabled = false;
  } catch { message.textContent = 'QR을 만들지 못했습니다. 주소 길이를 줄여 다시 시도하세요.'; }
});
download.addEventListener('click', () => {
  if (!canvas) return;
  const link = document.createElement('a');
  link.download = 'pulse-r1-install-qr.png';
  link.href = canvas.toDataURL('image/png');
  link.click();
});
