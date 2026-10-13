import * as at from '@coderline/alphatab';
import { checkAbort } from './pdf-fonts.js';

const ENGINE = 'gp5-pdf-svg';
const MAX_SVG_LENGTH = 32 * 1024 * 1024;

function settingsForPdf() {
  if (!at.Environment.renderEngines.has(ENGINE)) {
    const factory = at.Environment.getRenderEngineFactory('svg');
    at.Environment.renderEngines.set(ENGINE, new at.RenderEngineFactory(false, () => {
      const canvas = factory.createCanvas();
      const measure = document.createElement('canvas').getContext('2d');
      if (!measure) throw new Error('글꼴 측정 기능을 초기화하지 못했습니다.');
      const original = canvas.measureText.bind(canvas);
      canvas.measureText = text => {
        if (!/[^\u0000-\u00fe]/u.test(text)) return original(text);
        measure.font = canvas.font.toCssString();
        const bounds = measure.measureText(text);
        return new at.platform.MeasuredText(bounds.width * 1.07,
          Math.max(bounds.actualBoundingBoxAscent + bounds.actualBoundingBoxDescent, canvas.font.size));
      };
      return canvas;
    }));
  }
  const settings = new at.Settings();
  settings.core.engine = ENGINE;
  settings.core.useWorkers = false;
  settings.core.enableLazyLoading = false;
  settings.display.layoutMode = at.LayoutMode.Page;
  settings.display.scale = 0.8;
  settings.display.padding = [0];
  for (const name of ['ScoreTitle', 'ScoreSubTitle', 'ScoreArtist', 'ScoreAlbum',
    'ScoreWords', 'ScoreMusic', 'ScoreWordsAndMusic', 'ScoreCopyright', 'TrackNames']) {
    settings.notation.elements.set(at.NotationElement[name], false);
  }
  const resources = settings.display.resources;
  for (const [element, font] of resources.elementFonts) {
    resources.elementFonts.set(element, new at.model.Font('ScoreText', font.size, font.style, font.weight));
  }
  for (const key of ['tablatureFont', 'graceFont', 'numberedNotationFont', 'numberedNotationGraceFont']) {
    const font = resources[key];
    resources[key] = new at.model.Font('ScoreText', font.size, font.style, font.weight);
  }
  for (const key of ['staffLineColor', 'barSeparatorColor', 'barNumberColor', 'mainGlyphColor',
    'secondaryGlyphColor', 'scoreInfoColor']) resources[key] = new at.model.Color(0, 0, 0);
  return settings;
}

export function renderSystems(score, trackIndex, width, signal) {
  checkAbort(signal);
  const settings = settingsForPdf();
  const renderer = new at.rendering.ScoreRenderer(settings);
  const partials = [];
  let failure;
  let finished = false;
  let totalLength = 0;
  renderer.width = width;
  renderer.error.on(error => { failure = error; });
  renderer.partialRenderFinished.on(partial => {
    checkAbort(signal);
    if (typeof partial.renderResult !== 'string') throw new Error('악보 이미지를 생성하지 못했습니다.');
    totalLength += partial.renderResult.length;
    if (totalLength > MAX_SVG_LENGTH || partials.length >= 1000) {
      throw new Error('악보가 너무 커서 변환할 수 없습니다. 짧게 나누어 주세요.');
    }
    partials.push({ x: partial.x, width: partial.width, height: partial.height,
      firstBar: partial.firstMasterBarIndex, lastBar: partial.lastMasterBarIndex,
      svg: partial.renderResult });
  });
  renderer.renderFinished.on(() => { finished = true; });
  try {
    renderer.renderScore(score, [trackIndex]);
    if (failure) throw failure;
    if (!finished || !partials.some(partial => partial.firstBar >= 0)) {
      throw new Error('이 파트에는 출력할 악보가 없습니다.');
    }
    return { partials, musicFontSize: settings.display.resources.engravingSettings.musicFontSize };
  } finally {
    renderer.destroy();
  }
}

export function measureSystem(partial, musicFontSize, container) {
  const parsed = new DOMParser().parseFromString(partial.svg, 'image/svg+xml');
  if (parsed.querySelector('parsererror') || parsed.documentElement.localName !== 'svg') {
    throw new Error('악보 이미지 형식이 올바르지 않습니다.');
  }
  for (const element of [parsed.documentElement, ...parsed.documentElement.querySelectorAll('*')]) {
    if (!['svg', 'g', 'path', 'rect', 'text', 'tspan', 'line', 'circle', 'ellipse', 'polygon', 'polyline'].includes(element.localName)) {
      throw new Error('악보에 지원하지 않는 이미지 요소가 있습니다.');
    }
    for (const attribute of element.attributes) {
      if (/^on/iu.test(attribute.name) || /href$/iu.test(attribute.name) || /url\s*\(/iu.test(attribute.value)) {
        throw new Error('악보 이미지에 허용되지 않는 속성이 있습니다.');
      }
    }
  }
  const svg = document.importNode(parsed.documentElement, true);
  for (const element of svg.querySelectorAll('.at')) {
    element.setAttribute('font-family', 'ScoreBravura');
    element.setAttribute('font-size', String(musicFontSize));
    element.setAttribute('font-style', 'normal');
    element.setAttribute('font-weight', '400');
  }
  svg.setAttribute('font-family', 'ScoreText');
  const textElements = [...svg.querySelectorAll('text')].filter(element => !element.closest('.at'));
  for (const element of textElements) element.style.fontFamily = 'ScoreText';
  svg.setAttribute('width', String(partial.width));
  svg.setAttribute('height', String(partial.height));
  container.replaceChildren(svg);
  for (const element of partial.firstBar < 0 ? textElements : []) {
    if (!element.getNumberOfChars()) continue;
    const baseline = element.getStartPositionOfChar(0).y;
    element.setAttribute('y', String(baseline));
    element.style.dominantBaseline = 'alphabetic';
    element.style.alignmentBaseline = 'alphabetic';
  }
  const bbox = svg.getBBox();
  const top = Math.min(0, bbox.y);
  const left = Math.min(0, partial.x + bbox.x);
  const width = Math.max(partial.x + partial.width, partial.x + bbox.x + bbox.width) - left;
  const height = Math.ceil(Math.max(partial.height, bbox.y + bbox.height) - top) + 2;
  if (![width, height].every(value => Number.isFinite(value) && value > 0)) {
    throw new Error('악보의 크기를 계산하지 못했습니다.');
  }
  svg.setAttribute('viewBox', `${left - partial.x} ${top} ${width} ${height}`);
  svg.setAttribute('width', String(width));
  svg.setAttribute('height', String(height));
  return { svg, width, height };
}
