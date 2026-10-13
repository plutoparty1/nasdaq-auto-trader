export const PAPER = Object.freeze({ width: 210 * 72 / 25.4, height: 297 * 72 / 25.4,
  margin: 12 * 72 / 25.4, px: 0.75 });
export const CONTENT = Object.freeze({ width: PAPER.width - PAPER.margin * 2,
  height: PAPER.height - PAPER.margin * 2 });

export function wrapHeading(text, width, measure) {
  const lines = [];
  for (const paragraph of String(text).replace(/\r\n?/gu, '\n').split('\n')) {
    let line = '';
    for (const word of paragraph.split(/\s+/u).filter(Boolean)) {
      const candidate = line ? `${line} ${word}` : word;
      if (measure(candidate) <= width) { line = candidate; continue; }
      if (line) { lines.push(line); line = ''; }
      for (const char of word) {
        if (line && measure(line + char) > width) { lines.push(line); line = ''; }
        line += char;
      }
    }
    lines.push(line);
  }
  return lines;
}

export function makeHeading(doc, score, track) {
  const entries = [
    [score.title || '제목 없음', 13.5, 1.4, 0],
    [track.name || `파트 ${track.index + 1}`, 9, 1.5, 4.5],
    [[score.subTitle, score.artist, score.album].filter(Boolean).join(' · '), 7.5, 1.5, 3],
    [[score.words && `작사: ${score.words}`, score.music && `작곡: ${score.music}`,
      score.copyright].filter(Boolean).join(' · '), 7.5, 1.5, 3],
  ];
  const rows = [];
  let height = 0;
  for (const [text, size, lineHeight, gap] of entries) {
    if (!text) continue;
    if (text.length > 16000) throw new Error('곡 정보가 너무 깁니다. 제목이나 설명을 줄여 주세요.');
    doc.font('ScoreText').fontSize(size);
    height += gap;
    for (const line of wrapHeading(text, CONTENT.width, value => doc.widthOfString(value))) {
      rows.push({ text: line, size, y: height });
      height += size * lineHeight;
    }
  }
  height += 10.5;
  if (height >= CONTENT.height) throw new Error('곡 정보가 한 페이지보다 깁니다. 제목이나 설명을 줄여 주세요.');
  return { rows, height };
}

export function placeSystem(pages, width, height) {
  const scale = Math.min(PAPER.px, CONTENT.width / width, CONTENT.height / height);
  const item = { width: width * scale, height: height * scale, scaled: scale < PAPER.px - 0.0001 };
  let page = pages.at(-1);
  if (page.used + item.height > CONTENT.height + 0.001) {
    if (pages.length >= 300) throw new Error('PDF가 너무 깁니다. 악보를 짧게 나누어 주세요.');
    page = { used: 0, systems: [] };
    pages.push(page);
  }
  item.y = page.used;
  page.used += item.height;
  page.systems.push(item);
  return item;
}
