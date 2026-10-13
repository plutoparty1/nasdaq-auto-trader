import assert from 'node:assert/strict';
import test from 'node:test';
import { spawn } from 'node:child_process';
import http from 'node:http';
import { once } from 'node:events';

test('malformed preview URLs return 400 without terminating the server', async t => {
  const server = spawn(process.execPath, ['scripts/serve.mjs'], {
    env: { ...process.env, PULSE_PORT: '4191' }, windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'],
  });
  t.after(() => server.kill());
  await Promise.race([
    once(server.stdout, 'data'),
    once(server, 'exit').then(([code]) => { throw new Error('Preview exited: ' + code); }),
  ]);
  const get = path => new Promise((resolve, reject) => {
    const request = http.get({ host: '127.0.0.1', port: 4191, path }, response => {
      response.resume();
      response.on('end', () => resolve(response.statusCode));
    });
    request.on('error', reject);
    request.setTimeout(2000, () => { request.destroy(new Error('Preview timed out')); });
  });
  assert.equal(await get('//['), 400);
  assert.equal(await get('/'), 200);
  assert.equal(server.exitCode, null);
});
