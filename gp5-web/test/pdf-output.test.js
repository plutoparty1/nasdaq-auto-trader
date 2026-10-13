import { test } from 'node:test';
import assert from 'node:assert/strict';
import { EventEmitter, getEventListeners } from 'node:events';
import { collectPdf } from '../src/pdf-output.js';

function documentStream(end = () => {}) {
  const doc = new EventEmitter();
  doc.end = end;
  doc.destroy = () => { doc.destroyed = true; queueMicrotask(() => doc.emit('error', new Error('late shutdown error'))); };
  return doc;
}

test('PDF collector preserves chunks and releases all listeners after success', async () => {
  const doc = documentStream(() => { doc.emit('data', new TextEncoder().encode('%PDF-')); doc.emit('end'); });
  const controller = new AbortController();
  const output = collectPdf(doc, { signal: controller.signal });
  const blob = await output.finish();
  assert.equal(blob.type, 'application/pdf');
  assert.equal(await blob.text(), '%PDF-');
  assert.equal(doc.eventNames().length, 0);
  assert.equal(getEventListeners(controller.signal, 'abort').length, 0);
});

for (const event of ['error', 'close', 'abort']) {
  test(`PDF collection settles and cleans up when ${event} occurs before end`, async () => {
    const doc = documentStream();
    const controller = new AbortController();
    const output = collectPdf(doc, { signal: controller.signal });
    const pending = output.finish();
    const rejection = assert.rejects(pending, event === 'abort' ? { name: 'AbortError' } : Error);
    if (event === 'abort') controller.abort();
    else doc.emit(event, new Error('stream failed'));
    await rejection;
    assert.equal(doc.destroyed, true);
    assert.equal(doc.listenerCount('end'), 0);
    assert.equal(doc.listenerCount('data'), 0);
    assert.equal(doc.listenerCount('close'), 0);
    assert.equal(getEventListeners(controller.signal, 'abort').length, 0);
  });
}

test('PDF size limit rejects before finalization and disposes the stream', async () => {
  const doc = documentStream();
  const output = collectPdf(doc, { maxBytes: 4 });
  doc.emit('data', new Uint8Array(5));
  await assert.rejects(output.finish(), /PDF 파일이 너무 큽니다/u);
  assert.equal(doc.destroyed, true);
});

test('discard settles a waiting collector and removes its end listener', async () => {
  const doc = documentStream();
  const output = collectPdf(doc);
  const pending = assert.rejects(output.finish(), { name: 'AbortError' });
  output.discard();
  await pending;
  assert.equal(doc.listenerCount('end'), 0);
});

test('synchronous finalization failure cleans up listeners', async () => {
  const doc = documentStream(() => { throw new Error('font subset failed'); });
  const output = collectPdf(doc);
  await assert.rejects(output.finish(), /font subset failed/u);
  assert.equal(doc.listenerCount('end'), 0);
  assert.equal(doc.listenerCount('data'), 0);
});
