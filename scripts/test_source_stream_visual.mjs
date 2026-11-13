import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import { constants } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { createServer } from 'vite';
import { chromium } from '../logs/ui-image-26/node_modules/playwright/index.mjs';
import { installMobileOfflineApi } from './fixtures/mobile-offline-api.mjs';

const route = new URL('../src/routes/__source_stream_test/', import.meta.url);
await fs.mkdir(route, { recursive: true });
await fs.copyFile(new URL('./fixtures/source-stream-visual.svelte', import.meta.url), new URL('+page.svelte', route), constants.COPYFILE_EXCL);
let server, browser;
const results = [];
try {
	server = await createServer({ server: { port: 5194, strictPort: true, watch: { ignored: ['**/logs/**'] } } });
	await server.listen();
	const { lexChatMarkdown } = await server.ssrLoadModule('/src/lib/utils/marked/chat-lexer.ts');
	const { prepareStreamingMarkdown, stabilizeStreamingBlocks } = await server.ssrLoadModule('/src/lib/utils/marked/streaming-display.ts');
	// Read-only replay of the reported chat; no prompts, generation or database writes.
	const saved = JSON.parse(execFileSync('python', ['-c', "import sqlite3,json; c=sqlite3.connect('file:backend/data/neve.db?mode=ro',uri=True); r=c.execute('select chat from chat where title like ?',('%consulta de bq%',)).fetchone(); print(json.dumps([m['content'] for m in json.loads(r[0]).get('history',{}).get('messages',{}).values() if m.get('role')=='assistant'] if r else []))"], { encoding: 'utf8' }));
	let transientBefore = 0, transientAfter = 0;
	for (const text of saved) {
		assert(!lexChatMarkdown(text).some(t => t.type === 'hr'));
		for (let i = 1; i <= text.length; i++) {
			const parsed = lexChatMarkdown(prepareStreamingMarkdown(text.slice(0, i)));
			transientBefore += parsed.filter(t => t.type === 'hr').length;
			transientAfter += stabilizeStreamingBlocks(parsed).filter(t => t.type === 'hr').length;
		}
	}
	assert.equal(transientAfter, 0);
	if (saved.length) assert(transientBefore > 0, 'Reported chat should reproduce transient rules before stabilization');
	results.push({ savedResponses: saved.length, transientBefore, transientAfter });
	browser = await chromium.launch({ ignoreDefaultArgs: ['--hide-scrollbars'] });
	for (const [name, viewport] of [['desktop', { width: 1440, height: 1000 }], ['mobile', { width: 390, height: 844 }]]) {
		const page = await browser.newPage({ viewport });
		await installMobileOfflineApi(page);
		const errors = [];
		page.on('pageerror', error => errors.push(error.message));
		await page.goto('http://localhost:5194/__source_stream_test', { waitUntil: 'networkidle', timeout: 90000 });
		await page.waitForFunction(() => window.sourceStreamTest);
		for (const mode of ['dark', 'light']) {
			await page.evaluate(mode => document.documentElement.classList.toggle('dark', mode === 'dark'), mode);
			for (const text of ['Intro.\n\n*   **', 'Intro.\n\n*   **Tabela:** valor', 'Intro.\n\n***', 'Intro.\n\n***Importante***']) {
				await page.evaluate(text => window.sourceStreamTest.text(text), text);
				await page.waitForTimeout(350);
				assert.equal(await page.locator('#answer hr').count(), 0, text);
			}
			for (const text of ['Intro.\n\n---\n', 'Intro.\n\n***\n']) {
				await page.evaluate(text => window.sourceStreamTest.text(text), text);
				await page.waitForTimeout(250);
				assert.equal(await page.locator('#answer hr').count(), 1);
			}
			await page.evaluate(() => window.sourceStreamTest.text('Intro.\n\n---', true));
			assert.equal(await page.locator('#answer hr').count(), 1);
			for (const count of [0, 1, 5]) {
				await page.evaluate(count => window.sourceStreamTest.status([{ action: 'sources_retrieved', count, done: true }]), count);
				assert.equal(await page.locator('#status button, #status svg').count(), 0);
			}
			await page.evaluate(() => window.sourceStreamTest.status([{ action: 'queries_generated', description: 'Querying' }, { action: 'sources_retrieved', count: 1, done: true }]));
			assert.equal(await page.locator('#status button, #status svg').count(), 0);
			await page.evaluate(() => window.sourceStreamTest.status([{ action: 'knowledge_search', query: 'SQL', done: true }, { action: 'sources_retrieved', count: 1, done: true }]));
			assert.equal(await page.locator('#status button').count(), 1);
			assert.equal(await page.locator('#status svg').count(), 1);
			await page.locator('#status button').click();
			await page.waitForTimeout(250);
			assert.equal(await page.locator('#status .select-text').count(), 1);
			const inline = await page.locator('#inline code').evaluate(el => ({ border: getComputedStyle(el).borderTopWidth, background: getComputedStyle(el).backgroundColor }));
			assert.equal(inline.border, '0px');
			assert.equal(inline.background, mode === 'dark' ? 'rgb(38, 38, 38)' : 'rgb(246, 247, 248)');
			await page.evaluate(() => window.sourceStreamTest.citation());
			const scroller = page.locator('.max-h-\\[22rem\\]');
			await scroller.waitFor();
			await page.waitForTimeout(250);
			const scrollbar = await scroller.evaluate(el => {
				const ref = document.querySelector('#scroll-reference');
				const props = element => ({ width: getComputedStyle(element, '::-webkit-scrollbar').width, thumb: getComputedStyle(element, '::-webkit-scrollbar-thumb').backgroundColor, scrollbarWidth: getComputedStyle(element).scrollbarWidth });
				return { actual: props(el), reference: props(ref), overflow: el.scrollHeight > el.clientHeight };
			});
			assert.deepEqual(scrollbar.actual, scrollbar.reference);
			assert(scrollbar.overflow);
			await scroller.hover();
			await page.mouse.wheel(0, 250);
			await page.waitForTimeout(200);
			assert(await scroller.evaluate(el => el.scrollTop > 0));
			await page.screenshot({ path: `logs/source-stream-${name}-${mode}.png` });
			await page.keyboard.press('Escape');
			await scroller.waitFor({ state: 'hidden' });
			const pasted = '  # Titulo\n\n\n**Negrito** e `CASE WHEN`\n    indentado\n<div>Literal</div>';
			for (const source of [{ name: 'Notas.txt', pastedText: true }, { name: 'Texto colado' }, { name: 'Texto colado.txt' }]) {
				await page.evaluate(({ source, pasted }) => window.sourceStreamTest.citation({ source, document: [pasted], metadata: [{ html: true }] }), { source, pasted });
				const plain = page.locator('.citation-plain-text');
				await plain.waitFor();
				assert.equal(await plain.textContent(), pasted);
				assert.equal(await plain.locator('strong, code, h1, iframe, div').count(), 0);
				assert.equal(await plain.evaluate(el => getComputedStyle(el).whiteSpace), 'pre-wrap');
				await page.keyboard.press('Escape');
				await plain.waitFor({ state: 'hidden' });
			}
			await page.evaluate(() => window.sourceStreamTest.citation({ source: { name: 'Documento.txt' }, document: ['# Titulo\n\n**Negrito** e `CASE WHEN`'] }));
			await page.locator('.max-h-\\[22rem\\] strong').waitFor();
			assert.equal(await page.locator('.citation-plain-text').count(), 0);
			assert.equal(await page.locator('.max-h-\\[22rem\\] h1').count(), 1);
			await page.keyboard.press('Escape');
			await page.locator('.max-h-\\[22rem\\]').waitFor({ state: 'hidden' });
			results.push({ name, mode, inline, scrollbar });
		}
		assert.deepEqual(errors, []);
		await page.close();
	}
	await fs.writeFile('logs/source-stream-results.json', JSON.stringify(results, null, 2));
	console.log(JSON.stringify(results, null, 2));
} finally {
	await browser?.close();
	await server?.close();
	await fs.rm(route, { recursive: true, force: true });
}
