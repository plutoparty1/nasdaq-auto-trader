(() => {
  'use strict';
  const at = window.alphaTab;
  const pages = document.getElementById('pages');
  let rendering = false;

  function registerSvgEngine() {
    const factory = at.Environment.getRenderEngineFactory('svg');
    at.Environment.renderEngines.set('score-svg', new at.RenderEngineFactory(false, () => {
      const canvas = factory.createCanvas();
      const measure = document.createElement('canvas').getContext('2d');
      if (!measure) throw new Error('글꼴 측정 기능을 초기화하지 못했습니다.');
      const originalMeasure = canvas.measureText.bind(canvas);
      canvas.measureText = text => {
        if (!/[^\u0000-\u00fe]/u.test(text)) return originalMeasure(text);
        measure.font = canvas.font.toCssString();
        const bounds = measure.measureText(text);
        return new at.platform.MeasuredText(bounds.width * 1.07,
          Math.max(bounds.actualBoundingBoxAscent + bounds.actualBoundingBoxDescent, canvas.font.size));
      };
      return canvas;
    }));
  }

  async function loadFonts() {
    const loaded = await Promise.all([
      document.fonts.load('34px ScoreBravura', '\uE050'),
      document.fonts.load('16px ScoreText', '한글樂譜ABC0123'),
    ]);
    await document.fonts.ready;
    if (loaded.some(fonts => !fonts.length || fonts.some(font => font.status !== 'loaded'))) {
      throw new Error('악보 또는 한글 글꼴을 불러오지 못했습니다. 앱 파일을 다시 확인해 주세요.');
    }
  }

  function createSettings(encoding = 'utf-8') {
    if (!['utf-8', 'euc-kr'].includes(encoding)) throw new Error('악보의 문자 인코딩이 올바르지 않습니다.');
    const settings = new at.Settings();
    settings.importer.encoding = encoding;
    settings.core.engine = 'score-svg';
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
    document.documentElement.style.setProperty('--music-font-size', `${resources.engravingSettings.musicFontSize}px`);
    return settings;
  }

  function renderPart(score, trackIndex, settings, width) {
    const renderer = new at.rendering.ScoreRenderer(settings);
    const partials = [];
    let failure;
    let finished = false;
    renderer.width = width;
    renderer.error.on(error => { failure = error; });
    renderer.partialRenderFinished.on(partial => {
      if (typeof partial.renderResult !== 'string') throw new Error('SVG 악보를 생성하지 못했습니다.');
      partials.push({ ...partial, svg: partial.renderResult });
    });
    renderer.renderFinished.on(() => { finished = true; });
    try {
      renderer.renderScore(score, [trackIndex]);
      if (failure) throw failure;
      if (!finished || !partials.some(partial => partial.firstMasterBarIndex >= 0)) {
        throw new Error('이 파트에는 출력할 악보가 없습니다.');
      }
      return partials;
    } finally {
      renderer.destroy();
    }
  }

  function makePage() {
    const page = document.createElement('section');
    page.className = 'page';
    const content = document.createElement('div');
    content.className = 'page-content';
    page.append(content);
    pages.append(page);
    return content;
  }

  function makeHeading(score, track) {
    const heading = document.createElement('header');
    heading.className = 'part-heading';
    for (const [tag, text] of [['h1', score.title || '제목 없음'],
      ['h2', track.name || `파트 ${track.index + 1}`],
      ['p', [score.subTitle, score.artist, score.album].filter(Boolean).join(' · ')],
      ['p', [score.words && `작사: ${score.words}`, score.music && `작곡: ${score.music}`,
        score.copyright].filter(Boolean).join(' · ')]]) {
      if (!text) continue;
      const element = document.createElement(tag);
      element.textContent = text;
      heading.append(element);
    }
    return heading;
  }

  function makeChunk(partial, measure, width, maxHeight) {
    const parsed = new DOMParser().parseFromString(partial.svg, 'image/svg+xml');
    if (parsed.querySelector('parsererror') || parsed.documentElement.localName !== 'svg') {
      throw new Error('악보 이미지 형식이 올바르지 않습니다.');
    }
    const svg = document.importNode(parsed.documentElement, true);
    svg.setAttribute('width', String(partial.width));
    svg.setAttribute('height', String(partial.height));
    const chunk = document.createElement('div');
    chunk.className = 'score-chunk';
    chunk.dataset.firstBar = String(partial.firstMasterBarIndex);
    chunk.dataset.lastBar = String(partial.lastMasterBarIndex);
    chunk.append(svg);
    measure.append(chunk);
    const bbox = svg.getBBox();
    const top = Math.min(0, bbox.y);
    const left = Math.min(0, partial.x + bbox.x);
    const naturalWidth = Math.max(partial.x + partial.width, partial.x + bbox.x + bbox.width) - left;
    const naturalHeight = Math.ceil(Math.max(partial.height, bbox.y + bbox.height) - top) + 2;
    const scale = Math.min(1, width / naturalWidth, maxHeight / naturalHeight);
    chunk.style.height = `${Math.ceil(naturalHeight * scale)}px`;
    svg.style.left = `${(partial.x - left) * scale}px`;
    svg.style.top = `${-top * scale}px`;
    svg.style.transform = `scale(${scale})`;
    chunk.dataset.scaled = String(scale < 0.999);
    return chunk;
  }

  function paginate(score, track, partials, firstPage) {
    const width = firstPage.getBoundingClientRect().width;
    const height = Math.floor(firstPage.getBoundingClientRect().height) - 1;
    const measure = document.createElement('div');
    measure.className = 'measure';
    measure.style.width = `${width}px`;
    document.body.append(measure);
    let content = firstPage;
    const heading = makeHeading(score, track);
    content.append(heading);
    let used = Math.ceil(heading.getBoundingClientRect().height);
    try {
      if (used >= height) throw new Error('곡 정보가 한 페이지보다 깁니다. 제목이나 설명을 줄여 주세요.');
      for (const partial of partials) {
        const chunk = makeChunk(partial, measure, width, height);
        const chunkHeight = Math.ceil(chunk.getBoundingClientRect().height);
        if (used + chunkHeight > height) { content = makePage(); used = 0; }
        content.append(chunk);
        used += chunkHeight;
      }
    } finally {
      measure.remove();
    }
    const pageElements = [...pages.children];
    pageElements.forEach((page, index) => {
      const number = document.createElement('span');
      number.className = 'page-number';
      number.textContent = `${index + 1} / ${pageElements.length}`;
      page.append(number);
    });
  }

  function checkBounds() {
    for (const content of document.querySelectorAll('.page-content')) {
      const boundary = content.getBoundingClientRect();
      for (const child of content.children) {
        const rect = child.getBoundingClientRect();
        if (rect.bottom > boundary.bottom + 0.5 || rect.right > boundary.right + 0.5) {
          throw new Error('악보가 인쇄 영역을 벗어나 PDF 생성을 중단했습니다.');
        }
      }
    }
  }

  async function run(job) {
    if (rendering) {
      window.scoreJob.done({ id: job.id, ok: false, error: '다른 파트를 처리 중입니다.' });
      return;
    }
    rendering = true;
    try {
      if (!Number.isInteger(job.trackIndex) || !(job.bytes instanceof Uint8Array)) {
        throw new Error('악보 변환 요청이 올바르지 않습니다.');
      }
      pages.replaceChildren();
      await loadFonts();
      const settings = createSettings(job.encoding);
      const score = at.importer.ScoreLoader.loadScoreFromBytes(job.bytes, settings);
      const track = score.tracks[job.trackIndex];
      if (!track) throw new Error('선택한 파트를 찾을 수 없습니다.');
      const firstPage = makePage();
      const partials = renderPart(score, job.trackIndex, settings, Math.floor(firstPage.clientWidth));
      paginate(score, track, partials, firstPage);
      await document.fonts.ready;
      await new Promise(resolve => setTimeout(resolve, 0));
      checkBounds();
      window.scoreJob.done({ id: job.id, ok: true, pageCount: pages.childElementCount,
        systems: partials.filter(partial => partial.firstMasterBarIndex >= 0).length,
        scaledSystems: pages.querySelectorAll('[data-scaled="true"]').length });
    } catch (error) {
      pages.replaceChildren();
      window.scoreJob.done({ id: job.id, ok: false, error: error instanceof Error ? error.message : String(error) });
    } finally {
      rendering = false;
    }
  }

  registerSvgEngine();
  window.scoreJob.onRender(run);
})();
