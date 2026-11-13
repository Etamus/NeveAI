import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import { createServer } from 'vite';
import { chromium } from '../logs/ui-image-26/node_modules/playwright/index.mjs';
import { installMobileOfflineApi } from './fixtures/mobile-offline-api.mjs';

const hook = `import {chats as studyChats, showSidebar as studySidebar} from '$lib/stores'; onMount(()=>{window.__attachmentStudy={state:()=>({files,prompt,quality:stableDiffusionQuality}),destination:id=>chatId.set(id),reset:async()=>{files=[];prompt='';selectedModels=['local/mobile-fixture'];chatId.set('destination');studyChats.set([{id:'source',title:'Conversation source',updated_at:1700000000}]);studySidebar.set(innerWidth>=1024);await tick();},image:async()=>{files=[];stableDiffusionEnabled=true;stableDiffusionQuality='neve_image_2';await tick();}};return()=>delete window.__attachmentStudy;});`;
let server, browser;
const result = [];
try {
	server = await createServer({ plugins: [{ name: 'attachment-study', enforce: 'pre', async load(id) {
		if (id.endsWith('/src/lib/components/chat/MessageInput.svelte')) return (await fs.readFile(id, 'utf8')).replace('</script>', hook + '\n</script>');
	}}], server: { port: 5197, strictPort: true, watch: { ignored: ['**/logs/**', '**/scripts/**', '**/docs/**'] } } });
	await server.listen(); browser = await chromium.launch();
	for (const viewport of [{ width: 1440, height: 1000 }, { width: 800, height: 420 }, { width: 390, height: 640 }]) {
		const page = await browser.newPage({ viewport });
		await installMobileOfflineApi(page);
		const errors = []; page.on('pageerror', e => errors.push(e.message));
		await page.route('**/api/v1/chats/source', async route => {
			await new Promise(resolve => setTimeout(resolve, 80));
			await route.fulfill({ json: { id: 'source', title: 'Conversation source', updated_at: 1700000000 } });
		});
		await page.goto('http://localhost:5197', { waitUntil: 'networkidle', timeout: 90000 });
		await page.waitForFunction(() => window.__attachmentStudy);
		await page.evaluate(() => window.__attachmentStudy.reset());
		const drop = async id => page.evaluate(id => {
			const dt = new DataTransfer(); dt.setData('text/plain', JSON.stringify({ type: 'chat', id }));
			const input = document.querySelector('#chat-input');
			input.dispatchEvent(new DragEvent('dragover', { bubbles: true, cancelable: true, dataTransfer: dt }));
			input.dispatchEvent(new DragEvent('drop', { bubbles: true, cancelable: true, dataTransfer: dt }));
		}, id);
		if (viewport.width === 1440) {
			await page.locator('#sidebar-chat-group').filter({ has: page.locator('a[href="/c/source"]') }).dragTo(page.locator('#chat-input'));
		} else await drop('source');
		await page.waitForFunction(() => window.__attachmentStudy.state().files.length === 1);
		let state = await page.evaluate(() => window.__attachmentStudy.state());
		assert.equal(state.files[0].type, 'chat'); assert.equal(state.files[0].id, 'source');
		assert(!state.prompt.includes('"type":"chat"'));
		await drop('source'); await drop('destination'); await page.waitForTimeout(200);
		assert.equal((await page.evaluate(() => window.__attachmentStudy.state())).files.length, 1);
		await page.evaluate(() => window.__attachmentStudy.reset());
		await drop('source'); await drop('source'); await page.waitForTimeout(250);
		assert.equal((await page.evaluate(() => window.__attachmentStudy.state())).files.length, 1, 'Concurrent drops of the same conversation must not duplicate attachments');
		await page.evaluate(() => window.__attachmentStudy.reset());
		await drop('source');
		await page.evaluate(() => window.__attachmentStudy.destination('another-conversation'));
		await page.waitForTimeout(250);
		assert.equal((await page.evaluate(() => window.__attachmentStudy.state())).files.length, 0, 'A pending attachment must not enter a different conversation');
		await page.evaluate(() => window.__attachmentStudy.reset());
		await drop('source'); await page.waitForFunction(() => window.__attachmentStudy.state().files.length === 1);
		await page.locator('.composer-more-trigger').click();
		const menu = page.locator('.composer-integrations-menu'); await menu.waitFor();
		const metrics = await page.locator('.composer-integrations-scroll').evaluate(el => {
			const child = el.getBoundingClientRect(), parent = el.parentElement.getBoundingClientRect();
			return { top: child.top, bottom: child.bottom, parentTop: parent.top, parentBottom: parent.bottom, overflow: el.scrollHeight > el.clientHeight, scroll: el.scrollTop, height: el.clientHeight };
		});
		assert(metrics.top >= metrics.parentTop); assert(metrics.bottom <= metrics.parentBottom);
		if (metrics.overflow) {
			await page.locator('.composer-integrations-scroll').hover(); await page.mouse.wheel(0, 500); await page.waitForTimeout(200);
			assert(await page.locator('.composer-integrations-scroll').evaluate(el => el.scrollTop > 0));
		}
		await page.screenshot({ path: `logs/chat-attachment-menu-${viewport.width}.png` });
		await page.keyboard.press('Escape');
		await page.evaluate(() => window.__attachmentStudy.image());
		await page.screenshot({ path: `logs/image3-selector-${viewport.width}.png` });
		console.log('Image selector state', viewport, await page.evaluate(() => window.__attachmentStudy.state()), await page.locator('#message-input-container').innerText());
		await page.locator('#image-quality-dropdown-container > button').click();
		await page.getByRole('button', { name: /Neve Image 3/ }).click();
		assert.equal((await page.evaluate(() => window.__attachmentStudy.state())).quality, 'minimax_h3_image');
		assert.deepEqual(errors, []);
		result.push({ viewport, metrics, attached: state.files[0] }); await page.close();
	}
	await fs.writeFile('logs/chat-attachment-menu-results.json', JSON.stringify(result, null, 2));
	console.log('PASS chat drop, duplicate/self exclusion, menu clipping, Image 3 selection', result);
} finally { await browser?.close(); await server?.close(); }
