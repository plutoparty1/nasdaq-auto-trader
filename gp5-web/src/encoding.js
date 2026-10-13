import { importer, Settings } from '@coderline/alphatab';

const byteDecoder = new TextDecoder('windows-1252');
const originalBytes = new Map(Array.from({ length: 256 }, (_, byte) => [
  byteDecoder.decode(Uint8Array.of(byte)), byte,
]));

function sourceStrings(score) {
  const values = [];
  const add = (value) => { if (typeof value === 'string' && value.length) values.push(value); };
  for (const key of ['title', 'subTitle', 'artist', 'album', 'words', 'music',
    'copyright', 'tab', 'instructions', 'notices', 'tempoLabel']) add(score[key]);
  for (const style of score.style?.headerAndFooter?.values() ?? []) add(style.template);
  for (const bar of score.masterBars) add(bar.section?.text);
  for (const track of score.tracks) {
    add(track.name);
    for (const staff of track.staves) {
      for (const chord of staff.chords?.values() ?? []) add(chord.name);
      for (const bar of staff.bars) {
        for (const voice of bar.voices) for (const beat of voice.beats) add(beat.text);
      }
    }
  }
  return values;
}

function recoverBytes(text) {
  const bytes = [];
  for (const char of text) {
    const byte = originalBytes.get(char);
    if (byte === undefined) return null;
    bytes.push(byte);
  }
  return Uint8Array.from(bytes);
}

function strictDecode(bytes, encoding) {
  try {
    return new TextDecoder(encoding, { fatal: true }).decode(bytes);
  } catch (error) {
    if (error instanceof TypeError) return null;
    throw error;
  }
}

export function detectGp5Encoding(bytes) {
  const settings = new Settings();
  settings.importer.encoding = 'windows-1252';
  settings.importer.beatTextAsLyrics = false;
  const probe = importer.ScoreLoader.loadScoreFromBytes(bytes, settings);
  // Derived shortName and lyric chunks can split otherwise intact multibyte text.
  const fields = sourceStrings(probe).map(recoverBytes);
  if (originalBytes.size !== 256 || fields.some((field) => field === null)) return 'utf-8';
  const invalidUtf8 = fields.filter((field) => strictDecode(field, 'utf-8') === null);
  if (invalidUtf8.length === 0) return 'utf-8';
  if (fields.some((field) => strictDecode(field, 'euc-kr') === null)) return 'utf-8';
  const hasKorean = invalidUtf8.some((field) => /[\uac00-\ud7a3]/u.test(strictDecode(field, 'euc-kr')));
  return hasKorean ? 'euc-kr' : 'utf-8';
}
