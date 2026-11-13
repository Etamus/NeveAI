import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import { chromium } from '../logs/ui-image-26/node_modules/playwright/index.mjs';

const browser = await chromium.launch();
const results = [];
try {
  for (const [name, project, runtime, receive] of [['project', true, false,true], ['runtime', false, true,true], ['both', true, true,true], ['current', false, false,true],['runtime-off',false,true,false]]) {
    const page = await browser.newPage();
    await page.addInitScript(()=>localStorage.setItem('neveai.language','pt-BR'));
    const errors = [];
    let unavailable = false;
    let queries = 0;
    page.on('pageerror', error => errors.push(error.message));
    // Test visibility independently of the user's saved notification preference.
    await page.route('**/api/v1/users/user/settings', async route => {
      const response = await route.fetch();
      const settings = await response.json();
      await route.fulfill({ response, json: { ...settings, ui: { ...settings.ui, showUpdateToast: true,receiveLlamaUpdates:receive } } });
    });
    await page.route('**/api/version/updates', route => {
      queries++;
      if (unavailable) return route.fulfill({ status: 503, json: { detail: 'Temporary test outage' } });
      return route.fulfill({ json: {
        current_tag: 'v3.0.20', latest_tag: project ? 'v3.0.21' : 'v3.0.20', neve_update_available: project,
        llama_cpp: { current_tag: 'b11719', latest_tag: runtime ? 'b11857' : 'b11719', update_available: runtime }
      } });
    });
    await page.goto('http://localhost:8080', { waitUntil: 'networkidle' });
    const notifications = page.locator('[data-neve-toast]').filter({ hasText: /Atualiza|Update/ });
    if (project || runtime) {
      await notifications.waitFor();
      const text = await notifications.innerText();
      assert.equal(text.includes('NeveAI v3.0.21'), project);
      assert.equal(text.includes('llama.cpp b11857'), runtime && !project);
      assert.equal(text.includes('e mais'), runtime && project);
    } else assert.equal(await notifications.count(), 0);
    await page.getByRole('button', { name: /Usu/ }).click();
    await page.getByRole('menuitem').filter({ hasText: /Configura/ }).click();
    await page.route('**/api/updater/state',route=>route.fulfill({json:{status:'idle'}}));
    await page.getByRole('tab', { name: 'Atualizações', exact: true }).click();
    const update = page.locator('#tab-updates button').filter({ hasText: /^Atualizar agora$/ });
    await page.waitForTimeout(200);
    assert.equal(await update.count(), project || (runtime && receive) ? 1 : 0);
    if(project || (runtime && receive))assert(await update.isEnabled());
    assert.equal(await page.locator('[data-update-component="neve"]').count(),0);
    assert.equal(await page.locator('[data-update-component="llama"]').count(),runtime&&receive?1:0);
    assert.equal(await page.locator('#tab-updates h3').innerText(),project?'Atualização disponível (v3.0.21)':runtime&&receive?'Atualização disponível':'Você está na versão mais recente');
    if (project || (runtime&&receive)) {
      unavailable = true;
      const before = queries;
      await page.getByRole('tab',{name:'Geral',exact:true}).click();
      const failed = page.waitForResponse(response => response.url().includes('/api/version/updates') && response.status() === 503);
      await page.getByRole('tab',{name:'Atualizações',exact:true}).click();
      await failed;
      assert(queries > before);
      assert.equal(await update.count(), 1, 'A temporary failure must not erase a confirmed update');
    }
    await page.screenshot({ path: `logs/window-updates-${name}.png` });
    assert.deepEqual(errors, []);
    results.push({ name, button: await update.count(), errors });
    await page.close();
  }
  await fs.writeFile('logs/window-update-visibility.json', JSON.stringify(results, null, 2));
  console.log(JSON.stringify(results));
} finally { await browser.close(); }
