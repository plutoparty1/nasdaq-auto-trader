const byId = (id) => document.getElementById(id);
const choose = byId('choose');
const convert = byId('convert');
const cancel = byId('cancel');
const status = byId('status');
const error = byId('error');
const progress = byId('progress');
const selectAll = byId('select-all');
let source = null;
let busy = false;
let activeTrackIndices = [];

function showError(message) {
  error.textContent = message || '';
  error.hidden = !message;
}

function selectedTrackIndices() {
  return [...document.querySelectorAll('.track-check:checked')].map(input => Number(input.value));
}

function updateSelection() {
  const indices = selectedTrackIndices();
  const total = source.trackNames.length;
  selectAll.checked = indices.length === total;
  selectAll.indeterminate = indices.length > 0 && indices.length < total;
  byId('track-count').textContent = `${indices.length}/${total}개 선택`;
  convert.disabled = busy || indices.length === 0;
  status.textContent = indices.length
    ? `전체 ${total}개 중 ${indices.length}개 악기의 PDF를 만들 준비가 됐습니다.`
    : 'PDF로 저장할 악기를 하나 이상 선택해 주세요.';
  for (const row of byId('tracks').children) {
    row.querySelector('.track-state').textContent = row.querySelector('.track-check').checked ? '준비됨' : '선택 안 함';
  }
}

function setBusy(value) {
  busy = value;
  choose.disabled = value;
  convert.disabled = value || selectedTrackIndices().length === 0;
  selectAll.disabled = value;
  for (const checkbox of document.querySelectorAll('.track-check')) checkbox.disabled = value;
  cancel.hidden = !value;
  cancel.disabled = false;
  progress.hidden = !value;
  byId('open-folder').disabled = value;
  document.querySelector('main').setAttribute('aria-busy', String(value));
}

function renderSource(selected) {
  source = selected;
  byId('file-name').textContent = selected.name;
  byId('file-folder').textContent = selected.folder;
  byId('file-folder').title = selected.folder;
  byId('empty-state').hidden = true;
  byId('select-all-control').hidden = false;
  const list = byId('tracks');
  list.replaceChildren();
  list.hidden = false;
  selected.trackNames.forEach((name, index) => {
    const row = document.createElement('li');
    const option = document.createElement('label');
    option.className = 'track-option';
    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.className = 'track-check';
    checkbox.value = String(index);
    checkbox.checked = true;
    const number = document.createElement('span');
    number.className = 'track-number';
    number.textContent = String(index + 1).padStart(2, '0');
    const label = document.createElement('span');
    label.className = 'track-name';
    label.textContent = name;
    const state = document.createElement('span');
    state.className = 'track-state';
    option.append(checkbox, number, label);
    row.append(option, state);
    list.append(row);
  });
  updateSelection();
  byId('outputs').hidden = true;
  byId('outputs').replaceChildren();
  byId('open-folder').hidden = true;
}

async function chooseFile() {
  if (busy) return;
  choose.disabled = true;
  showError(null);
  try {
    const result = await window.gp5.chooseFile();
    if (result.error) showError(result.error);
    if (result.source) renderSource(result.source);
  } catch (failure) {
    showError(failure instanceof Error ? failure.message : '파일을 열지 못했습니다.');
  } finally {
    choose.disabled = false;
  }
}

choose.addEventListener('click', chooseFile);
byId('tracks').addEventListener('change', () => {
  if (!busy) updateSelection();
});
selectAll.addEventListener('change', () => {
  if (busy) return;
  for (const checkbox of document.querySelectorAll('.track-check')) checkbox.checked = selectAll.checked;
  updateSelection();
});
convert.addEventListener('click', async () => {
  if (busy || !source) return;
  const indices = selectedTrackIndices();
  if (indices.length === 0) return;
  activeTrackIndices = indices;
  setBusy(true);
  showError(null);
  progress.value = 0;
  progress.max = indices.length;
  status.textContent = '악보를 준비하고 있습니다.';
  byId('outputs').replaceChildren();
  byId('outputs').hidden = true;
  byId('open-folder').hidden = true;
  for (const row of byId('tracks').children) {
    row.querySelector('.track-state').textContent = row.querySelector('.track-check').checked ? '대기 중' : '선택 안 함';
  }
  try {
    const result = await window.gp5.convert(indices);
    showError(result.error);
    status.textContent = result.cancelled
      ? `변환을 취소했습니다. 완료된 PDF ${result.files.length}개는 저장돼 있습니다.`
      : result.error
        ? `변환을 마치지 못했습니다. PDF ${result.files.length}개가 저장됐습니다.`
        : `완료! 악기별 PDF ${result.files.length}개를 원본 폴더에 저장했습니다.`;
    const outputs = byId('outputs');
    for (const file of result.files) {
      const item = document.createElement('li');
      item.textContent = file.split(/[\\/]/).at(-1);
      outputs.append(item);
    }
    outputs.hidden = result.files.length === 0;
    byId('open-folder').hidden = result.files.length === 0;
  } catch (failure) {
    showError(failure instanceof Error ? failure.message : '변환을 마치지 못했습니다.');
    status.textContent = '변환에 실패했습니다. 다시 시도해 주세요.';
  } finally {
    for (const index of indices) {
      const state = byId('tracks').children[index].querySelector('.track-state');
      if (state.textContent !== '저장됨') state.textContent = '미완료';
    }
    activeTrackIndices = [];
    setBusy(false);
  }
});

cancel.addEventListener('click', async () => {
  cancel.disabled = true;
  status.textContent = '변환을 취소하고 있습니다.';
  try {
    await window.gp5.cancel();
  } catch (failure) {
    showError(failure instanceof Error ? failure.message : '취소 요청에 실패했습니다.');
    cancel.disabled = false;
  }
});
byId('open-folder').addEventListener('click', async () => {
  try {
    await window.gp5.openOutputFolder();
  } catch (failure) {
    showError(failure instanceof Error ? failure.message : '저장 폴더를 열지 못했습니다.');
  }
});
window.gp5.onProgress((event) => {
  if (!busy || !activeTrackIndices.includes(event.trackIndex)) return;
  progress.max = event.total || 1;
  if (event.status === 'rendering') {
    status.textContent = `${event.current}/${event.total} · ${event.track} 악보를 만드는 중입니다.`;
  }
  if (event.status === 'saved') progress.value = event.current;
  const row = byId('tracks').children[event.trackIndex];
  if (row && ['rendering', 'saved'].includes(event.status)) {
    row.querySelector('.track-state').textContent = event.status === 'saved' ? '저장됨' : '변환 중';
  }
});
chooseFile();
