const byId = id => document.getElementById(id);
let urls = [];
let links = [];
let shareButtons = [];
let busy = false;
let sharing = false;
let generation = 0;

function shareStatus(message) {
  byId('share-status').textContent = message;
  byId('share-status').hidden = !message;
}

export function setDownloadsBusy(value) {
  busy = Boolean(value);
  for (const { element, url } of links) {
    if (busy) element.removeAttribute('href');
    else element.href = url;
    element.setAttribute('aria-disabled', String(busy));
    element.tabIndex = busy ? -1 : 0;
  }
  for (const button of shareButtons) button.disabled = busy || sharing;
}

export function clearDownloads() {
  generation += 1;
  for (const url of urls) URL.revokeObjectURL(url);
  urls = [];
  links = [];
  shareButtons = [];
  sharing = false;
  byId('outputs').replaceChildren();
  const download = byId('download');
  download.removeAttribute('href');
  download.removeAttribute('download');
  download.onclick = null;
  download.hidden = true;
  byId('share-zip').onclick = null;
  byId('share-zip').hidden = true;
  byId('result').hidden = true;
  shareStatus('');
}

function canShare(file) {
  if (typeof navigator.share !== 'function' || typeof navigator.canShare !== 'function') return false;
  try {
    return navigator.canShare({ files: [file] });
  } catch {
    return false;
  }
}

function attachShare(button, file) {
  const current = generation;
  shareButtons.push(button);
  button.hidden = false;
  button.onclick = async () => {
    if (busy || sharing || current !== generation) return;
    sharing = true;
    shareStatus('공유 창을 열고 있습니다.');
    setDownloadsBusy(busy);
    try {
      const pending = navigator.share({ files: [file] });
      await pending;
      if (current === generation) shareStatus('공유 요청을 전달했습니다.');
    } catch (error) {
      if (current === generation) {
        shareStatus(error?.name === 'AbortError' ? '' : '공유하지 못했습니다. PDF 저장·열기를 선택하세요.');
      }
    } finally {
      if (current === generation) {
        sharing = false;
        setDownloadsBusy(busy);
      }
    }
  };
}

function attachLink(element, url) {
  const current = generation;
  links.push({ element, url });
  element.onclick = event => {
    if (busy || current !== generation) event.preventDefault();
  };
}

export function showResult(result, total) {
  clearDownloads();
  if (result.pdfs.length === 0) return;
  for (const file of result.pdfs) {
    const url = URL.createObjectURL(file);
    urls.push(url);
    const item = document.createElement('li');
    item.className = 'output-file';
    const name = document.createElement('span');
    name.className = 'output-name';
    name.textContent = file.name;
    const actions = document.createElement('div');
    actions.className = 'output-actions';
    const save = document.createElement('a');
    save.className = 'button secondary pdf-download';
    save.textContent = 'PDF 저장';
    save.download = file.name;
    save.setAttribute('aria-label', `${file.name} PDF 저장`);
    attachLink(save, url);
    const open = document.createElement('a');
    open.className = 'button secondary pdf-open';
    open.textContent = '열기';
    open.target = '_blank';
    open.rel = 'noopener';
    open.setAttribute('aria-label', `${file.name} 새 탭에서 열기`);
    attachLink(open, url);
    actions.append(save, open);
    if (canShare(file)) {
      const share = document.createElement('button');
      share.type = 'button';
      share.className = 'secondary pdf-share';
      share.textContent = '공유';
      share.setAttribute('aria-label', `${file.name} 공유`);
      attachShare(share, file);
      actions.append(share);
    }
    item.append(name, actions);
    byId('outputs').append(item);
  }
  if (result.blob) {
    const url = URL.createObjectURL(result.blob);
    urls.push(url);
    const download = byId('download');
    attachLink(download, url);
    download.download = result.filename;
    download.textContent = 'ZIP 저장';
    download.hidden = false;
    const zip = new File([result.blob], result.filename, { type: 'application/zip' });
    if (canShare(zip)) attachShare(byId('share-zip'), zip);
  }
  const partial = result.cancelled || Boolean(result.error) || result.pdfs.length < total;
  byId('result-title').textContent = partial ? '완성된 PDF 저장하기' : 'PDF 저장 준비 완료';
  byId('result-detail').textContent = `선택한 ${total}개 중 ${result.pdfs.length}개 악기의 PDF를 완성했습니다. 개별 저장·열기를 선택하세요.${result.blob ? ' ZIP으로 한 번에 받으세요.' : ''}`;
  setDownloadsBusy(busy);
  byId('result').hidden = false;
}
