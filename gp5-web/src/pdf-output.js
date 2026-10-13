const ignoreLateError = () => {};

export function collectPdf(doc, { signal, maxBytes = 100 * 1024 * 1024 } = {}) {
  let length = 0;
  let failure;
  let complete = false;
  let blob;
  let pending;
  let settle;
  const chunks = [];
  const cleanup = () => {
    doc.off('data', onData);
    doc.off('end', onEnd);
    doc.off('error', fail);
    doc.off('close', onClose);
    signal?.removeEventListener('abort', onAbort);
  };
  function fail(error) {
    if (failure || complete) return;
    failure = error instanceof Error ? error : new Error(String(error));
    cleanup();
    chunks.length = 0;
    settle?.reject(failure);
    // The browser build has no destroy(); Node-compatible streams may emit a late error during shutdown.
    if (typeof doc.destroy === 'function') {
      doc.on('error', ignoreLateError);
      try { doc.destroy(); } catch { /* Preserve the original conversion failure. */ }
    }
  }
  const onData = chunk => {
    length += chunk.byteLength;
    if (length > maxBytes) {
      fail(new Error('PDF 파일이 너무 큽니다. 악보를 짧게 나누어 주세요.'));
      return;
    }
    chunks.push(chunk);
  };
  const onEnd = () => {
    if (failure || complete) return;
    try { blob = new Blob(chunks, { type: 'application/pdf' }); }
    catch (error) { fail(error); return; }
    complete = true;
    cleanup();
    chunks.length = 0;
    settle?.resolve(blob);
  };
  const onClose = () => fail(new Error('PDF 생성이 완료되기 전에 연결이 종료되었습니다.'));
  const onAbort = () => fail(new DOMException('변환을 취소했습니다.', 'AbortError'));
  doc.on('error', fail);
  doc.on('close', onClose);
  doc.on('end', onEnd);
  doc.on('data', onData);
  signal?.addEventListener('abort', onAbort, { once: true });
  if (signal?.aborted) onAbort();
  return {
    finish() {
      if (failure) return Promise.reject(failure);
      if (complete) return Promise.resolve(blob);
      if (pending) return pending;
      pending = new Promise((resolve, reject) => { settle = { resolve, reject }; });
      try { doc.end(); } catch (error) { fail(error); }
      return pending;
    },
    discard() { if (!complete && !failure) onAbort(); },
  };
}
