const fs = require('node:fs');
const path = require('node:path');
const { spawnSync } = require('node:child_process');

const files = fs.readdirSync(__dirname)
  .filter(name => name.endsWith('.test.cjs'))
  .map(name => path.join(__dirname, name));
const result = spawnSync(require('electron'), ['--test', ...files], {
  stdio: 'inherit',
  env: { ...process.env, ELECTRON_RUN_AS_NODE: '1' },
});
if (result.error) console.error(result.error);
process.exitCode = result.status ?? 1;
