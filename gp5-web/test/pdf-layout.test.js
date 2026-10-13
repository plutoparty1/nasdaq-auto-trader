import { test } from 'node:test';
import assert from 'node:assert/strict';
import { CONTENT, PAPER, placeSystem, wrapHeading } from '../src/pdf-layout.js';

test('A4 content leaves exactly 12 mm on every edge', () => {
  assert.equal(PAPER.width * 25.4 / 72, 210);
  assert.equal(PAPER.height * 25.4 / 72, 297);
  assert.ok(Math.abs(CONTENT.width * 25.4 / 72 - 186) < 0.0001);
  assert.ok(Math.abs(CONTENT.height * 25.4 / 72 - 273) < 0.0001);
});

test('systems move intact to the next page and oversized systems scale to fit', () => {
  const pages = [{ used: CONTENT.height - 10, systems: [] }];
  const first = placeSystem(pages, 600, 100);
  const tall = placeSystem(pages, 600, 3000);
  assert.equal(pages.length, 3);
  assert.equal(first.y, 0);
  assert.equal(tall.y, 0);
  assert.equal(tall.scaled, true);
  assert.ok(tall.height <= CONTENT.height);
  assert.equal(pages.reduce((count, page) => count + page.systems.length, 0), 2);
});

test('Korean headings keep words together and split only an oversized word', () => {
  const width = value => [...value].length;
  assert.deepEqual(wrapHeading('한글 제목 이어지는지 확인', 9, width), ['한글 제목', '이어지는지 확인']);
  assert.deepEqual(wrapHeading('가나다라마바사아자차', 4, width), ['가나다라', '마바사아', '자차']);
  assert.deepEqual(wrapHeading('literal <script> & text', 40, width), ['literal <script> & text']);
});

test('pagination stops at the explicit page limit', () => {
  const pages = Array.from({ length: 300 }, () => ({ used: CONTENT.height, systems: [] }));
  assert.throws(() => placeSystem(pages, 600, 100), /PDF가 너무 깁니다/u);
});
