import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import { constants } from 'node:fs';
import { createServer } from 'vite';
import { chromium } from '../logs/ui-image-26/node_modules/playwright/index.mjs';
import { installMobileOfflineApi } from './fixtures/mobile-offline-api.mjs';
const route = new URL('../src/routes/__project_delete_study/', import.meta.url);
await fs.mkdir(route, { recursive: true });
await fs.copyFile(new URL('./fixtures/project-delete-study.svelte', import.meta.url), new URL('+page.svelte', route), constants.COPYFILE_EXCL);
let server, browser;
try {
	server = await createServer({ plugins: [{ name: 'project-delete-study', enforce: 'pre', async load(id) {
		if (id.endsWith('/src/lib/components/layout/Sidebar/RecursiveFolder.svelte')) return (await fs.readFile(id, 'utf8')).replace('</script>', `onMount(()=>{window.__openProjectDelete=()=>showDeleteConfirm=true;return()=>delete window.__openProjectDelete;});\n</script>`);
	}}], server: { port: 5198, strictPort: true, watch: { ignored: ['**/logs/**'] } } });
	await server.listen(); browser = await chromium.launch();
	for (const width of [1440, 390]) for (const mode of ['dark', 'light']) {
		const page = await browser.newPage({ viewport: { width, height: 844 } }); await installMobileOfflineApi(page);
		await page.goto('http://localhost:5198/__project_delete_study', { waitUntil: 'networkidle', timeout: 90000 });
		await page.waitForFunction(() => window.__openProjectDelete);
		await page.evaluate(mode => { document.documentElement.classList.toggle('dark', mode === 'dark'); window.__openProjectDelete(); }, mode);
		const label = page.locator('label').filter({ has: page.locator('input[type="checkbox"]') }); await label.waitFor();
		const metrics = await label.evaluate(el => {
			const row = el.parentElement, rect = el.getBoundingClientRect();
			const buttons = [...row.querySelectorAll('button')].map(b => b.getBoundingClientRect());
			return { rowButtons: buttons.length, center: rect.y + rect.height / 2, buttonCenter: buttons[0].y + buttons[0].height / 2, labelRight: rect.right, labelBottom: rect.bottom, buttonTop: buttons[0].top, buttonHeight: buttons[0].height, buttonLeft: buttons[0].x, overflow: row.scrollWidth > row.clientWidth };
		});
		assert.equal(metrics.rowButtons, 2); assert(!metrics.overflow); assert(metrics.buttonHeight < 40);
		const spacing=await label.evaluate(el=>parseFloat(getComputedStyle(el).columnGap)/parseFloat(getComputedStyle(document.documentElement).fontSize));
		assert.equal(spacing,0.625);
		if (width > 480) { assert(Math.abs(metrics.center - metrics.buttonCenter) < 1); assert(metrics.labelRight <= metrics.buttonLeft); }
		else assert(metrics.labelBottom <= metrics.buttonTop);
		assert(await label.evaluate(el => [...el.parentElement.querySelectorAll('button')].every(button => getComputedStyle(button).whiteSpace === 'nowrap')));
		const checkbox = label.locator('input'); const checked = await checkbox.isChecked(); await label.click(); assert.equal(await checkbox.isChecked(), !checked);
		await page.screenshot({ path: `logs/project-delete-${width}-${mode}.png` });
		await page.keyboard.press('Escape'); await label.waitFor({ state: 'hidden' }); await page.close();
	}
	console.log('PASS: actual project confirmation layout, label toggle and cancel in both themes/viewport sizes; no deletions executed');
} finally { await browser?.close(); await server?.close(); await fs.rm(route, { recursive: true, force: true }); }
