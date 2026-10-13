import { loadGp5 } from './import-score.js';
import { exportSelected } from './export-score.js';
import { clearDownloads, showResult, setDownloadsBusy } from './download-results.js';

const byId = id => document.getElementById(id);
const fileInput = byId('file-input');
const tracks = byId('tracks');
const selectAll = byId('select-all');
const status = byId('status');
const progress = byId('progress');
let source = null;
let operation = null;

function selectedIndices() {
  return [...tracks.querySelectorAll('.track-check:checked')].map(input => Number(input.value));
}

function showError(message) {
  byId('error').textContent = message || '';
  byId('error').hidden = !message;
}

function refreshControls() {
  const busy = operation !== null;
  fileInput.disabled = busy;
  byId('choose').disabled = busy;
  byId('convert').disabled = busy || selectedIndices().length === 0;
  selectAll.disabled = busy || !source;
  for (const checkbox of tracks.querySelectorAll('.track-check')) checkbox.disabled = busy;
  byId('cancel').hidden = !busy;
  byId('cancel').disabled = operation?.controller.signal.aborted ?? false;
  setDownloadsBusy(busy);
  tracks.setAttribute('aria-busy', String(busy));
}

function selectionChanged() {
  if (!source) return;
  const count = selectedIndices().length;
  const total = source.trackNames.length;
  selectAll.checked = count === total;
  selectAll.indeterminate = count > 0 && count < total;
  byId('track-count').textContent = `${count}/${total}개 선택`;
  for (const row of tracks.children) {
    row.querySelector('.track-state').textContent = row.querySelector('.track-check').checked ? '준비됨' : '선택 안 함';
  }
  clearDownloads();
  status.textContent = count ? `전체 ${total}개 중 ${count}개 악기를 PDF로 만들 준비가 됐습니다.` : 'PDF로 만들 악기를 하나 이상 선택해 주세요.';
  refreshControls();
}

function showSource(loaded) {
  source = loaded;
  byId('file-name').textContent = loaded.name;
  byId('score-title').textContent = loaded.title ? `악보: ${loaded.title}` : '';
  byId('score-title').hidden = !loaded.title;
  byId('empty-state').hidden = true;
  byId('select-all-control').hidden = false;
  tracks.replaceChildren();
  tracks.hidden = false;
  loaded.trackNames.forEach((name, index) => {
    const row = document.createElement('li');
    const label = document.createElement('label');
    label.className = 'track-option';
    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.className = 'track-check';
    checkbox.value = String(index);
    checkbox.checked = true;
    const number = document.createElement('span');
    number.className = 'track-number';
    number.textContent = String(index + 1).padStart(2, '0');
    const nameLabel = document.createElement('span');
    nameLabel.className = 'track-name';
    nameLabel.textContent = name;
    const state = document.createElement('span');
    state.className = 'track-state';
    label.append(checkbox, number, nameLabel);
    row.append(label, state);
    tracks.append(row);
  });
  selectionChanged();
}

async function readFile(file) {
  if (!file || operation) return;
  const current = { kind: 'loading', controller: new AbortController() };
  operation = current;
  showError(null);
  refreshControls();
  progress.hidden = false;
  progress.removeAttribute('value');
  status.textContent = '악보를 읽고 있습니다.';
  try {
    if (!/\.gp5$/i.test(file.name)) throw new Error('GP5 파일을 선택해 주세요.');
    if (file.size === 0 || file.size > 64 * 1024 * 1024) throw new Error('내용이 있는 64 MB 이하의 GP5 파일을 선택해 주세요.');
    const loaded = await loadGp5(file);
    if (operation !== current || current.controller.signal.aborted) return;
    showSource(loaded);
  } catch (error) {
    if (operation !== current) return;
    showError(error instanceof Error ? error.message : '악보를 읽지 못했습니다.');
    status.textContent = '파일을 확인한 뒤 다시 선택해 주세요.';
  } finally {
    if (operation === current) {
      operation = null;
      progress.hidden = true;
      refreshControls();
    }
  }
}

async function convert() {
  const indices = selectedIndices();
  if (operation || !source || indices.length === 0) return;
  const current = { kind: 'exporting', controller: new AbortController() };
  operation = current;
  clearDownloads();
  showError(null);
  refreshControls();
  progress.max = indices.length;
  progress.value = 0;
  progress.hidden = false;
  status.textContent = '변환에 필요한 파일과 악보를 준비하고 있습니다.';
  for (const row of tracks.children) {
    row.querySelector('.track-state').textContent = row.querySelector('.track-check').checked ? '대기 중' : '선택 안 함';
  }
  try {
    const result = await exportSelected({ source, indices, signal: current.controller.signal, onProgress(event) {
      if (operation !== current || !indices.includes(event.trackIndex)) return;
      const state = tracks.children[event.trackIndex].querySelector('.track-state');
      if (event.status === 'saved') { state.textContent = '완료'; progress.value = event.current; }
      if (event.status === 'rendering') {
        state.textContent = '변환 중';
        status.textContent = `${event.current}/${event.total} · ${event.track} 악보를 만드는 중입니다.`;
      }
    } });
    showError(result.error);
    showResult(result, indices.length);
    const downloadable = result.pdfs.length > 0;
    if (downloadable && !result.blob) status.textContent = 'ZIP을 만들지 못했습니다. 완성된 PDF는 각각 저장할 수 있습니다.';
    else if (result.cancelled) status.textContent = downloadable ? `변환을 취소했습니다. 완성된 PDF ${result.files.length}개를 저장하세요.` : '변환을 취소했습니다. 완성된 PDF가 없습니다.';
    else if (result.error) status.textContent = downloadable ? `일부 악기의 변환을 마치지 못했습니다. 완성된 PDF ${result.files.length}개를 저장하세요.` : '변환을 마치지 못했습니다. 다시 시도해 주세요.';
    else status.textContent = downloadable ? `선택한 악기 ${result.files.length}개의 PDF를 만들었습니다. 개별 PDF 또는 ZIP을 저장해 주세요.` : '다운로드할 PDF를 만들지 못했습니다. 다시 시도해 주세요.';
  } catch (error) {
    showError(error instanceof Error ? error.message : 'PDF를 만들지 못했습니다.');
    status.textContent = '변환을 마치지 못했습니다. 다시 시도해 주세요.';
  } finally {
    for (const index of indices) {
      const state = tracks.children[index].querySelector('.track-state');
      if (state.textContent !== '완료') state.textContent = '미완료';
    }
    operation = null;
    progress.hidden = true;
    refreshControls();
  }
}

byId('choose').addEventListener('click', () => { if (!operation) fileInput.click(); });
fileInput.addEventListener('change', () => {
  const file = fileInput.files?.[0];
  fileInput.value = '';
  void readFile(file);
});
tracks.addEventListener('change', () => { if (!operation) selectionChanged(); });
selectAll.addEventListener('change', () => {
  if (operation) return;
  for (const checkbox of tracks.querySelectorAll('.track-check')) checkbox.checked = selectAll.checked;
  selectionChanged();
});
byId('convert').addEventListener('click', () => { void convert(); });
byId('cancel').addEventListener('click', () => {
  if (!operation) return;
  operation.controller.abort();
  byId('cancel').disabled = true;
  status.textContent = '변환을 취소하고 완성된 파일을 정리하고 있습니다.';
  if (operation.kind === 'loading') {
    operation = null;
    progress.hidden = true;
    status.textContent = '파일 읽기를 취소했습니다.';
    refreshControls();
  }
});
window.addEventListener('pagehide', event => {
  if (!event.persisted) { operation?.controller.abort(); clearDownloads(); }
});
refreshControls();
