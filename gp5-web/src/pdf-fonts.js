const fonts = [
  ['ScoreText', 'NotoSansCJKkr-Regular.otf'],
  ['ScoreBravura', 'Bravura.otf'],
];
let cached;

export function checkAbort(signal) {
  if (signal?.aborted) throw new DOMException('변환을 취소했습니다.', 'AbortError');
}

export async function yieldToBrowser(signal) {
  checkAbort(signal);
  await new Promise(resolve => setTimeout(resolve, 0));
  checkAbort(signal);
}

export async function loadPdfFonts(signal) {
  checkAbort(signal);
  if (cached) return cached;
  const loaded = [];
  try {
    for (const [family, filename] of fonts) {
      const url = `${import.meta.env.BASE_URL}assets/fonts/${filename}`;
      const response = await fetch(url, { signal });
      if (!response.ok) throw new Error('악보 글꼴을 불러오지 못했습니다. 다시 시도해 주세요.');
      const data = new Uint8Array(await response.arrayBuffer());
      checkAbort(signal);
      const face = new FontFace(family, data);
      await face.load();
      document.fonts.add(face);
      loaded.push({ family, data, face });
    }
    checkAbort(signal);
    cached = loaded;
    return cached;
  } catch (error) {
    for (const { face } of loaded) document.fonts.delete(face);
    throw error;
  }
}

export function releasePdfFonts() {
  for (const { face } of cached ?? []) document.fonts.delete(face);
  cached = undefined;
}
