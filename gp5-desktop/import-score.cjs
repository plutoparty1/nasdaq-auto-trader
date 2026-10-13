'use strict';

const path = require('node:path');
const { importer, Settings } = require('@coderline/alphatab');
const { detectGp5Encoding } = require('./encoding.cjs');

function parseGp5(bytes, sourceName) {
  const version = bytes.subarray(1, 25).toString('ascii');
  if (path.extname(sourceName).toLowerCase() !== '.gp5' || bytes.length < 31 || bytes[0] !== 24 || !/^FICHIER GUITAR PRO v5\.(00|10)$/.test(version)) {
    throw new Error('올바른 GP5 파일을 선택해 주세요.');
  }
  try {
    const settings = new Settings();
    settings.importer.encoding = detectGp5Encoding(bytes);
    const score = importer.ScoreLoader.loadScoreFromBytes(bytes, settings);
    if (score.tracks.length === 0 || score.masterBars.length === 0) {
      throw new Error('악보에 변환할 트랙이나 마디가 없습니다.');
    }
    return {
      encoding: settings.importer.encoding,
      title: score.title.trim() || path.parse(sourceName).name,
      trackNames: score.tracks.map((track, index) => track.name.trim() || `Track ${index + 1}`),
    };
  } catch (cause) {
    throw new Error('GP5 파일을 읽을 수 없습니다. 파일이 손상되었거나 지원하지 않는 형식입니다.', { cause });
  }
}

module.exports = { parseGp5 };
