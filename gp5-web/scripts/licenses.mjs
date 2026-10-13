import { execSync } from 'node:child_process';
import { readFile, readdir, writeFile, mkdir } from 'node:fs/promises';
import path from 'node:path';

const locations = execSync('npm ls --omit=dev --all --parseable', { encoding: 'utf8' }).trim().split(/\r?\n/).slice(1);
const sections = [];
for (const location of locations) {
  const pkg = JSON.parse(await readFile(path.join(location, 'package.json'), 'utf8'));
  const files = (await readdir(location)).filter(name => /^(licen[sc]e|copying|notice)(\.|$)/i.test(name));
  const texts = await Promise.all(files.map(name => readFile(path.join(location, name), 'utf8')));
  sections.push(`${pkg.name}@${pkg.version} — ${pkg.license || 'See upstream notices'}\n${texts.join('\n\n')}`);
}
await mkdir('public/LICENSES', { recursive: true });
await writeFile('public/LICENSES/npm-notices.txt', sections.join('\n\n----------------------------------------\n\n'));
console.log(`Preserved license notices for ${locations.length} runtime packages.`);
