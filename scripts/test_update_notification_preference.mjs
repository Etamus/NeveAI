import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import { createServer } from 'vite';
import { chromium } from '../logs/ui-image-26/node_modules/playwright/index.mjs';
import { installMobileOfflineApi } from './fixtures/mobile-offline-api.mjs';

const origin = 'http://localhost:5188';
const output = 'logs/update-notification-preference';
const label = 'Notificar sobre novas atualizações';
const updateSelector = '[data-neve-toast-kind="update"]';
const hook = `onMount(() => {
 window.__updatePreferenceFixture = {
  async open(tab = 'updates') { showSettingsTab.set(tab); showSettings.set(true); await tick(); },
  async close() { showSettings.set(false); await tick(); },
  async patch(patch) { settings.update(value => ({...value, ...patch})); await tick(); },
  async poll() { await checkForVersionUpdates(); await tick(); },
  others() {
   neveDownloadToast.set({name:'Fixture download',progress:37,label:'Fixture download progress',cancelling:false,onCancel:()=>{}});
   window.dispatchEvent(new CustomEvent(LOCAL_MODEL_RUNTIME_EVENT,{detail:{phase:'start',action:'load',displayName:'Fixture runtime'}}));
   toast.error('Fixture unrelated error',{id:'fixture-unrelated-error',duration:Infinity});
  }
 };
 return () => { delete window.__updatePreferenceFixture; };
});`;

let server, browser;
const results = [];
try {
 await fs.mkdir(output, { recursive: true });
 server = await createServer({
  cacheDir: 'node_modules/.vite-update-notification-preference',
  plugins: [{
   name: 'update-notification-preference-fixture', enforce: 'pre',
   configResolved(config) { config.server.proxy = undefined; },
   async load(id) {
    if (!id.replaceAll('\\', '/').endsWith('/src/routes/(app)/+layout.svelte')) return;
    const source = await fs.readFile(id, 'utf8');
    assert(source.includes('const checkForVersionUpdates = async () => {'));
    assert(source.includes('showSettingsTab'));
    assert(source.includes('</script>'));
    return source.replace('</script>', `${hook}\n</script>`);
   }
  }],
  server: { port: 5188, strictPort: true, watch: { ignored: ['**/logs/**', '**/scripts/**', '**/docs/**'] } }
 });
 await server.listen();
 browser = await chromium.launch();
 for (const [name, viewport] of [
  ['desktop', { width: 1440, height: 1000 }],
  ['mobile', { width: 390, height: 844 }]
 ]) {
  const context = await browser.newContext({ viewport, serviceWorkers: 'block' });
  try {
   const page = await context.newPage();
   page.setDefaultTimeout(15000);
   const errors = [], forbidden = [], saves = [];
   let ui = { models: ['local/mobile-fixture'] };
   let target = 'project';
   let polls = 0, settingsReads = 0;
   const payload = () => ({
    current_tag: 'v3.0.20', latest_tag: ['project', 'both'].includes(target) ? 'v3.0.21' : 'v3.0.20',
    neve_update_available: ['project', 'both'].includes(target),
    llama_cpp: { current_tag: 'b11719', latest_tag: ['runtime', 'both'].includes(target) ? 'b11857' : 'b11719',
     update_available: ['runtime', 'both'].includes(target) }
   });
   page.on('pageerror', error => { errors.push(error.message); console.error(name, 'PAGEERROR', error.stack); });
   page.on('console', message => { if (message.type() === 'error') console.error(name, 'CONSOLE', message.text()); });
   await page.routeWebSocket('**/*', ws => ws.close());
   await page.route('**/*', route => {
    const url = new URL(route.request().url());
    if (url.origin === origin && !/^\/(api|llamacpp|ws|dbg|openai|audio|retrieval|health|static)(\/|$)/.test(url.pathname)) return route.continue();
    forbidden.push(`${route.request().method()} ${url.href}`);
    console.error(name, 'BLOCKED', route.request().method(), url.href);
    return route.fulfill({ status: 503, body: 'Blocked by update notification fixture' });
   });
   await installMobileOfflineApi(page);
   // Later routes take precedence over the offline API; no request reaches a real backend.
   await page.route('**/api/config', route => route.fulfill({ json: {
    name: 'Neve AI', version: '3.0.20', default_models: 'local/mobile-fixture',
    features: { auth: false, enable_websocket: false, enable_version_update_check: true },
    file: { max_file_count: 10 }
   } }));
   await page.route(/\/api\/(?:v1\/)?users\/user\/settings(?:\/update)?(?:\?.*)?$/, route => {
    if (route.request().method() === 'GET') settingsReads++;
    else if (route.request().method() === 'POST') {
     const body = route.request().postDataJSON();
     assert(body.ui && typeof body.ui.showUpdateToast === 'boolean');
     ui = structuredClone(body.ui);
     saves.push(structuredClone(body));
    } else throw new Error(`Unexpected settings method: ${route.request().method()}`);
    return route.fulfill({ json: { ui } });
   });
   await page.route('**/api/version/updates', route => {
    polls++;
    return route.fulfill({ json: payload() });
   });
   await page.route('**/api/updater/state',route=>route.fulfill({json:{status:'idle'}}));

   const update = page.locator(updateSelector);
   const toggle = page.getByRole('switch', { name: label, exact: true });
   const aboutUpdate = page.locator('#tab-updates button').filter({ hasText: /^Atualizar agora$/ });
   async function open(tab = 'updates') {
    await page.evaluate(tab => window.__updatePreferenceFixture.open(tab), tab);
    await page.locator(tab === 'about' ? '#tab-about' : '#update-notifications-label').waitFor({ state: 'visible' });
   }
   async function close() {
    await page.evaluate(() => window.__updatePreferenceFixture.close());
    await page.locator('[role="dialog"][aria-hidden="false"]').waitFor({ state: 'hidden' });
   }
   async function boot() {
    console.log(name, 'boot', { target, preference: ui.showUpdateToast });
    const reads = settingsReads, checks = polls;
    await page.goto(origin, { waitUntil: 'networkidle', timeout: 90000 });
    await page.waitForFunction(() => window.__updatePreferenceFixture, null, { timeout: 30000 });
    await page.waitForFunction(() => !!document.querySelector('.app'));
    assert(settingsReads > reads, 'Reload must fetch saved settings from the in-memory API');
    assert(polls > checks, 'Automatic update checks must run even when notifications are disabled');
   }
   async function checked(enabled) {
    await page.waitForFunction(({ label, enabled }) => {
     const text = [...document.querySelectorAll('[id]')].find(element => element.textContent.trim() === label && element.id === 'update-notifications-label');
     return text && document.querySelector(`[role="switch"][aria-labelledby="${text.id}"]`)?.getAttribute('aria-checked') === String(enabled);
    }, { label, enabled });
   }
   async function setToggle(enabled) {
    const count = saves.length;
    const saved = page.waitForResponse(response => response.url().includes('/users/user/settings') && response.request().method() === 'POST');
    await toggle.click();
    await checked(enabled);
    await saved;
    assert.equal(saves.length, count + 1, 'The real General switch must save exactly once');
    assert.equal(ui.showUpdateToast, enabled);
    assert.deepEqual(ui.models, ['local/mobile-fixture'], 'Unrelated settings must survive saves');
   }
   async function offset(expected) {
    await page.waitForFunction(expected => {
     const value = getComputedStyle(document.documentElement).getPropertyValue('--neve-update-toast-offset').trim();
     return expected ? parseFloat(value) > 0 : value === '0px';
    }, expected);
   }
   async function hidden() {
    await update.waitFor({ state: 'detached' });
    await offset(false);
   }
   async function visible(expected) {
    await update.waitFor({ state: 'visible' });
    await page.waitForFunction(({ selector, expected }) => document.querySelector(selector)?.textContent.includes(expected), { selector: updateSelector, expected });
    await offset(true);
   }
   async function screenshot(state) {
    await page.screenshot({ path: `${output}/${name}-${state}.png`, fullPage: true });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false, 'Horizontal overflow');
   }
   async function othersIntact() {
    for (const selector of ['[data-neve-toast-kind="download"]', '[data-neve-toast-kind="runtime"]']) {
     await page.locator(selector).waitFor({ state: 'visible' });
    }
    await page.getByText('Fixture unrelated error', { exact: true }).waitFor({ state: 'visible' });
   }

   await boot();
   await visible('NeveAI v3.0.21');
   await open();
   await checked(true);
   assert.equal(Object.hasOwn(ui, 'showUpdateToast'), false, 'Missing preference must not be written merely by opening General');
   const labelBox = await page.locator('#update-notifications-label').boundingBox();
   const temporaryBox = await page.locator('#tab-updates > section').boundingBox();
   const switchBox = await toggle.boundingBox();
   assert(labelBox && temporaryBox && switchBox);
   assert(labelBox.y >= temporaryBox.y + temporaryBox.height, 'Preference must sit below the update card');
   assert(labelBox.x + labelBox.width <= switchBox.x, 'Wrapped label must not overlap switch');
   assert(switchBox.x + switchBox.width <= viewport.width);
   await screenshot('general-default');
   await boot();
   await open();
   await checked(true);
   assert.equal(saves.length, 0, 'Default enabled must survive reload without saving');
   await close();

   // General itself hides update toasts behind its modal. Exercise the live settings
   // subscription separately while a toast is actually visible, without saving.
   await visible('NeveAI v3.0.21');
   await page.evaluate(() => window.__updatePreferenceFixture.others());
   await othersIntact();
   await page.evaluate(() => window.__updatePreferenceFixture.patch({ enableInterfaceNotifications: false }));
   await hidden();
   for (const kind of ['download', 'runtime']) await page.locator(`[data-neve-toast-kind="${kind}"]`).waitFor({ state: 'detached' });
   await page.getByText('Fixture unrelated error', { exact: true }).waitFor({ state: 'detached' });
   await screenshot('master-disabled');
   await page.evaluate(() => window.__updatePreferenceFixture.patch({ enableInterfaceNotifications: true }));
   await visible('NeveAI v3.0.21');
   await page.evaluate(() => window.__updatePreferenceFixture.others());
   await othersIntact();
   await page.evaluate(() => window.__updatePreferenceFixture.patch({ showUpdateToast: false }));
   await hidden();
   await othersIntact();
   await screenshot('live-suppressed');
   await page.evaluate(() => window.__updatePreferenceFixture.patch({ showUpdateToast: true }));
   await visible('NeveAI v3.0.21');
   await othersIntact();
   await update.getByRole('button', { name: /Close notification|Fechar notifica/ }).click();
   await hidden();
   await page.evaluate(() => window.__updatePreferenceFixture.patch({ enableMessageQueue: true }));
   await hidden();
   await othersIntact();

   await open();
   await checked(true);
   await setToggle(false);
   await screenshot('general-disabled');
   await boot();
   await hidden();
   await open();
   await checked(false);
   await close();
   for (const next of ['project', 'runtime', 'both']) {
    target = next;
    const before = polls;
    await page.evaluate(() => window.__updatePreferenceFixture.poll());
    assert(polls > before, `Polling stopped while disabled for ${next}`);
    await hidden();
    await open();
    await page.evaluate(() => window.dispatchEvent(new Event('focus')));
    await aboutUpdate.waitFor({ state: 'visible' });
    await page.waitForFunction(target => {
     const heading=document.querySelector('#tab-updates h3')?.textContent || '';
     const llama=document.querySelector('[data-update-component="llama"]');
     return heading.includes('v3.0.21')===(target!=='runtime') && Boolean(llama)===(target!=='project');
    }, next);
    assert(await aboutUpdate.isEnabled());
    await screenshot(`about-disabled-${next}`);
    await close();
    await hidden();
   }

   await open();
   await checked(false);
   await setToggle(true);
   const beforeRestore = polls;
   await close();
   await visible('NeveAI v3.0.21 e mais');
   assert.equal(polls, beforeRestore, 'Reenabling must restore the pending result without requiring another check');
   await page.evaluate(() => window.__updatePreferenceFixture.others());
   await othersIntact();
   await screenshot('reenabled-pending');
   await boot();
   await visible('NeveAI v3.0.21 e mais');
   await open();
   await checked(true);
   await screenshot('general-reloaded-enabled');
   await close();

   await open();
   await setToggle(false);
   target = 'current';
   await page.evaluate(() => window.__updatePreferenceFixture.poll());
   await setToggle(true);
   await close();
   await hidden();
   assert.deepEqual(errors, []);
   assert.deepEqual(forbidden, []);
   results.push({ name, viewport, settingsReads, polls, savedPreferences: saves.map(body => body.ui.showUpdateToast),
    defaultAndReload: true, disabledAndReload: true, projectAndRuntimeSuppressed: true,
    aboutIndependent: true, pendingRestored: true, resolvedNotRestored: true,
    liveDismissAndOffset: true, otherNotificationsUnaffected: true, backendRequests: 0, errors });
  } catch (error) {
   console.error(name, error);
   for (const page of context.pages()) {
    await page.screenshot({ path: `${output}/${name}-failure.png`, fullPage: true }).catch(() => {});
   }
   throw error;
  } finally {
   await context.close();
  }
 }
 await fs.writeFile(`${output}/results.json`, JSON.stringify(results, null, 2));
 console.log('PASS update notification preference: ' + JSON.stringify(results));
} finally {
 try { await browser?.close(); } finally { await server?.close(); }
}
