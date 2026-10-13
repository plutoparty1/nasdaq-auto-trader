import { build } from 'esbuild';
import { readFile, writeFile, mkdir, copyFile } from 'node:fs/promises';

await mkdir('dist', { recursive: true });
const app = await build({ entryPoints: ['src/app.js'], bundle: true, minify: true, target: ['chrome90'], format: 'esm', write: false });
const css = (await readFile('src/style.css', 'utf8')).replace(/\s+/g, ' ');
const html = (await readFile('index.html', 'utf8'))
  .replace('<link rel="stylesheet" href="src/style.css">', () => `<style>${css}</style>`)
  .replace('<script type="module" src="src/app.js"></script>', () => `<script type="module">${app.outputFiles[0].text.replace(/<\/script/gi, '<\\/script')}</script>`);
await writeFile('dist/index.html', html);
const install = await build({ entryPoints: ['src/install.js'], bundle: true, minify: true, target: ['chrome90'], format: 'iife', write: false });
await writeFile('dist/install.html', (await readFile('install.html', 'utf8'))
  .replace('<script type="module" src="src/install.js"></script>', () => `<script>${install.outputFiles[0].text.replace(/<\/script/gi, '<\\/script')}</script>`));
await copyFile('docs/INSTALL.md', 'dist/README.md');
console.log(`Built self-contained app (${Buffer.byteLength(html)} bytes) and installation QR tool.`);
