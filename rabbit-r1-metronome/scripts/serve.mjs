import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';

const port = Number(process.env.PULSE_PORT || 4173);
const files = new Map([['/', 'index.html'], ['/index.html', 'index.html'], ['/install.html', 'install.html'], ['/README.md', 'README.md']]);
createServer(async (request, response) => {
  let pathname;
  try { pathname = new URL(request.url, 'http://localhost').pathname; }
  catch { response.writeHead(400); response.end('Invalid URL'); return; }
  const file = files.get(pathname);
  if (!file) { response.writeHead(404); response.end('Not found'); return; }
  try {
    const content = await readFile(new URL(`../dist/${file}`, import.meta.url));
    response.writeHead(200, { 'Content-Type': file.endsWith('.html') ? 'text/html; charset=utf-8' : 'text/plain; charset=utf-8', 'Cache-Control': 'no-store' });
    response.end(content);
  } catch { response.writeHead(503); response.end('Run npm run build first.'); }
}).listen(port, '127.0.0.1', () => console.log(`PULSE preview: http://127.0.0.1:${port}`));
