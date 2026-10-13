import { PDFDocument } from 'pdfkit';
import SVGtoPDF from 'svg-to-pdfkit';
import { checkAbort, loadPdfFonts, releasePdfFonts, yieldToBrowser } from './pdf-fonts.js';
import { CONTENT, PAPER, makeHeading, placeSystem } from './pdf-layout.js';
import { measureSystem, renderSystems } from './pdf-score.js';
import { collectPdf } from './pdf-output.js';

let busy = false;

async function paginate(doc, score, track, rendered, signal, onProgress) {
  const heading = makeHeading(doc, score, track);
  const pages = [{ used: heading.height, systems: [] }];
  const measure = document.createElement('div');
  measure.setAttribute('aria-hidden', 'true');
  measure.style.cssText = 'position:absolute;left:-100000px;top:0;visibility:hidden;pointer-events:none';
  document.body.append(measure);
  try {
    for (let index = 0; index < rendered.partials.length; index++) {
      await yieldToBrowser(signal);
      const partial = rendered.partials[index];
      const system = measureSystem(partial, rendered.musicFontSize, measure);
      const item = placeSystem(pages, system.width, system.height);
      system.svg.setAttribute('width', String(item.width));
      system.svg.setAttribute('height', String(item.height));
      item.svg = new XMLSerializer().serializeToString(system.svg);
      item.firstBar = partial.firstBar;
      item.lastBar = partial.lastBar;
      partial.svg = '';
      onProgress?.({ stage: 'layout', completed: index + 1, total: rendered.partials.length });
    }
    return { pages, heading };
  } finally {
    measure.remove();
  }
}

function drawHeading(doc, heading) {
  for (const row of heading.rows) {
    doc.font('ScoreText').fontSize(row.size).fillColor('black');
    doc.text(row.text, PAPER.margin, PAPER.margin + row.y, { lineBreak: false });
  }
}

async function writePages(doc, layout, signal, onProgress) {
  for (let index = 0; index < layout.pages.length; index++) {
    await yieldToBrowser(signal);
    doc.addPage({ size: [PAPER.width, PAPER.height], margin: 0 });
    if (index === 0) drawHeading(doc, layout.heading);
    for (const system of layout.pages[index].systems) {
      await yieldToBrowser(signal);
      SVGtoPDF(doc, system.svg, PAPER.margin, PAPER.margin + system.y, {
        width: system.width, height: system.height, assumePt: true,
        fontCallback: family => family.includes('ScoreBravura') ? 'ScoreBravura' : 'ScoreText',
        warningCallback: warning => { throw new Error(`악보 PDF를 생성하지 못했습니다: ${warning}`); },
      });
      system.svg = '';
    }
    doc.font('ScoreText').fontSize(6).fillColor('black');
    doc.text(`${index + 1} / ${layout.pages.length}`, PAPER.margin, PAPER.height - 8 * 72 / 25.4,
      { width: CONTENT.width, align: 'right', lineBreak: false });
    onProgress?.({ stage: 'pdf', completed: index + 1, total: layout.pages.length,
      page: index + 1, totalPages: layout.pages.length });
  }
}

export async function renderTrackPdf({ score, trackIndex, signal, onProgress }) {
  checkAbort(signal);
  if (busy) throw new Error('다른 파트를 변환하고 있습니다.');
  const track = Number.isInteger(trackIndex) && score?.tracks?.[trackIndex];
  if (!track) throw new Error('선택한 파트를 찾을 수 없습니다.');
  if (!score.masterBars?.length || score.masterBars.length > 2000) {
    throw new Error('악보의 마디 수가 지원 범위를 벗어났습니다. 최대 2,000마디까지 지원합니다.');
  }
  busy = true;
  let output;
  try {
    onProgress?.({ stage: 'fonts', completed: 0, total: 1 });
    const fonts = await loadPdfFonts(signal);
    await yieldToBrowser(signal);
    const doc = new PDFDocument({ autoFirstPage: false, font: null, compress: true,
      info: { Title: score.title || '제목 없음', Subject: track.name || `파트 ${trackIndex + 1}` } });
    output = collectPdf(doc, { signal });
    for (const { family, data } of fonts) doc.registerFont(family, data);
    onProgress?.({ stage: 'fonts', completed: 1, total: 1 });
    await yieldToBrowser(signal);
    const rendered = renderSystems(score, trackIndex, Math.floor(CONTENT.width / PAPER.px), signal);
    const layout = await paginate(doc, score, track, rendered, signal, onProgress);
    await writePages(doc, layout, signal, onProgress);
    await yieldToBrowser(signal);
    const blob = await output.finish();
    checkAbort(signal);
    return blob;
  } finally {
    output?.discard();
    busy = false;
  }
}

export function releaseRenderer() {
  if (!busy) releasePdfFonts();
}
