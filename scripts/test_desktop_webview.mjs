import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import { spawn, execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { chromium } from '../logs/ui-image-26/node_modules/playwright/index.mjs';

const root = process.cwd();
const execute = promisify(execFile);
async function inspectTarget(predicate, expression, screenshot) {
  let target;
  for (let attempt = 0; attempt < 100; attempt++) {
    const targets = await (await fetch('http://127.0.0.1:9228/json/list')).json();
    target = targets.find(predicate);
    if (target) break;
    await new Promise(resolve => setTimeout(resolve, 50));
  }
  assert(target, 'Native popup target was not created');
  const socket = new WebSocket(target.webSocketDebuggerUrl);
  try {
    await new Promise((resolve, reject) => { socket.addEventListener('open', resolve, { once: true }); socket.addEventListener('error', reject, { once: true }); });
    const value = await new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(Error('Popup inspection timeout')), 5000);
      socket.addEventListener('message', event => {
        const message = JSON.parse(event.data);
        if (message.id !== 1) return;
        clearTimeout(timer);
        if (message.error || message.result?.exceptionDetails) reject(Error('Popup evaluation failed'));
        else resolve(message.result?.result?.value);
      });
      socket.send(JSON.stringify({ id: 1, method: 'Runtime.evaluate', params: { expression, returnByValue: true } }));
    });
    if (screenshot) {
      await new Promise(resolve => setTimeout(resolve, 500));
      let data;
      for (let attempt = 0; attempt < 5; attempt++) {
        try { data = await new Promise((resolve, reject) => {
        const timer = setTimeout(() => reject(Error('Popup screenshot timeout')), 5000);
        socket.addEventListener('message', event => {
          const message = JSON.parse(event.data);
          if (message.id !== 2 + attempt) return;
          clearTimeout(timer); message.error ? reject(Error('Popup screenshot failed')) : resolve(message.result.data);
        });
        socket.send(JSON.stringify({ id: 2 + attempt, method: 'Page.captureScreenshot', params: { format: 'png' } }));
      }); break; } catch (error) {
          if (attempt === 4) throw error;
          await new Promise(resolve => setTimeout(resolve, 500));
        }
      }
      await fs.writeFile(screenshot, Buffer.from(data, 'base64'));
    }
    return value;
  } finally { socket.close(); }
}
const state = JSON.parse(await fs.readFile('.desktop/installed.json', 'utf8'));
const directory = path.join(root, 'logs', 'webview2-native-test');
await fs.mkdir(directory, { recursive: true });
const ready = path.join(directory, 'ready.tmp');
await fs.rm(ready, { force: true });
const child = spawn(path.join(root, '.desktop', state.host), ['--root', root, '--runtime', path.join(root, '.desktop', state.runtime), '--profile', path.join(directory, 'profile'), '--ready-file', ready], {
  windowsHide: true, env: { ...process.env, NEVE_WEBVIEW2_DEBUG_PORT: '9228', NEVE_WEBVIEW2_TEST_MODE: '1', WEBVIEW2_DEFAULT_BACKGROUND_COLOR: 'FF000000' }
});
let browser;
const result = { runtime: state.runtime_version, errors: [] };
try {
  for (let attempt = 0; attempt < 100; attempt++) {
    try { browser = await chromium.connectOverCDP('http://127.0.0.1:9228'); break; }
    catch { if (child.exitCode !== null) throw Error('Native host exited: ' + child.exitCode); await new Promise(resolve => setTimeout(resolve, 200)); }
  }
  assert(browser, 'No native WebView2 CDP endpoint');
  const context = browser.contexts()[0];
  const page = context.pages()[0] ?? await context.waitForEvent('page');
  page.on('pageerror', error => result.errors.push(error.message));
  const network = await context.newCDPSession(page);
  await network.send('Network.enable');
  network.on('Network.webSocketHandshakeResponseReceived', event => { if (event.response.status === 101) result.webSocketConnected = true; });
  await page.waitForFunction(() => window.__NEVE_WEBVIEW2__ === true, { timeout: 60000 });
  for (let attempt = 0; attempt < 300; attempt++) {
    try { await fs.access(ready); break; } catch { await new Promise(resolve => setTimeout(resolve, 200)); }
  }
  await fs.access(ready);
  result.startupWindow = JSON.parse((await execute('powershell.exe', ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', 'scripts/verify_desktop_window.ps1', '-WindowProcessId', String(child.pid), '-Action', 'Inspect'], { windowsHide: true })).stdout);
  assert.deepEqual(result.startupWindow, { Minimized: false, Visible: true, Foreground: true });
  result.url = page.url();
  result.userAgent = await page.evaluate(() => navigator.userAgent);
  result.browserVersion = browser.version();
  assert(result.userAgent.includes('156.0.'));
  result.api = await page.evaluate(async () => {
    const headers = { Authorization: 'Bearer ' + localStorage.token };
    return Promise.all(['/health', '/api/tasks', '/api/v1/chats/?page=1', '/api/v1/files/generated?kind=all&skip=0&limit=50'].map(async url => {
      const response = await fetch(url, { headers });
      return { url, status: response.status };
    }));
  });
  assert(result.api.every(response => response.status === 200));
  await page.evaluate(() => localStorage.setItem('neve-webview-test', 'persisted'));
  await page.reload({ waitUntil: 'networkidle' });
  assert.equal(await page.evaluate(() => localStorage.getItem('neve-webview-test')), 'persisted');
  assert.equal(result.webSocketConnected, true);
  result.capabilities = await page.evaluate(() => ({
    clipboard: Boolean(navigator.clipboard?.writeText),
    fileReader: Boolean(window.FileReader),
    webSocket: Boolean(window.WebSocket),
    worker: Boolean(window.Worker),
    mp4: document.createElement('video').canPlayType('video/mp4; codecs="avc1.42E01E"'),
    png: document.createElement('canvas').toDataURL().startsWith('data:image/png')
  }));
  assert(Object.values(result.capabilities).every(Boolean));
  await page.screenshot({ path: path.join(directory, 'light.png') });
  await page.evaluate(() => { document.documentElement.classList.add('dark'); localStorage.setItem('theme', 'dark'); });
  await page.waitForTimeout(200);
  await page.screenshot({ path: path.join(directory, 'dark.png') });
  const session = await context.newCDPSession(page);
  result.hostPid = child.pid;
  const cycles = await execute('powershell.exe', ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', 'scripts/verify_desktop_window.ps1', '-WindowProcessId', String(child.pid)], { windowsHide: true });
  result.cycles = JSON.parse(cycles.stdout);
  assert(result.cycles.Samples.every(sample => sample.Difference < 20), JSON.stringify(result.cycles));
  assert.equal(await page.evaluate(() => window.__NEVE_WEBVIEW2__), true);
  const marker = 'NeveAI native clipboard ' + Date.now();
  const clipboardReady = path.join(directory, 'clipboard-ready.json');
  const clipboardDone = path.join(directory, 'clipboard-done.tmp');
  await fs.rm(clipboardReady, { force: true }); await fs.rm(clipboardDone, { force: true });
  const clipboardCheck = execute('powershell.exe', ['-NoProfile', '-STA', '-ExecutionPolicy', 'Bypass', '-File', 'scripts/verify_desktop_clipboard.ps1', '-Directory', directory, '-Expected', marker, '-VerifyHtml'], { windowsHide: true });
  for (let attempt = 0; attempt < 100; attempt++) {
    try { await fs.access(clipboardReady); break; } catch { await new Promise(resolve => setTimeout(resolve, 30)); }
  }
  if (JSON.parse(await fs.readFile(clipboardReady, 'utf8')).safe) {
    try {
      await page.evaluate(text => { const button = document.createElement('button'); button.id = 'native-clipboard-check'; button.textContent = 'Clipboard'; button.style.cssText = 'position:fixed;top:80px;left:400px;z-index:999999'; button.onclick = () => { window.__clipboardCheck = navigator.clipboard.write([new ClipboardItem({ 'text/plain': new Blob([text], { type: 'text/plain' }), 'text/html': new Blob(['<strong>' + text + '</strong>'], { type: 'text/html' }) })]).then(() => true); }; document.body.append(button); }, marker);
      await page.locator('#native-clipboard-check').click();
      assert.equal(await page.evaluate(() => window.__clipboardCheck), true);
      await page.locator('#chat-input').click();
      await page.locator('#chat-input').press('Control+V');
      assert((await page.locator('#chat-input').innerText()).includes(marker));
      await page.locator('#chat-input').press('Control+A'); await page.locator('#chat-input').press('Backspace');
      result.clipboardPaste = true;
      await page.locator('#native-clipboard-check').evaluate(button => button.remove());
    } finally { await fs.writeFile(clipboardDone, 'done'); }
  }
  result.clipboard = JSON.parse((await clipboardCheck).stdout);
  const nextReady = path.join(directory, 'second-instance.tmp');
  await fs.rm(nextReady, { force: true });
  await execute(path.join(root, '.desktop', state.host), ['--root', root, '--runtime', path.join(root, '.desktop', state.runtime), '--profile', path.join(directory, 'profile'), '--ready-file', nextReady], { windowsHide: true });
  await fs.access(nextReady);
  result.singleInstance = true;
  const videoBytes = await fs.readFile(path.join(directory, 'probe.mp4'));
  result.videoPlayback = await page.evaluate(async base64 => {
    const url = URL.createObjectURL(new Blob([Uint8Array.from(atob(base64), character => character.charCodeAt(0))], { type: 'video/mp4' }));
    const video = document.createElement('video');
    video.muted = true; video.playsInline = true;
    video.style.cssText = 'position:fixed;bottom:20px;right:20px;width:160px;height:96px;z-index:999999';
    document.body.append(video); video.src = url;
    await video.play();
    await new Promise(resolve => { video.ontimeupdate = () => { if (video.currentTime >= 0.3) resolve(); }; });
    const canvas = document.createElement('canvas'); canvas.width = canvas.height = 1;
    const ctx = canvas.getContext('2d'); ctx.drawImage(video, 0, 0, 1, 1);
    const info = { duration: video.duration, currentTime: video.currentTime, width: video.videoWidth, height: video.videoHeight, pixel: [...ctx.getImageData(0, 0, 1, 1).data] };
    video.pause(); video.remove(); URL.revokeObjectURL(url); return info;
  }, videoBytes.toString('base64'));
  assert(result.videoPlayback.currentTime >= 0.3 && result.videoPlayback.width === 160);

  await page.evaluate(() => window.open('/health', '_blank').focus());
  assert((await inspectTarget(target => target.url.endsWith('/health'), 'document.body.innerText')).includes('true'));
  result.popup = true;

  const blobUrl = await page.evaluate(() => { const url = URL.createObjectURL(new Blob(['Native blob preview'], { type: 'text/plain' })); window.open(url, '_blank').focus(); return url; });
  assert((await inspectTarget(target => target.url === blobUrl, 'document.body.innerText')).includes('Native blob preview'));
  result.blobPreview = true;
  const pdfBytes = await fs.readFile(path.join(directory, 'probe.pdf'));
  const pdfUrl = await page.evaluate(base64 => { const url = URL.createObjectURL(new Blob([Uint8Array.from(atob(base64), character => character.charCodeAt(0))], { type: 'application/pdf' })); window.open(url, '_blank').focus(); return url; }, pdfBytes.toString('base64'));
  result.pdf = await inspectTarget(target => target.url === pdfUrl, '({type:document.contentType,embed:Boolean(document.querySelector("embed"))})', path.join(directory, 'pdf-preview.png'));
  assert.equal(result.pdf.type, 'application/pdf');

  const png = Buffer.from(await page.evaluate(() => { const canvas = document.createElement('canvas'); canvas.width = 128; canvas.height = 128; const ctx = canvas.getContext('2d'); ctx.fillStyle = '#246f80'; ctx.fillRect(0, 0, 128, 128); return canvas.toDataURL().split(',')[1]; }), 'base64');
  await page.route('**/api/v1/files/**', async route => {
    const url = new URL(route.request().url());
    if (route.request().method() === 'POST' && url.pathname === '/api/v1/files/') return route.fulfill({ json: { id: 'desktop-probe', filename: 'desktop-probe.png', data: {}, meta: { name: 'desktop-probe.png', content_type: 'image/png', size: png.length }, created_at: 1, updated_at: 1 } });
    if (url.pathname.includes('desktop-probe/process/status')) return route.fulfill({ contentType: 'text/event-stream', body: 'data: {"status":"completed"}\n\n' });
    if (url.pathname.includes('desktop-probe/content')) return route.fulfill({ contentType: 'image/png', body: png });
    return route.continue();
  });
  await page.locator('[data-composer-root] input[type=file]').first().setInputFiles({ name: 'desktop-probe.png', mimeType: 'image/png', buffer: png });
  await page.waitForTimeout(400);
  await page.screenshot({ path: path.join(directory, 'attachment-in-progress.png') });
  await page.waitForFunction(() => [...document.querySelectorAll('.composer-image-thumbnail img, img.composer-image-thumbnail')].some(img => img.complete && img.naturalWidth > 0));
  result.attachment = true;
  await page.screenshot({ path: path.join(directory, 'attachment.png') });

  const downloadEvent = page.waitForEvent('download');
  await page.evaluate(() => { const link = document.createElement('a'); link.href = URL.createObjectURL(new Blob(['WebView2 download verified'], { type: 'text/plain' })); link.download = 'neve-desktop-test.txt'; document.body.append(link); link.click(); link.remove(); });
  const download = await downloadEvent;
  await download.saveAs(path.join(directory, 'download-verified.txt'));
  assert.equal(await fs.readFile(path.join(directory, 'download-verified.txt'), 'utf8'), 'WebView2 download verified');
  result.download = true;
  assert.deepEqual(result.errors, []);
  await fs.writeFile(path.join(directory, 'results.json'), JSON.stringify(result, null, 2));
  console.log(JSON.stringify(result));
  await execute('powershell.exe', ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', 'scripts/verify_desktop_window.ps1', '-WindowProcessId', String(child.pid), '-Action', 'Close'], { windowsHide: true });
} finally {
  if (browser) await browser.close().catch(() => {});
  if (child.exitCode === null) {
    await Promise.race([new Promise(resolve => child.once('exit', resolve)), new Promise(resolve => setTimeout(resolve, 3000))]);
    if (child.exitCode === null) child.kill();
  }
}
