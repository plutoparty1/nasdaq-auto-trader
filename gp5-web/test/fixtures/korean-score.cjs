'use strict';

const fs = require('node:fs');
const path = require('node:path');
const originalNames = ['Electric Guitar', 'Bass Guitar', 'Drum Kit'];
const legacyText = new Map([
  ['한글 악보 제목', 'c7d1b1db20bec7bab820c1a6b8f1'],
  ['기타', 'b1e2c5b8'],
  ['베이스', 'baa3c0ccbdba'],
  ['드럼', 'b5e5b7b3'],
  ['리드 기타 뷁', 'b8aeb5e520b1e2c5b82094ee'],
  ['한글 연주 지시', 'c7d1b1db20bfacc1d620c1f6bdc3'],
  ['Café Élégant', '436166e920c96ce967616e74'],
  ['Guitàr', '47756974e072'],
]);

function encodedText(text, encoding) {
  if (encoding === 'utf-8' || /^[\x00-\x7f]*$/u.test(text)) return Buffer.from(text, 'utf8');
  const hex = legacyText.get(text);
  if (!hex) throw new Error(`No legacy fixture bytes registered for ${text}`);
  return Buffer.from(hex, 'hex');
}

function replaceVariableText(bytes, offset, text) {
  const oldLength = bytes[offset + 4];
  if (text.length > 255) throw new Error('GP5 fixture text exceeds its byte-length field');
  const prefix = Buffer.alloc(5);
  prefix.writeInt32LE(text.length + 1);
  prefix[4] = text.length;
  return Buffer.concat([bytes.subarray(0, offset), prefix, text, bytes.subarray(offset + 5 + oldLength)]);
}

function makeKoreanGp5(encoding, options = {}) {
  const title = options.title ?? '한글 악보 제목';
  const trackNames = options.trackNames ?? ['기타', '베이스', '드럼'];
  const beatText = options.beatText ?? '한글 연주 지시';
  if (trackNames.length !== originalNames.length) throw new Error('Fixture requires three track names');
  let bytes = fs.readFileSync(path.join(__dirname, 'QA Trio.gp5'));
  for (let index = 0; index < originalNames.length; index++) {
    const offset = bytes.indexOf(Buffer.from(originalNames[index]));
    const text = encodedText(trackNames[index], encoding);
    if (offset < 1 || text.length > 40) throw new Error('Invalid GP5 track-name fixture');
    bytes[offset - 1] = text.length;
    bytes.fill(0, offset, offset + 40);
    text.copy(bytes, offset);
  }
  const beatOffset = bytes.indexOf(Buffer.from('Electric Guitar ONLY'));
  if (beatOffset < 5) throw new Error('GP5 fixture has no expected beat text');
  bytes = replaceVariableText(bytes, beatOffset - 5, encodedText(beatText, encoding));
  bytes = replaceVariableText(bytes, 31, encodedText(title, encoding));
  return { bytes, title, trackNames: [...trackNames], beatText };
}

module.exports = { makeKoreanGp5 };
