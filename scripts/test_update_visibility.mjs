import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import { chromium } from '../logs/ui-image-26/node_modules/playwright/index.mjs';

const browser = await chromium.launch();
const results = [];
try {
  for (const [name, project, runtime] of [['project', true, false], ['runtime', false, true], ['both', true, true], ['current', false, false]]) {
    const page = await browser.newPage();
    const errors = [];
    let unavailable = false;
    let queries = 0;
    page.on('pageerror', error => errors.push(error.message));
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
      assert.equal(text.includes('llama.cpp b11857'), runtime);
    } else assert.equal(await notifications.count(), 0);
    await page.getByRole('button', { name: /Usu/ }).click();
    await page.getByRole('menuitem').filter({ hasText: /Configura/ }).click();
    await page.getByRole('tab', { name: 'Sobre', exact: true }).click();
    const update = page.locator('#tab-about button').filter({ hasText: /^Atualizar$/ });
    await page.waitForTimeout(200);
    assert.equal(await update.count(), project || runtime ? 1 : 0);
    if (project || runtime) {
      unavailable = true;
      const before = queries;
      await page.evaluate(() => window.dispatchEvent(new Event('focus')));
      await page.waitForResponse(response => response.url().includes('/api/version/updates') && response.status() === 503);
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
