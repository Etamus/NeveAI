import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import { createServer } from 'vite';
import { chromium } from '../logs/ui-image-26/node_modules/playwright/index.mjs';
import { installMobileOfflineApi } from './fixtures/mobile-offline-api.mjs';

const hook = `onMount(()=>{window.__artifactProtocol={async seed(content=''){
 for(const id of [..._contentBuffers.keys()])stopContentFlush(id);
 cancelGenerationAnchorRAF();releaseGeneratingMessageAnchor();cancelMessagesBottomWheelLock();
 showArtifacts.set(false);showControls.set(false);artifactContents.set([]);artifactSelection.set(null);
 temporaryChatEnabled.set(true);chatId.set('local:artifact-protocol');await tick();
 loading=false;loadedChatViewportReady=true;deferLoadedChatMessages=false;selectedModels=['local/mobile-fixture'];taskIds=[];autoScroll=false;
 history={currentId:'reply',messages:{question:{id:'question',role:'user',content:'Preview',parentId:null,childrenIds:['reply'],timestamp:1700000000},reply:{id:'reply',role:'assistant',content,done:false,parentId:'question',childrenIds:[],model:'local/mobile-fixture',timestamp:1700000001}}};await tick();
 },event(type,data){return chatEventHandler({chat_id:$chatId,message_id:'reply',data:{type,data}},()=>{});},state(){return{opened:$showArtifacts,content:history.messages.reply.content,done:history.messages.reply.done,buffering:!!_flushRAF}}};return()=>delete window.__artifactProtocol;});`;
let server, browser, page;
const results = [];
try {
	server = await createServer({ plugins: [{ name: 'artifact-protocol', enforce: 'pre', async load(id) {
		if (id.endsWith('/src/lib/components/chat/Chat.svelte')) return (await fs.readFile(id, 'utf8')).replace('</script>', hook + '\n</script>');
	} }], server: { port: 5198, strictPort: true, watch: { ignored: ['**/logs/**', '**/scripts/**', '**/docs/**'] } } });
	await server.listen(); browser = await chromium.launch();
	for (const width of [1440, 390]) {
		page = await browser.newPage({ viewport: { width, height: 900 } });
		await installMobileOfflineApi(page);
		const errors = []; page.on('pageerror', error => errors.push(error.message));
		await page.goto('http://localhost:5198', { waitUntil: 'networkidle', timeout: 90000 });
		await page.waitForFunction(() => window.__artifactProtocol);
		await page.evaluate(() => window.__artifactProtocol.seed());
		const initial = '```html\n<main><h1 id="live">Socket stream</h1><input id="keep" value="initial"><p id="tail">One';
		await page.evaluate(content => window.__artifactProtocol.event('chat:completion', { content }), initial);
		await page.waitForFunction(() => window.__artifactProtocol.state().content.includes('Socket stream'));
		assert.equal((await page.evaluate(() => window.__artifactProtocol.state())).opened, false);
		await page.getByRole('button', { name: /Pré-visualização|Artifact preview/ }).first().click();
		let frame = page.frameLocator('[data-artifact-preview] iframe');
		await frame.locator('#live').waitFor();
		await frame.locator('#keep').fill('retained');
		await page.evaluate(() => window.__artifactProtocol.event('chat:message:delta', { content: ' two</p><p id="added">Delta arrived</p></main>\n```' }));
		await frame.locator('#added').waitFor();
		assert.equal(await frame.locator('#tail').innerText(), 'One two');
		assert.equal(await frame.locator('#keep').inputValue(), 'retained');
		await page.evaluate(() => window.__artifactProtocol.event('chat:completion', { done: true }));
		await page.waitForFunction(() => window.__artifactProtocol.state().done);
		await page.waitForTimeout(350);
		assert.equal(await frame.locator('[data-neve-cursor]').evaluate(node => getComputedStyle(node).opacity), '0');
		assert.equal((await page.evaluate(() => window.__artifactProtocol.state())).buffering, false);
		await page.evaluate(() => window.__artifactProtocol.seed());
		await page.evaluate(content => window.__artifactProtocol.event('chat:completion', { content, done: true }), initial + '</p></main>\n```');
		await page.waitForFunction(() => window.__artifactProtocol.state().done);
		await page.waitForTimeout(400);
		assert.equal((await page.evaluate(() => window.__artifactProtocol.state())).opened, false, 'Completion must not open the panel');
		results.push({ width, completion_gateway: true, snapshot_stream: true, delta_stream: true, input_preserved: true, cursor_stopped: true, no_automatic_open: true });
		const scripts = '```html\n<div id="ordered"></div><script>window.beforeModule="ready";</script><script type="module">document.getElementById("ordered").textContent=window.beforeModule;</script>\n```';
		await page.evaluate(content => window.__artifactProtocol.seed(content), scripts);
		await page.getByRole('button', { name: /Pré-visualização|Artifact preview/ }).first().click();
		frame = page.frameLocator('[data-artifact-preview] iframe');
		await frame.locator('#ordered').waitFor();
		await page.waitForTimeout(300);
		assert.equal(await frame.locator('#ordered').innerText(), 'ready', 'Classic setup must execute before deferred ES modules');
		const imports = '```html\n<div id="mapped"></div><script type="importmap">{"imports":{"project-values":"./values.ts"}}</script><script type="module">import {label} from "project-values";document.getElementById("mapped").textContent=label;</script>\n```\n```ts values.ts\nexport const label:string="Import map works";\n```';
		await page.evaluate(content => window.__artifactProtocol.seed(content), imports);
		await page.getByRole('button', { name: /Pré-visualização|Artifact preview/ }).first().click();
		frame = page.frameLocator('[data-artifact-preview] iframe');
		await frame.locator('#mapped').filter({ hasText: 'Import map works' }).waitFor({ timeout: 10000 });
		await page.route('https://artifact-modules.test/**', route => route.fulfill({ contentType: 'text/javascript', headers: { 'access-control-allow-origin': '*' }, body: new URL(route.request().url()).pathname === '/values.js'
			? 'export const suffix=" preserved";'
			: 'import {suffix} from "remote-value";export const label="Remote import map"+suffix;' }));
		const remote = '```html\n<p id="remote"></p><script type="importmap">{"imports":{"remote-module":"https://artifact-modules.test/module.js","remote-value":"https://artifact-modules.test/values.js"}}</script><script type="module">import {label} from "remote-module";document.getElementById("remote").textContent=label;</script>\n```';
		await page.evaluate(content => window.__artifactProtocol.seed(content), remote);
		await page.getByRole('button', { name: /Pré-visualização|Artifact preview/ }).first().click();
		frame = page.frameLocator('[data-artifact-preview] iframe');
		await frame.locator('#remote').filter({ hasText: 'Remote import map preserved' }).waitFor({ timeout: 10000 });
		const jsonData = '```html\n<script id="config" type="application/json">{"label":"Embedded data preserved"}</script><script id="template" type="text/template"><strong>Template</strong></script><p id="data"></p><script type="text/javascript">const config=JSON.parse(document.getElementById("config").textContent);document.getElementById("data").textContent=config.label;</script>\n```';
		await page.evaluate(content => window.__artifactProtocol.seed(content), jsonData);
		await page.getByRole('button', { name: /Pré-visualização|Artifact preview/ }).first().click();
		frame = page.frameLocator('[data-artifact-preview] iframe');
		await frame.locator('#data').filter({ hasText: 'Embedded data preserved' }).waitFor();
		assert.notEqual(await frame.locator('[data-neve-cursor]').evaluate(node => node.style.transform), '', 'Script-driven DOM changes must move the cursor');
		assert.equal(await frame.locator('#template').textContent(), '<strong>Template</strong>');
		const nested = '```html pages/index.html\n<p id="nested"></p><script type="importmap">{"imports":{"values":"./values.ts"}}</script><script type="module">import {value} from "values";document.getElementById("nested").textContent=value;</script>\n```\n```ts pages/values.ts\nexport const value:string="Nested map works";\n```';
		await page.evaluate(content => window.__artifactProtocol.seed(content), nested);
		await page.getByRole('button', { name: /Pré-visualização|Artifact preview/ }).first().click();
		frame = page.frameLocator('[data-artifact-preview] iframe');
		await frame.locator('#nested').filter({ hasText: 'Nested map works' }).waitFor();
		const plain = '```html\n<h1 id="ordinary">React.useState is only text here</h1>\n```';
		await page.evaluate(content => window.__artifactProtocol.seed(content), plain);
		await page.getByRole('button', { name: /Pré-visualização|Artifact preview/ }).first().click();
		frame = page.frameLocator('[data-artifact-preview] iframe');
		await frame.locator('#ordinary').filter({hasText:'React.useState is only text here'}).waitFor();
		assert.deepEqual(errors, []);
		results.push({ width, classic_module_order: true, virtual_import_map: true, remote_import_map: true, nested_imports: true, embedded_json: true, inert_template: true, errors });
		await page.screenshot({ path: `logs/artifact-protocol-${width}.png` });
		await page.close();
	}
	await fs.writeFile('logs/artifact-protocol-results.json', JSON.stringify(results, null, 2));
	console.log('PASS', results);
} catch (error) {
	console.log('REACHED', results);
	await page?.screenshot({ path: 'logs/artifact-protocol-failed.png' });
	throw error;
} finally { await browser?.close(); await server?.close(); }
