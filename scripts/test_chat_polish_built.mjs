import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import { chromium } from '../logs/ui-image-26/node_modules/playwright/index.mjs';
import { installMobileOfflineApi } from './fixtures/mobile-offline-api.mjs';

const base = process.env.NEVE_TEST_ORIGIN ?? 'http://localhost:8080';
const png = await fs.readFile('backend/data/cache/mesh_generation/smoke/reference.png');
const model = 'local/mobile-fixture';
const url = 'https://example.test/article';
const history = { currentId: 'reply', messages: {
	request: { id: 'request', role: 'user', content: 'Find sources', parentId: null, childrenIds: ['reply'], timestamp: 1700000000 },
	reply: { id: 'reply', role: 'assistant', content: 'Sources for this query.\n\n'.repeat(80) + '\n\n```unknown-grammar\nclass Example {\n  run() { return "<demo>"; }\n}\n```\n\nTwo sources [1][2].', done: true, parentId: 'request',
		childrenIds: [], model, timestamp: 1700000001,
		statusHistory: [
			{ action: 'web_search', description: 'Searching the web', done: false },
			{ action: 'web_search', description: 'Searched 10 sites', done: true, deep_search: true,
				items: Array.from({ length: 10 }, (_, i) => ({ title: 'Example ' + i, link: url + '/' + i })) }
		],
		sources: [url, 'https://second.example.test/article'].map(url => ({ source: { id: url, url, name: url }, document: ['Example quoted source.'], metadata: [{ source: url }] }))
	}
} };
const browser = await chromium.launch();
try {
	for (const width of [1440, 390]) {
		const page = await browser.newPage({ viewport: { width, height: 900 } });
		page.setDefaultTimeout(12000);
		const errors = [];
		page.on('pageerror', error => errors.push(error.message));
		await installMobileOfflineApi(page);
		let testSocket;
		await page.routeWebSocket('**/ws/socket.io/**', ws => {
			testSocket = ws;
			ws.send('0' + JSON.stringify({ sid: 'test-engine', upgrades: [], pingInterval: 60000, pingTimeout: 20000, maxPayload: 1000000 }));
			ws.onMessage(data => { if (String(data).startsWith('40')) ws.send('40{"sid":"test-session"}'); });
		});
		await page.route('https://www.google.com/s2/favicons?*', r => r.fulfill({ status: 200, body: png, contentType: 'image/png' }));
		await page.addInitScript(() => localStorage.setItem('neveai.integration-suggestions.v1:mobile-fixture-user', '["model3d_generation"]'));
		await page.route('**/api/config', r => r.fulfill({ json: {
			name: 'Neve AI', version: '3.0.20', default_models: model,
			features: { auth: false, enable_websocket: true, enable_stable_diffusion: true, enable_model3d_generation: true },
			file: { max_file_count: 10 }
		} }));
		await page.route('**/api/v1/chats/web-fixture', r => r.fulfill({ json: {
			id: 'web-fixture', title: 'Test web', user_id: 'mobile-fixture-user', chat: { history, models: [model], title: 'Test web' }
		} }));
		await page.route('**/api/tasks/chat/**', r => r.fulfill({ json: { task_ids: [] } }));
		let uploads = 0;
		await page.route('**/api/v1/files/?*', async r => {
			if (r.request().method() !== 'POST') return r.fallback();
			const form = await new Response(r.request().postDataBuffer(), { headers: { 'content-type': r.request().headers()['content-type'] } }).formData();
			const file = form.get('file');
			const id = 'attachment-' + ++uploads;
			await r.fulfill({ json: { id, filename: file.name, meta: { content_type: file.type, size: file.size }, data: { content: 'Test document.' } } });
		});
		await page.route('**/files/attachment-*/process/status?*', r => r.fulfill({ body: 'data: {"status":true}\n\n', contentType: 'text/event-stream' }));
		await page.route('**/files/attachment-*/content', r => r.fulfill({ body: png, contentType: 'image/png' }));
		await page.route('**/test-image.png', r => r.fulfill({ body: png, contentType: 'image/png' }));
		const paste = async () => page.evaluate(async () => {
			const data = new DataTransfer();
			data.items.add(new File([await (await fetch('/test-image.png')).blob()], 'pasted.png', { type: 'image/png' }));
			return document.body.dispatchEvent(new ClipboardEvent('paste', { clipboardData: data, bubbles: true, cancelable: true }));
		});
		await page.goto(base, { waitUntil: 'networkidle' });
		let catalogReads = 0;
		const catalogRequest = r => r.method() === 'GET' && new URL(r.url()).pathname === '/api/models';
		page.on('request', r => { if (catalogRequest(r)) catalogReads++; });
		const selector = page.locator('button[id^="model-selector-"]').first();
		for (let i=0; i<3; i++) {
			await selector.hover();
			await page.mouse.move(width - 5, 300);
		}
		assert.equal(catalogReads, 0, 'passing over the selector must not refresh the catalog');
		const catalogRead = page.waitForRequest(catalogRequest);
		await selector.click();
		await catalogRead;
		const modelSearch = page.locator('#model-search-input');
		for (const [query, present] of [['mobile test', true], ['no matching model zz', false], ['local/mobile', true]]) {
			await modelSearch.fill(query);
			await page.locator('[data-model-selector-row]').filter({hasText:/Mobile test model/i}).first().waitFor({state:present ? 'visible' : 'detached'});
		}
		assert.equal(catalogReads, 1, 'typing filters locally');
		await page.keyboard.press('Escape');
		await modelSearch.waitFor({state:'hidden'});
		await page.locator('[data-suggest-integration="model3d_generation"]').click();
		const slot = page.locator('[data-image-slot="base"]');
		const composer = page.locator('#message-input-container');
		assert.equal(await composer.locator('#send-message-button').evaluate(el=>el.parentElement._tippy.props.delay[0]),0,'primary composer actions have no hover wait');
		assert.match(await slot.innerText(), /Adicionar|Add/);
		assert(!(await page.locator('#chat-input').isVisible()), 'Model-only input hides the text editor');
		assert(await page.locator('#send-message-button').isDisabled());
		await page.evaluate(() => document.activeElement?.blur());
		await composer.hover();
		assert.equal(await paste(), false);
		await slot.locator('img').waitFor();
		await page.waitForFunction(() => !document.querySelector('#send-message-button')?.disabled);
		assert.equal(uploads, 1);
		const [chooser] = await Promise.all([page.waitForEvent('filechooser'), slot.click()]);
		await chooser.setFiles({ name: 'replacement.png', mimeType: 'image/png', buffer: png });
		await slot.locator('img:not(.invisible)').waitFor();
		assert.equal(uploads, 2);
		assert.equal(await slot.locator('img').count(), 1);
		await page.route('**/api/v1/chats/new', r => r.fulfill({ json: { id: 'delayed-task' } }));
		let release;
		const barrier = new Promise(resolve => { release = resolve; });
		await page.route('**/api/chat/completions', async r => {
			await barrier;
			await r.fulfill({ json: { task_id: 'late-task-id' } });
		});
		await page.route('**/api/tasks/stop/late-task-id', r => r.fulfill({ json: { status: true } }));
		const submitted = page.waitForRequest(r => r.url().endsWith('/api/chat/completions'), { timeout: 15000 });
		await composer.focus();
		assert.equal(await composer.evaluate(el => getComputedStyle(el).outlineStyle), 'none');
		await page.keyboard.press('Enter');
		assert.equal((await submitted).postDataJSON().features.model3d_generation, true);
		await composer.hover();
		assert.equal(await paste(), false, '3D reference paste is accepted during generation');
		await slot.locator('img:not(.invisible)').waitFor();
		assert.equal(uploads, 3);
		await page.locator('#send-message-button[type="button"]').click();
		const lateStop = page.waitForRequest(r => r.url().endsWith('/stop/late-task-id'));
		release();
		await lateStop;

		if (width >= 768) {
			for (const mode of ['restore', 'outpaint', 'inpaint', 'outfit', 'body']) {
				await page.goto(base, { waitUntil: 'networkidle' });
				await page.locator('#input-menu-button').click();
				await page.getByRole('button', { name: /Criar imagem|Create image/ }).click();
				await page.locator('#image-mode-dropdown-container > button').click();
				await page.locator('[data-image-mode="' + mode + '"]').click();
				const before = uploads;
				await page.evaluate(() => document.activeElement?.blur());
				await composer.hover();
				assert.equal(await paste(), false, mode);
				await slot.locator('img').waitFor();
				assert.equal(uploads, before + 1, mode);
				if (mode === 'outpaint') {
					await composer.locator('[data-image-mode-edit]').click();
					await page.locator('[data-outpaint-aspect] > button').click();
					await page.locator('[data-outpaint-aspect] [role=menuitemradio]').filter({hasText:'16:9'}).click();
					await page.getByRole('button',{name:/^Aplicar$|^Apply$/}).click();
				}
				if (mode === 'restore' || mode === 'outpaint') {
					await page.waitForFunction(() => !document.querySelector('#send-message-button')?.disabled);
					const sent = page.waitForRequest(r => r.url().endsWith('/api/chat/completions'));
					await page.keyboard.press('Enter');
					assert((await sent).postDataJSON().features);
				}
			}
		}
		await page.goto(base, { waitUntil: 'networkidle' });
		await page.locator('input[type="file"][multiple]').first().setInputFiles({
			name: 'notes.txt', mimeType: 'text/plain', buffer: Buffer.from('Test document.')
		});
		const tile = composer.getByRole('button', { name: 'notes.txt', exact: true });
		assert.equal(await tile.getAttribute('title'), null);
		await tile.locator('[data-title-self]').hover();
		const nameTip = page.locator('[data-tippy-root] .tippy-content').filter({ hasText: 'notes.txt' });
		assert.equal(await nameTip.isVisible(), false, 'pointer entry alone does not immediately show the filename');
		await tile.hover({ position: { x: 5, y: 6 } });
		await page.waitForTimeout(240);
		assert.equal(await nameTip.isVisible(), false, 'leaving cancels a pending tooltip');
		await tile.locator('[data-title-self]').hover();
		await nameTip.waitFor();
		await tile.hover({ position: { x: 5, y: 6 } });
		await nameTip.waitFor({ state: 'hidden' });
		await tile.click();
		const attachmentPreview = page.getByRole('dialog');
		const retrieval = attachmentPreview.locator('[data-file-retrieval]');
		await retrieval.getByRole('switch').waitFor();
		if (width >= 768) {
			const [toggle, dismiss] = await Promise.all([retrieval.boundingBox(), attachmentPreview.locator('[data-mobile-modal-close]').boundingBox()]);
			assert(toggle.x + toggle.width <= dismiss.x && Math.abs(toggle.y + toggle.height / 2 - dismiss.y - dismiss.height / 2) < 1);
		}
		const switchControl = retrieval.getByRole('switch');
		const state = await switchControl.getAttribute('aria-checked');
		await switchControl.click();
		assert.notEqual(await switchControl.getAttribute('aria-checked'), state);
		await page.keyboard.press('Escape');
		await attachmentPreview.waitFor({ state: 'hidden' });
		await page.goto(base + '/c/web-fixture', { waitUntil: 'networkidle' });
		const web = page.locator('.web-search-block');
		const sites = web.getByRole('button', { name: 'Searched 10 sites' });
		await sites.click();
		assert.equal(await web.locator('a').count(), 8);
		assert.equal(await web.evaluate(node => node.getAnimations({ subtree: true }).filter(a => a.effect?.target?.matches('a, a *')).length), 0);
		await web.getByRole('button', { name: '+2 mais' }).click();
		assert.equal(await web.locator('a').count(), 10);
		await sites.click();
		assert.equal(await web.locator('a').count(), 0);
		const origins = page.getByRole('button', { name: /Toggle 2 sources|Alternar 2 origens/i });
		const source = page.locator('#source-reply-1');
		const unknown = page.locator('code.language-unknown-grammar');
		assert((await unknown.innerText()).includes('<demo>'));
		await unknown.locator('[class^="hljs-"]').first().waitFor();
		assert.equal(await unknown.locator('demo').count(), 0);
		const badge = page.getByRole('button', { name: /\+1 more sources/ });
		// Finish the upward scroll used for the tool call before pointing at the citation at the end.
		await page.locator('#messages-container').hover();
		await page.mouse.wheel(0, 16000);
		await page.waitForFunction(() => {
			const trigger = document.querySelector('button[aria-label$="more sources"]');
			if (!trigger) return false;
			const r = trigger.getBoundingClientRect();
			return trigger.contains(document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2));
		});
		await badge.hover();
		const grouped = page.locator('[data-grouped-source-card]');
		await page.waitForTimeout(250);
		assert.equal(await grouped.count(), 0, 'hover alone must not open grouped sources');
		await badge.click();
		await grouped.waitFor({timeout:1200});
		const links = grouped.getByRole('button');
		assert.equal(await links.count(), 2);
		assert.equal(await links.first().evaluate(n => getComputedStyle(n).backgroundColor), 'rgba(0, 0, 0, 0)');
		await links.last().hover();
		await page.mouse.move(0, 0);
		assert(await grouped.isVisible());
		await badge.click();
		await grouped.waitFor({state:'hidden', timeout:500});
		for (const opening of [true, false]) {
			const samples = await origins.evaluate(async button => {
				button.click();
				const samples = [];
				const start = performance.now();
				do {
					await new Promise(requestAnimationFrame);
					const block = document.querySelector('[data-source-disclosure]');
					samples.push([block?.getBoundingClientRect().height ?? 0, block?.querySelector('button')?.getBoundingClientRect().height ?? 0, Number(getComputedStyle(block.querySelector('.source-links')).opacity)]);
				} while (performance.now() - start < 350);
				return samples;
			});
			assert(samples.filter(([, , opacity]) => opacity > 0 && opacity < 1).length >= 2, 'links themselves visibly fade in and out');
			const peak = Math.max(...samples.map(([h]) => h));
			assert(samples.some(([h]) => h > 0 && h < peak - 0.25), 'intermediate accordion height');
			assert(opening ? samples.at(-1)[0] > samples[0][0] : samples.at(-1)[0] === 0, 'accordion ends in requested state');
			assert.equal(new Set(samples.map(([,h]) => h).filter(Boolean)).size, 1, 'source rows retain full height');
		}
		assert(await source.evaluate(n => !!n.closest('[inert]')), 'closed source list is inert');
		await origins.click();
		assert.equal(await page.locator('#source-reply-1').evaluate(n => n.getAnimations({subtree:true}).length), 0);
		await page.locator('#source-reply-1').click();
		const modal = page.getByRole('dialog');
		const link = modal.locator('.file-preview-header a');
		assert.equal(await link.getAttribute('href'), url);
		assert.equal((await link.innerText()).trim(), '');
		assert.equal(await link.locator('svg').count(), 1);
		const longest = await modal.evaluate(node => Math.max(0, ...node.getAnimations({ subtree: true }).map(a => a.effect?.getTiming().duration || 0)));
		assert.equal(longest, 0);
		await page.keyboard.press('Escape');
		await modal.waitFor({ state: 'hidden' });
		await page.locator('#input-menu-button').click();
		await page.getByRole('button', { name: /Criar modelo|Create model/i }).click();
		await slot.waitFor();
		const scroll = page.locator('#messages-container');
		await scroll.evaluate(el => { el.scrollTop = el.scrollHeight; });
		await page.waitForTimeout(450);
		const geometry = () => scroll.evaluate(el => [el.scrollTop, el.scrollHeight, el.clientHeight, document.querySelector('#message-input-container').getBoundingClientRect().top]);
		const beforePaste = await geometry();
		assert(beforePaste[1] > beforePaste[2]);
		await composer.hover();
		await paste();
		await slot.locator('img').waitFor();
		await page.waitForTimeout(400);
		const afterPaste = await geometry();
		console.log('Paste geometry', width, beforePaste, afterPaste);
		assert.deepEqual(afterPaste, beforePaste);
		for (const action of ['stable_diffusion', 'model3d_generation', 'music_generation', 'video_generation', 'web_search', 'text']) {
			const chat = structuredClone(history);
			Object.assign(chat.messages.reply, {
				done: false, content: action === 'text' ? 'Starting content.\n\n'.repeat(75) : '', sources: [], statusHistory: action === 'text' ? [] : [{ action, done: false, description: 'Working...' }]
			});
			const id = 'resume-' + action;
			await page.route('**/api/v1/chats/' + id, r => r.fulfill({ json: {
				id, chat: { title: id, history: chat, models: [model] }, user_id: 'mobile-fixture-user'
			} }));
			await page.route('**/api/tasks/chat/' + id, r => r.fulfill({ json: { task_ids: ['task-' + id] } }));
			await page.route('**/api/tasks/stop/task-' + id, r => r.fulfill({ json: { status: true } }));
			await page.goto(base + '/c/' + id, { waitUntil: 'networkidle' });
			const stop = page.locator('#send-message-button[aria-label="Parar"], #send-message-button[aria-label="Stop"]');
			await stop.waitFor();
			if (action === 'text') {
				const scroll = page.locator('#messages-container');
				const before = await scroll.evaluate(n => [n.scrollTop, n.scrollHeight]);
				assert(before[0] > 0);
				testSocket.send('42' + JSON.stringify(['events', {chat_id:id, message_id:'reply', data:{
					type:'chat:message:delta',data:{content:'\n\nMore text.\n\n'.repeat(35) + 'resumed-stream-marker'}
				}}]));
				await page.getByText('resumed-stream-marker', {exact:true}).waitFor({state:'attached'});
				await page.waitForTimeout(400);
				const after = await scroll.evaluate(n => [n.scrollTop, n.scrollHeight]);
				assert(after[1] > before[1]);
				assert(Math.abs(after[0] - before[0]) <= 1, 'reopened stream must not drag viewport');
			}
			console.log('Resumed', action, width);
			assert.equal(await page.locator('.regenerate-response-button').count(), 0);
			const stopped = page.waitForRequest(r => r.method() === 'POST' && r.url().endsWith('/stop/task-' + id));
			await stop.click();
			await stopped;
			await stop.waitFor({ state: 'hidden' });
			await page.locator('.regenerate-response-button').waitFor({ state: 'attached' });
			if (action === 'model3d_generation') assert.equal(await page.locator('.copy-response-button').count(), 0);
		}
		assert.deepEqual(errors, []);
		console.log('PASS', width, 'suggestions, 3D selector and clipboard, source accordion and icon');
		await page.close();
	}
} finally {
	await browser.close();
}
