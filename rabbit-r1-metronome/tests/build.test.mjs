import assert from 'node:assert/strict';
import test from 'node:test';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';

test('standalone build has exactly one syntactically valid inline script per page', async () => {
  for (const page of ['index', 'install']) {
    const html = await readFile(new URL('../dist/' + page + '.html', import.meta.url), 'utf8');
    const scripts = [...html.matchAll(/<script(?: type="module")?>([\s\S]*?)<\/script>/g)];
    assert.equal(scripts.length, 1);
    assert.equal((html.match(/<script/g) || []).length, 1);
    assert.equal(html.includes('src="src/'), false);
    assert.doesNotThrow(() => new vm.Script('(async () => {' + scripts[0][1] + '})'));
  }
});
