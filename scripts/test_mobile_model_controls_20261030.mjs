import fs from 'node:fs/promises';
import { constants } from 'node:fs';
import assert from 'node:assert/strict';
import { createServer } from 'vite';
import { chromium } from '../logs/ui-image-26/node_modules/playwright/index.mjs';
import { installMobileOfflineApi } from './fixtures/mobile-offline-api.mjs';
import sharp from 'sharp';

const baseline = process.argv.includes('--baseline');
const output = 'logs/mobile-model-controls-20261030';
const files = [
 'src/lib/components/chat/MessageInput/ReasoningDropdown.svelte',
 'src/lib/components/chat/ModelSelector/Selector.svelte',
 'src/lib/components/chat/UnifiedModels.svelte',
 'src/lib/components/chat/DownloadNeveModelsModal.svelte'
];
const fixture = new URL('../src/routes/__mobile_model_controls/', import.meta.url);
const models = Array.from({length: 3}, (_, i) => ({id: `local/fixture-${i}`, filename: `Example model ${i} with a longer name.gguf`, file_size: 123456, file_size_human: '4.0 GB', is_loaded: i === 0, n_ctx: 8192, cache_type: 'q8_0', context_shift: 'off', token_prediction: 'off', speculative_decoding: 'off'}));
const catalog = [
 ['neve-echo-s', 'Neve Echo S'], ['neve-echo', 'Neve Echo'], ['neve-sense', 'Neve Sense'],
 ['neve-strata-s', 'Neve Strata S'], ['neve-strata-x', 'Neve Strata'], ['neve-muse', 'Neve Muse'], ['neve-cascade-x', 'Neve Cascade']
].map(([id, name]) => ({id, name, installed: false, repo: `Fixture/${id}`, size_label: '6 GB', description: 'A detailed description for the model catalog and download options.'}));
const hook = `onMount(()=>{ window.__modelControls=()=>{const model={id:'local/mobile-fixture',name:'Example model',owned_by:'llamacpp',info:{meta:{}},llamacpp:{reasoning_control:'toggle'}};models.set([model]);selectedModels=[model.id];};return()=>delete window.__modelControls;});`;
let browser, server;
const results = [];
await fs.mkdir(output, {recursive: true});
if (baseline && !process.argv.includes('--keep-sources')) for (let i = 0; i < files.length; i++) await fs.copyFile(files[i], `${output}/source-${i}.svelte`);
await fs.mkdir(fixture, {recursive: true});
await fs.copyFile(new URL('./fixtures/mobile-refinements.svelte', import.meta.url), new URL('+page.svelte', fixture), constants.COPYFILE_EXCL);
try {
 server = await createServer({plugins: [{name: 'mobile-model-controls-test', enforce: 'pre', async load(id) {
  const index = files.findIndex(file => id.replaceAll('\\', '/').endsWith('/' + file));
  if (baseline && index >= 0) return fs.readFile(`${output}/source-${index}.svelte`, 'utf8');
  if (id.endsWith('/src/lib/components/chat/MessageInput.svelte')) return (await fs.readFile(id, 'utf8')).replace('</script>', hook + '\n</script>');
 }}], server: {port: 5188, strictPort: true, watch: {ignored: ['**/logs/**', '**/scripts/**', '**/docs/**']}}});
 await server.listen();
 browser = await chromium.launch();
 const widths = (process.env.CONTROL_WIDTHS ?? '320,390,430,640,767,768,1440').split(',').map(Number);
 for (const width of widths) for (const dark of [false, true]) {
  const mobile = width < 768;
  const page = await browser.newPage({viewport: {width, height: 1000}, hasTouch: mobile});
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.addInitScript(() => localStorage.setItem('neveai.reasoningLevel', '1'));
  await installMobileOfflineApi(page);
  await page.route('**/api/v1/models/model/profile/image?**', async route => route.fulfill({contentType: 'image/png', body: await fs.readFile('static/static/logosense.png')}));
  await page.route('**/llamacpp/models', route => route.fulfill({json: {models}}));
  await page.route('**/llamacpp/models/loaded', route => route.fulfill({json: {models: [models[0]]}}));
  await page.route('**/llamacpp/catalog', route => route.fulfill({json: {models: catalog}}));
  await page.goto('http://localhost:5188', {waitUntil: 'networkidle', timeout: 90000});
  await page.waitForFunction(() => window.__modelControls);
  await page.evaluate(async dark => {document.documentElement.classList.toggle('dark', dark); window.__modelControls(); await document.fonts.ready;}, dark);
  await page.waitForTimeout(250);
  const capture = async (locator, kind) => {
   const key = `${kind}-${width}-${dark ? 'dark' : 'light'}`;
   const buffer = await locator.screenshot({animations: 'disabled'});
   await fs.writeFile(`${output}/${baseline ? 'before' : 'after'}-${key}.png`, buffer);
   if (!baseline && !mobile) {
    const previous = await fs.readFile(`${output}/before-${key}.png`);
    const a = await sharp(previous).raw().toBuffer({resolveWithObject: true}), b = await sharp(buffer).raw().toBuffer({resolveWithObject: true});
    assert.deepEqual(a.info, b.info, 'Desktop dimensions changed: ' + key);
    // Native circular borders can vary by two color levels; geometry is checked separately.
    let changed = 0;
    for (let i = 0; i < a.data.length; i += a.info.channels) {
     let delta = 0;
     for (let channel = 0; channel < a.info.channels; channel++) delta = Math.max(delta, Math.abs(a.data[i + channel] - b.data[i + channel]));
     assert(delta <= 2, 'Desktop pixels changed: ' + key);
     if (delta) changed++;
    }
    assert(changed <= 100, 'Desktop rendering changed: ' + key);
   }
  };
  const metrics = {width, dark};
  const selector = page.locator('[id^="model-selector-"][id$="-button"]').first();
  metrics.chevron = await selector.locator('svg').last().evaluate(e => e.getBoundingClientRect().width);
  if (!baseline) {
   const before = JSON.parse(await fs.readFile(`${output}/before-results.json`, 'utf8'));
   assert.equal(metrics.chevron, before.find(item => item.width >= 768).chevron);
  }
  await capture(selector, 'selector');
  for (const expanded of [false, true]) {
   await page.locator('#chat-input').fill(expanded ? 'A longer paragraph with words and spaces. '.repeat(20) : 'Hello');
   await page.waitForTimeout(200);
   if (mobile) {
    metrics[expanded ? 'expanded' : 'compact'] = await page.evaluate(() => {
     const gauge = document.querySelector('.mobile-reasoning-toggle'), send = document.querySelector('#send-message-button');
     const g = gauge.getBoundingClientRect(), s = send.getBoundingClientRect(), icon = gauge.querySelector('svg').getBoundingClientRect();
     return {gauge: [g.width, g.height], send: [s.width, s.height], radius: getComputedStyle(gauge).borderRadius, icon: icon.width};
    });
    const value = metrics[expanded ? 'expanded' : 'compact'];
    assert.deepEqual(value.gauge, value.send);
    assert.equal(value.radius, '50%');
    if (!baseline) assert.equal(value.icon, 26);
   }
   await capture(page.locator('#message-input-container'), expanded ? 'expanded' : 'compact');
  }
  if (mobile) {
   const gauge = page.locator('.mobile-reasoning-toggle');
   await gauge.click(); assert.equal(await gauge.getAttribute('aria-pressed'), 'false');
   await gauge.hover(); await capture(gauge, 'gauge-hover');
   await gauge.click(); assert.equal(await gauge.getAttribute('aria-pressed'), 'true');
  }
  await page.goto('http://localhost:5188/__mobile_model_controls', {waitUntil: 'networkidle', timeout: 90000});
  await page.waitForFunction(() => window.__mobileRefinements);
  for (const kind of ['unified', 'download']) {
   await page.evaluate(({kind, dark}) => window.__mobileRefinements.open(kind, dark), {kind, dark});
   await page.waitForTimeout(400);
   const modal = page.locator('.modal').last();
   await modal.waitFor({state: 'visible'});
   if (kind === 'unified') {
    metrics.avatarGaps = await page.locator('.unified-model-card').evaluateAll(nodes => nodes.map(node => node.children[1].getBoundingClientRect().left - node.querySelector('.model-avatar').getBoundingClientRect().right));
    if (!baseline && mobile) assert(metrics.avatarGaps.every(gap => gap >= 14));
   } else {
    await page.locator('.catalog-model-card').first().waitFor();
    if (!baseline) {
     metrics.downloadButtonMargin = await page.locator('.catalog-download-button').evaluate(node => getComputedStyle(node).marginRight);
     assert.equal(metrics.downloadButtonMargin, mobile ? '6px' : '0px');
    }
    metrics.catalog = await page.locator('.catalog-model-row').evaluateAll(nodes => nodes.map(node => {
     const heading = node.children[2].children[0], name = heading.children[0].getBoundingClientRect(), badges = heading.children[1].getBoundingClientRect();
     return {name: {x: name.x, y: name.y, width: name.width, height: name.height}, badges: {x: badges.x, y: badges.y, width: badges.width, height: badges.height}, clipped: heading.children[1].scrollWidth > heading.children[1].clientWidth};
    }));
    if (!baseline) for (const item of metrics.catalog) {
     assert(item.badges.x >= item.name.x + item.name.width - 0.5, JSON.stringify(item));
     assert(Math.abs(item.name.y + item.name.height / 2 - item.badges.y - item.badges.height / 2) < 1, JSON.stringify(item));
     assert(!item.clipped, 'Badges clipped');
    }
   }
   if (!baseline && !mobile) {
    const previous = JSON.parse(await fs.readFile(`${output}/before-results.json`, 'utf8')).find(item => item.width === width && item.dark === dark);
    assert.deepEqual(kind === 'unified' ? metrics.avatarGaps : metrics.catalog, kind === 'unified' ? previous.avatarGaps : previous.catalog);
   }
   assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
   await capture(modal, kind);
   await page.evaluate(() => window.__mobileRefinements.open('', false));
   await page.waitForTimeout(150);
  }
  assert.deepEqual(errors, []);
  results.push(metrics);
  await page.close();
  console.log('PASS ' + width + ' ' + (dark ? 'dark' : 'light'));
 }
 await fs.writeFile(`${output}/${baseline ? 'before' : 'after'}-results.json`, JSON.stringify(results, null, 2));
} catch (error) {
 for (const page of browser?.contexts().flatMap(context => context.pages()) ?? []) await page.screenshot({path: `${output}/failure.png`}).catch(() => {});
 throw error;
} finally {
 await browser?.close(); await server?.close();
 await fs.unlink(new URL('+page.svelte', fixture)); await fs.rmdir(fixture);
}
