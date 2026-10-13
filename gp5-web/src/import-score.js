export async function loadGp5(file) {
  if (!/\.gp5$/i.test(file.name)) throw new Error('GP5 파일을 선택해 주세요.');
  if (file.size > 64 * 1024 * 1024) throw new Error('64MB 이하의 GP5 파일을 선택해 주세요.');
  const bytes = new Uint8Array(await file.arrayBuffer());
  const version = new TextDecoder('ascii').decode(bytes.subarray(1, 25));
  if (bytes.length < 31 || bytes[0] !== 24 || !/^FICHIER GUITAR PRO v5\.(00|10)$/.test(version)) {
    throw new Error('올바른 GP5 파일을 선택해 주세요.');
  }
  try {
    const [{ importer, Settings }, { detectGp5Encoding }] = await Promise.all([
      import('@coderline/alphatab'),
      import('./encoding.js'),
    ]);
    const encoding = detectGp5Encoding(bytes);
    const settings = new Settings();
    settings.importer.encoding = encoding;
    const score = importer.ScoreLoader.loadScoreFromBytes(bytes, settings);
    if (score.tracks.length === 0 || score.masterBars.length === 0) {
      throw new Error('악보에 변환할 악기나 마디가 없습니다.');
    }
    return {
      name: file.name,
      title: score.title.trim() || file.name.replace(/\.gp5$/i, ''),
      trackNames: score.tracks.map((track, index) => track.name.trim() || `Track ${index + 1}`),
      encoding,
      score,
    };
  } catch (cause) {
    throw new Error('GP5 파일을 읽을 수 없습니다. 파일이 손상되었거나 지원하지 않는 형식입니다.', { cause });
  }
}
