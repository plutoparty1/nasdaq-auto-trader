import { readdir, readFile, stat, mkdir, writeFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { zipSync } from 'fflate';
import path from 'node:path';

const root = process.cwd();
const pkg = JSON.parse(await readFile('package.json', 'utf8'));
const tag = process.env.GITHUB_REF_TYPE === 'tag' ? process.env.GITHUB_REF_NAME : null;
if (tag && tag !== `v${pkg.version}`) throw new Error('Release tag must match package.json version.');
const sourcePaths = ['.github', '.gitignore', '.gitattributes', 'src', 'scripts', 'test', 'public', 'docs',
  'index.html', 'package.json', 'package-lock.json', 'vite.config.js', 'playwright.config.js',
  'README.md', 'ARCHITECTURE.md', 'CONTRIBUTING.md', 'VERIFICATION.md', 'CHANGELOG.md', 'DESIGN.md', 'LICENSE'];
const timestamp = new Date('2026-01-01T00:00:00Z');

async function collect(base, relative, entries) {
  const absolute = path.join(base, relative);
  const info = await stat(absolute);
  if (info.isDirectory()) {
    for (const name of (await readdir(absolute)).sort()) await collect(base, path.join(relative, name), entries);
    return;
  }
  if (!info.isFile()) throw new Error(`Unsupported archive entry: ${relative}`);
  entries[relative.split(path.sep).join('/')] = [new Uint8Array(await readFile(absolute)), { mtime: timestamp }];
}

await readFile('dist/index.html');
await mkdir('release', { recursive: true });
const checksums = [];
for (const [name, base, paths] of [
  ['GP5-PDF-Web-site.zip', path.join(root, 'dist'), await readdir('dist')],
  ['GP5-PDF-Web-source.zip', root, sourcePaths],
]) {
  const entries = Object.create(null);
  for (const item of paths) await collect(base, item, entries);
  const bytes = zipSync(entries, { level: 6 });
  await writeFile(path.join('release', name), bytes);
  checksums.push(`${createHash('sha256').update(bytes).digest('hex')}  ${name}`);
  console.log(`${name}: ${Object.keys(entries).length} files, ${bytes.length} bytes`);
}
await writeFile('release/SHA256SUMS.txt', `${checksums.join('\n')}\n`);
await writeFile('release/NOTES.md', `GP5 PDF Web ${pkg.version}\n\n` +
  'Convert GP5 scores on iPhone/iPad Safari, Android Chrome, Windows and Mac. Save/open individual PDFs, share files where supported, or download one ZIP. Conversion stays in your browser.\n\n' +
  'Mobile WebKit/Chromium emulation is automated; native OS file/share dialogs still need physical-device verification.\n\n' +
  '- `GP5-PDF-Web-site.zip`: built static site, ready for static hosting.\n' +
  '- `GP5-PDF-Web-source.zip`: standalone source including automated tests and GitHub workflows.\n' +
  '- `SHA256SUMS.txt`: checksums for both archives.\n\n' +
  'See CHANGELOG.md and VERIFICATION.md in the source archive for changes, verification, and limits.\n');
