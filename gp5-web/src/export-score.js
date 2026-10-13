import { zipSync } from 'fflate';

const PDF_BUDGET = 128 * 1024 * 1024;
const utf8 = new TextEncoder();

function safeName(value, byteLimit) {
  const clean = value.normalize('NFC').replace(/[<>:"/\\|?*\u0000-\u001f\u007f]/g, '_');
  let shortened = '';
  for (const character of clean) {
    if (utf8.encode(shortened + character).length > byteLimit) break;
    shortened += character;
  }
  const name = shortened.replace(/^[ .]+|[ .]+$/g, '') || 'Score';
  return /^(con|prn|aux|nul|conin\$|conout\$|com[1-9¹²³]|lpt[1-9¹²³])(?:\.|$)/i.test(name) ? `_${name}` : name;
}

function selectTracks(indices, trackCount) {
  if (!Array.isArray(indices) || indices.length === 0) throw new Error('PDF로 만들 악기를 하나 이상 선택해 주세요.');
  if (indices.length > trackCount) throw new Error('선택한 악기 정보가 올바르지 않습니다.');
  const selected = new Set();
  for (const index of indices) {
    if (!Number.isInteger(index) || index < 0 || index >= trackCount || selected.has(index)) {
      throw new Error('선택한 악기 정보가 올바르지 않습니다.');
    }
    selected.add(index);
  }
  return [...selected];
}

export function createExporter(renderTrackPdf, packZip = zipSync) {
  return async function exportSelected({ source, indices, signal = new AbortController().signal, onProgress = () => {} }) {
    const stem = safeName(source.name.replace(/\.gp5$/i, ''), 72);
    const pdfs = [];
    let generatedBytes = 0;
    let cancelled = false;
    let error = null;
    try {
      const selected = selectTracks(indices, source.trackNames.length);
      for (const [ordinal, trackIndex] of selected.entries()) {
        signal.throwIfAborted();
        const progress = { current: ordinal + 1, total: selected.length, trackIndex, track: source.trackNames[trackIndex] };
        onProgress({ ...progress, status: 'rendering' });
        const pdf = await renderTrackPdf({
          score: source.score, trackIndex, signal,
          onProgress: (event) => onProgress({ ...progress, status: 'rendering', page: event.page }),
        });
        signal.throwIfAborted();
        if (generatedBytes + pdf.size > PDF_BUDGET) {
          throw new Error('PDF 합계가 128MB를 초과했습니다. 악기를 나누어 변환해 주세요.');
        }
        const number = String(trackIndex + 1).padStart(2, '0');
        const name = `${stem} - ${number} - ${safeName(source.trackNames[trackIndex], 96)}.pdf`;
        pdfs.push(new File([pdf], name, { type: 'application/pdf' }));
        generatedBytes += pdf.size;
        onProgress({ ...progress, status: 'saved' });
        await new Promise((resolve) => setTimeout(resolve, 0));
      }
      signal.throwIfAborted();
    } catch (cause) {
      cancelled = signal.aborted || cause?.name === 'AbortError';
      error = cancelled ? null : cause instanceof Error ? cause.message : 'PDF를 변환하지 못했습니다.';
    }
    const files = pdfs.map(pdf => pdf.name);
    let blob = null;
    if (files.length > 0) {
      try {
        const entries = Object.create(null);
        for (const pdf of pdfs) entries[pdf.name] = new Uint8Array(await pdf.arrayBuffer());
        blob = new Blob([packZip(entries, { level: 0 })], { type: 'application/zip' });
      } catch (cause) {
        error = `완료된 PDF를 ZIP으로 묶지 못했습니다: ${cause instanceof Error ? cause.message : '메모리 부족'}`;
      }
    }
    cancelled ||= signal.aborted;
    const filename = `${stem}${cancelled || error ? ' - partial' : ''}.zip`;
    return { blob, filename, files, pdfs, cancelled, error };
  };
}

export function createLazyRenderer(loadModule) {
  return async (request) => {
    const { signal } = request;
    signal.throwIfAborted();
    let onAbort;
    const interrupted = new Promise((_resolve, reject) => {
      onAbort = () => reject(signal.reason);
      signal.addEventListener('abort', onAbort, { once: true });
    });
    try {
      const { renderTrackPdf } = await Promise.race([loadModule(), interrupted]);
      signal.throwIfAborted();
      return renderTrackPdf(request);
    } finally {
      signal.removeEventListener('abort', onAbort);
    }
  };
}

export const exportSelected = createExporter(createLazyRenderer(() => import('./pdf.js')));
