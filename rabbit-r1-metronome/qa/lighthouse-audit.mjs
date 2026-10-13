import { spawn } from 'node:child_process';
import { createHash } from 'node:crypto';
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { setTimeout as delay } from 'node:timers/promises';
import { chromium } from 'playwright';
import lighthouse, { desktopConfig } from 'lighthouse';

const root = fileURLToPath(new URL('../', import.meta.url));
const output = new URL('./', import.meta.url);
const serverPort = Number(process.env.PULSE_AUDIT_PORT || 4187);
const debugPort = Number(process.env.PULSE_AUDIT_DEBUG_PORT || 9237);
const origin = `http://127.0.0.1:${serverPort}`;
const categories = ['performance', 'accessibility', 'best-practices', 'seo'];
const pages = [{ name: 'app', path: '/' }, { name: 'install', path: '/install.html' }];
const profiles = ['mobile', 'desktop'];
const results = [];
let chromeContext;
let browserVersion;
let server;
let serverError;

const median = values => [...values].sort((left, right) => left - right)[Math.floor(values.length / 2)];
const score = value => value === null ? 'n/a' : Math.round(value * 100);

async function waitForServer() {
  for (let attempt = 0; attempt < 100; attempt++) {
    if (serverError) throw serverError;
    if (server.exitCode !== null) throw new Error(`Audit server exited: ${server.exitCode}`);
    try {
      const response = await fetch(origin);
      if (response.ok) return;
    } catch { /* The owned server may still be starting. */ }
    await delay(100);
  }
  throw new Error('Audit server did not become available.');
}

async function cleanup() {
  await chromeContext?.close().catch(() => undefined);
  if (server && server.exitCode === null) server.kill();
}

function summarizeRun(page, profile, run, result, filename) {
  const lhr = result.lhr;
  const scores = Object.fromEntries(categories.map(category => [category, lhr.categories[category].score]));
  const belowPerfect = Object.entries(lhr.audits)
    .filter(([, audit]) => typeof audit.score === 'number' && audit.score < 1)
    .map(([id, audit]) => ({ id, title: audit.title, score: audit.score, displayValue: audit.displayValue,
      description: audit.description, details: audit.details }));
  return { page: page.name, path: page.path, profile, run, filename, scores, belowPerfect,
    fetchTime: lhr.fetchTime, lighthouseVersion: lhr.lighthouseVersion, userAgent: lhr.userAgent,
    configSettings: lhr.configSettings, runtimeError: lhr.runtimeError, warnings: lhr.runWarnings,
    metrics: Object.fromEntries(['first-contentful-paint', 'largest-contentful-paint', 'speed-index',
      'total-blocking-time', 'cumulative-layout-shift'].map(id => [id, lhr.audits[id]?.numericValue])) };
}

async function writeSummary(builds) {
  const lines = ['# PULSE Lighthouse navigation audit', '',
    `Generated: ${new Date().toISOString()}`, '',
    'Installed Chrome was launched in an isolated Playwright profile with channel `chrome` and a local CDP port. Lighthouse used its Node API, not its CLI. The owned HTTP server served production `dist` files.', '',
    'Each page/profile has three independent navigations. The table uses the median category score, displayed on the usual 0–100 scale. Default mobile simulated throttling is 4× CPU with Lighthouse 13’s Slow 4G model; desktop uses the official desktop configuration. The exact viewport, user-agent, and throttling settings are retained in every JSON report.', '',
    '| Page | Profile | Performance | Accessibility | Best practices | SEO |',
    '| --- | --- | ---: | ---: | ---: | ---: |'];
  let perfect = true;
  for (const page of pages) {
    for (const profile of profiles) {
      const runs = results.filter(result => result.page === page.name && result.profile === profile);
      if (runs.length !== 3) { perfect = false; continue; }
      const medians = categories.map(category => median(runs.map(result => result.scores[category])));
      if (medians.some(value => value !== 1) || runs.some(run => run.runtimeError)) perfect = false;
      lines.push(`| ${page.path} | ${profile} | ${medians.map(score).join(' | ')} |`);
    }
  }
  lines.push('', `Lighthouse category gate: **${perfect ? 'PASS' : 'FAIL / incomplete'}**.`, '',
    '## Individual runs', '', '| Report | P | A | BP | SEO | FCP ms | LCP ms | TBT ms | CLS |',
    '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |');
  for (const result of results) {
    const metric = result.metrics;
    lines.push(`| [${result.filename}](${result.filename}) | ${categories.map(category => score(result.scores[category])).join(' | ')} | ${Math.round(metric['first-contentful-paint'])} | ${Math.round(metric['largest-contentful-paint'])} | ${Math.round(metric['total-blocking-time'])} | ${metric['cumulative-layout-shift'].toFixed(4)} |`);
  }
  lines.push('', '## Audit findings', '');
  const findings = new Map();
  for (const result of results) {
    for (const audit of result.belowPerfect) {
      const key = `${result.page}/${result.profile}/${audit.id}`;
      const item = findings.get(key) || { page: result.page, profile: result.profile, ...audit, runs: [], scores: [] };
      item.runs.push(result.run);
      item.scores.push(audit.score);
      findings.set(key, item);
    }
  }
  if (!findings.size) lines.push('No numerically scored audits fell below 1.');
  for (const finding of findings.values()) {
    lines.push(`- ${finding.page}, ${finding.profile}: \`${finding.id}\` — ${finding.title}; runs ${finding.runs.join(', ')}, minimum audit score ${Math.min(...finding.scores)}${finding.displayValue ? `; ${finding.displayValue}` : ''}.`);
  }
  const warnings = results.flatMap(result => (result.warnings || []).map(warning => `${result.filename}: ${warning}`));
  lines.push('', '## Scope and reproducibility', '',
    `- Chrome: ${browserVersion}; Lighthouse: ${results[0]?.lighthouseVersion || 'unknown'}; Node: ${process.version}.`,
    '- Run: `node qa/lighthouse-audit.mjs`. Override isolated ports using `PULSE_AUDIT_PORT` and `PULSE_AUDIT_DEBUG_PORT` if needed.',
    '- Audits cover initial navigation and visible starting states. Interaction latency, playback timing, QR scanning, native SDK behavior, and physical r1 performance require their separate functional/device tests.',
    '- Loopback omits public DNS/TLS/CDN latency. No public deployment URL was available; re-audit the hosted URLs after deployment.',
    '- All functional content and animations remain enabled. Product files were not edited by this audit.',
    '- No React code is present, so React-specific tooling does not apply.', '',
    'Production input fingerprints:', '', '| File | Bytes | SHA-256 |', '| --- | ---: | --- |');
  for (const build of builds) lines.push(`| ${build.path} | ${build.bytes} | \`${build.sha256}\` |`);
  if (warnings.length) lines.push('', 'Run warnings:', '', ...warnings.map(warning => `- ${warning}`));
  await writeFile(new URL('lighthouse-summary.md', output), `${lines.join('\n')}\n`);
  await writeFile(new URL('lighthouse-runs.json', output), `${JSON.stringify({ generatedAt: new Date().toISOString(), builds, results }, null, 2)}\n`);
  return perfect;
}

try {
  await mkdir(output, { recursive: true });
  const builds = await Promise.all(['index.html', 'install.html'].map(async filename => {
    const content = await readFile(new URL(`../dist/${filename}`, import.meta.url));
    return { path: `dist/${filename}`, bytes: content.length, sha256: createHash('sha256').update(content).digest('hex') };
  }));
  server = spawn(process.execPath, ['scripts/serve.mjs'], {
    cwd: root, env: { ...process.env, PULSE_PORT: String(serverPort) }, windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'],
  });
  server.on('error', error => { serverError = error; });
  server.stderr.on('data', data => process.stderr.write(data));
  await waitForServer();
  chromeContext = await chromium.launchPersistentContext('', { channel: 'chrome', headless: true,
    args: [`--remote-debugging-port=${debugPort}`, '--remote-debugging-address=127.0.0.1'] });
  browserVersion = (await (await fetch(`http://127.0.0.1:${debugPort}/json/version`)).json()).Browser;
  const page = chromeContext.pages()[0] || await chromeContext.newPage();
  await page.goto(origin);
  await page.locator('#play').waitFor({ state: 'visible' });
  for (const target of pages) {
    for (const profile of profiles) {
      for (let run = 1; run <= 3; run++) {
        const filename = `lighthouse-${target.name}-${profile}-${run}.json`;
        console.log(`WORKING: ${target.name} ${profile} run ${run}/3`);
        const result = await lighthouse(`${origin}${target.path}`, {
          port: debugPort, output: 'json', logLevel: 'error', onlyCategories: categories,
        }, profile === 'desktop' ? desktopConfig : undefined);
        if (!result) throw new Error(`No Lighthouse result: ${filename}`);
        await writeFile(new URL(filename, output), `${JSON.stringify(result.lhr, null, 2)}\n`);
        const summary = summarizeRun(target, profile, run, result, filename);
        results.push(summary);
        console.log(`RESULT: ${target.name} ${profile} ${run}: ${categories.map(category => `${category}=${score(summary.scores[category])}`).join(' ')}`);
        if (summary.runtimeError) throw new Error(`${filename}: ${summary.runtimeError.message}`);
      }
    }
  }
  const perfect = await writeSummary(builds);
  console.log(`COMPLETE: ${results.length} audits; median category gate ${perfect ? 'PASS' : 'FAIL'}. Reports: qa/lighthouse-summary.md`);
  if (!perfect) process.exitCode = 1;
} finally {
  await cleanup();
}
