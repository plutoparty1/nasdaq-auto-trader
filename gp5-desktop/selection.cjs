'use strict';

function parseSelection(indices, trackCount) {
  if (!Array.isArray(indices) || indices.length === 0) {
    throw new Error('PDF로 만들 악기를 하나 이상 선택해 주세요.');
  }
  if (indices.length > trackCount) throw new Error('선택한 악기 정보가 올바르지 않습니다.');
  const selected = new Set();
  for (const index of indices) {
    if (!Number.isInteger(index) || index < 0 || index >= trackCount || selected.has(index)) {
      throw new Error('선택한 악기 정보가 올바르지 않습니다.');
    }
    selected.add(index);
  }
  return Object.freeze([...selected]);
}

module.exports = { parseSelection };
