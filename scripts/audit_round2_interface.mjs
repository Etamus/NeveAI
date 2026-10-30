import assert from 'node:assert/strict';
import { createServer as createHttpServer } from 'node:http';
import fs from 'node:fs/promises';
import { resolve, extname, sep } from 'node:path';
import { performance } from 'node:perf_hooks';
import { createServer as createViteServer } from 'vite';
import { chromium } from '../logs/ui-image-26/node_modules/playwright/index.mjs';
import { installMobileOfflineApi } from './fixtures/mobile-offline-api.mjs';

const output = 'logs/round2-audit';
await fs.mkdir(output, { recursive: true });
const root = resolve('build');
const server = createHttpServer(async (request, response) => {
  let file = resolve(root, '.' + decodeURIComponent(new URL(request.url, 'http://local').pathname));
  if (file !== root && !file.startsWith(root + sep)) {
    response.writeHead(403).end();
    return;
  }
  try {
    if ((await fs.stat(file)).isDirectory()) file = resolve(file, 'index.html');
    await fs.access(file);
  } catch {
    file = resolve(root, 'index.html');
  }
  response.setHeader('Content-Type', {
    '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css',
    '.json': 'application/json', '.woff2': 'font/woff2', '.svg': 'image/svg+xml'
  }[extname(file)] ?? 'application/octet-stream');
  response.end(await fs.readFile(file));
});

let browser, vite;
const results = { library: [], lexer: [] };
const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=', 'base64');
const files = Array.from({ length: 500 }, (_, index) => ({
  id: 'audit-' + index, filename: 'Fixture ' + index + '.png',
  created_at: 1700000000, updated_at: 1700000000,
  meta: { content_type: 'image/png', size: png.length, data: { generated: true } }
}));

try {
  await new Promise(resolve => server.listen(5192, '127.0.0.1', resolve));
  browser = await chromium.launch();
  for (const width of [1440, 390]) {
    const page = await browser.newPage({ viewport: { width, height: 1000 } });
    page.setDefaultTimeout(20000);
    const errors = [], requests = [];
    page.on('pageerror', error => errors.push(error.message));
    await installMobileOfflineApi(page);
    await page.route('**/api/v1/files/**', route => {
      const url = new URL(route.request().url());
      if (url.pathname.endsWith('/generated')) {
        const skip = Number(url.searchParams.get('skip') ?? 0);
        requests.push({ skip, at: performance.now() });
        return route.fulfill({ json: files.slice(skip, skip + 50) });
      }
      if (/\/(thumbnail|content)$/.test(url.pathname)) {
        return route.fulfill({ contentType: 'image/png', body: png });
      }
      return route.fallback();
    });
    await page.goto('http://127.0.0.1:5192/library', { waitUntil: 'networkidle' });
    await page.waitForFunction(() => document.querySelectorAll('.library-grid > article').length === 50);
    await page.evaluate(() => {
      window.__round2LongTasks = [];
      window.__round2Observer = new PerformanceObserver(list => {
        window.__round2LongTasks.push(...list.getEntries().map(entry => entry.duration));
      });
      window.__round2Observer.observe({ type: 'longtask' });
    });
    for (const count of [50, 500]) {
      const started = performance.now();
      if (count === 500) {
        for (let expected = 100; expected <= 500; expected += 50) {
          await page.getByText(/^(Load more|Carregar mais)$/).click();
          await page.waitForFunction(n => document.querySelectorAll('.library-grid > article').length === n, expected);
        }
      }
      const appendWallMs = performance.now() - started;
      const main = page.locator('main').last();
      await main.evaluate(element => { element.scrollTop = 0; });
      const rect = await main.boundingBox();
      await page.mouse.move(rect.x + rect.width / 2, rect.y + rect.height / 2);
      await page.evaluate(() => {
        window.__round2Frames = [];
        window.__round2Sampling = true;
        let previous = performance.now();
        const sample = now => {
          window.__round2Frames.push(now - previous);
          previous = now;
          if (window.__round2Sampling) requestAnimationFrame(sample);
        };
        requestAnimationFrame(sample);
      });
      for (let i = 0; i < 35; i++) {
        await page.mouse.wheel(0, 450);
        await page.waitForTimeout(16);
      }
      const measured = await page.evaluate(() => {
        window.__round2Sampling = false;
        const main = document.querySelector('main');
        const frames = window.__round2Frames.filter(n => n > 0).sort((a, b) => a - b);
        return {
          cards: document.querySelectorAll('.library-grid > article').length,
          descendants: document.querySelectorAll('.library-grid *').length,
          scrollTop: main.scrollTop, scrollMax: main.scrollHeight - main.clientHeight,
          frameP95: frames[Math.floor(frames.length * 0.95)],
          frameMax: frames.at(-1), longTasks: [...window.__round2LongTasks]
        };
      });
      results.library.push({ width, count, appendWallMs, ...measured });
      console.log(JSON.stringify(results.library.at(-1)));
    }
    const before = requests.length, start = performance.now();
    await page.evaluate(() => window.dispatchEvent(new Event('focus')));
    for (let i = 0; requests.length < before + 10 && i < 200; i++) await page.waitForTimeout(25);
    assert.equal(requests.length - before, 10);
    results.library.push({ width, action: 'refresh-500', requests: requests.length - before, wallMs: performance.now() - start });
    await page.screenshot({ path: output + '/library-' + width + '.png' });
    assert.deepEqual(errors, []);
    await page.close();
  }
  vite = await createViteServer({ server: { middlewareMode: true, watch: { ignored: ['**/logs/**', '**/backend/**'] } } });
  const { lexChatMarkdown } = await vite.ssrLoadModule('/src/lib/utils/marked/chat-lexer.ts');
  const paragraph = '## Heading\n\nA **formatted** paragraph with a [link](https://example.com).\n\n| A | B |\n| --- | --- |\n| One | Two |\n\n```js\nconst value = 1;\n```\n\n';
  for (const length of [8192, 32768, 131072]) {
    const text = paragraph.repeat(Math.ceil(length / paragraph.length)).slice(0, length);
    for (let i = 0; i < 4; i++) lexChatMarkdown(text);
    const times = [];
    for (let i = 0; i < 15; i++) {
      const started = performance.now(); lexChatMarkdown(text); times.push(performance.now() - started);
    }
    times.sort((a, b) => a - b);
    results.lexer.push({ characters: length, medianMs: times[7], p95Ms: times[14] });
  }
  await fs.writeFile(output + '/metrics.json', JSON.stringify(results, null, 2));
  console.log(JSON.stringify(results.lexer));
} finally {
  await vite?.close();
  await browser?.close();
  await new Promise(resolve => server.close(resolve));
}
