'use strict';

const fs = require('node:fs/promises');
const path = require('node:path');

function safeName(value, fallback, byteLimit) {
  const clean = value.normalize('NFC').replace(/[<>:"/\\|?*\u0000-\u001f\u007f]/g, '_');
  let shortened = '';
  for (const character of clean) {
    if (Buffer.byteLength(shortened + character) > byteLimit) break;
    shortened += character;
  }
  const name = shortened.replace(/^[ .]+|[ .]+$/g, '') || fallback;
  return /^(con|prn|aux|nul|conin\$|conout\$|com[1-9¹²³]|lpt[1-9¹²³])(?:\.|$)/i.test(name) ? `_${name}` : name;
}

function createPdfWriter(fileSystem = fs) {
  return async function writeTrackPdf(output, bytes, signal) {
    const source = safeName(path.parse(output.sourceName).name, 'Score', 72);
    const track = safeName(output.trackName, 'Track', 96);
    const number = String(output.trackIndex + 1).padStart(2, '0');
    for (let attempt = 1; attempt <= 10000; attempt += 1) {
      signal?.throwIfAborted();
      const suffix = attempt === 1 ? '' : ` (${attempt})`;
      const filename = path.join(output.folder, `${source} - ${number} - ${track}${suffix}.pdf`);
      let handle;
      try {
        handle = await fileSystem.open(filename, 'wx');
      } catch (error) {
        if (error.code === 'EEXIST') continue;
        throw error;
      }
      try {
        signal?.throwIfAborted();
        await handle.writeFile(bytes, { signal });
        await handle.close();
        handle = null;
        signal?.throwIfAborted();
        return filename;
      } catch (error) {
        const cleanupErrors = [];
        if (handle) {
          try { await handle.close(); } catch (closeError) { cleanupErrors.push(closeError); }
        }
        try { await fileSystem.unlink(filename); } catch (removeError) { cleanupErrors.push(removeError); }
        if (cleanupErrors.length) {
          throw new AggregateError([error, ...cleanupErrors], `PDF 저장에 실패했고 임시 파일을 정리하지 못했습니다: ${filename}`, { cause: error });
        }
        throw error;
      }
    }
    throw new Error('같은 이름의 PDF가 너무 많습니다. 기존 출력 파일을 다른 폴더로 옮겨 주세요.');
  };
}

module.exports = { createPdfWriter, writeTrackPdf: createPdfWriter() };
