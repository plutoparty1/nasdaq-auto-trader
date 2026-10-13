import { readdir } from 'node:fs/promises';
import { spawnSync } from 'node:child_process';
import path from 'node:path';

for (const folder of ['src', 'scripts', 'test']) {
  for (const name of await readdir(folder)) {
    if (!name.endsWith('.js') && !name.endsWith('.mjs')) continue;
    const result = spawnSync(process.execPath, ['--check', path.join(folder, name)], { stdio: 'inherit' });
    if (result.status !== 0) process.exit(result.status ?? 1);
  }
}
console.log('JavaScript syntax checks passed.');
