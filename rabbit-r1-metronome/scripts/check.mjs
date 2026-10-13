import { readdir } from 'node:fs/promises';
import { spawnSync } from 'node:child_process';

let failed = false;
for (const directory of ['src', 'scripts', 'tests']) {
  for (const file of await readdir(directory)) {
    if (!/\.m?js$/.test(file)) continue;
    const result = spawnSync(process.execPath, ['--check', `${directory}/${file}`], { stdio: 'inherit' });
    if (result.status !== 0) failed = true;
  }
}
if (failed) process.exitCode = 1;
else console.log('All JavaScript syntax checks passed.');
