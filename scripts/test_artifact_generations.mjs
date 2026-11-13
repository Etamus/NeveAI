import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import { createServer } from 'vite';
import { chromium } from '../logs/ui-image-26/node_modules/playwright/index.mjs';
import { installMobileOfflineApi } from './fixtures/mobile-offline-api.mjs';

const hook = `import {artifactCode} from '$lib/stores';onMount(()=>{window.__generations={async seed(content){
 for(const id of [..._contentBuffers.keys()])stopContentFlush(id);
 cancelGenerationAnchorRAF();releaseGeneratingMessageAnchor();cancelMessagesBottomWheelLock();
 showArtifacts.set(false);showControls.set(false);artifactContents.set([]);artifactSelection.set(null);artifactCode.set(null);
 temporaryChatEnabled.set(true);chatId.set('local:artifact-generations');await tick();
 loading=false;loadedChatViewportReady=true;deferLoadedChatMessages=false;selectedModels=['local/mobile-fixture'];taskIds=[];autoScroll=false;
 history={currentId:'first',messages:{question:{id:'question',role:'user',content:'Make a page',parentId:null,childrenIds:['first'],timestamp:1700000000},first:{id:'first',role:'assistant',content,done:false,parentId:'question',childrenIds:[],model:'local/mobile-fixture',timestamp:1700000001}}};await tick();
 },next(id){const previous=history.currentId;const userId=id+'-user';history.messages[previous].childrenIds=[userId];history.messages[userId]={id:userId,role:'user',content:'Edit the page',parentId:previous,childrenIds:[id],timestamp:1700000002};history.messages[id]={id,role:'assistant',content:'',done:false,parentId:userId,childrenIds:[],model:'local/mobile-fixture',timestamp:1700000003};history.currentId=id;history={...history};},regenerate(){const message=history.messages[history.currentId];message.content='';message.done=false;history={...history};},event(type,data){return chatEventHandler({chat_id:$chatId,message_id:history.currentId,data:{type,data}},()=>{});},state(){return{selected:$artifactSelection,entries:$artifactContents,content:history.messages[history.currentId].content,done:history.messages[history.currentId].done,opened:$showArtifacts}}};return()=>delete window.__generations;});`;
const source = (label) =>
	'```html\n<html><body><h1 id="generation">' +
	label +
	'</h1><input id="keep" value="initial"></body></html>\n';
let server, browser, page;
const results = [];
try {
	server = await createServer({
		plugins: [
			{
				name: 'artifact-generations',
				enforce: 'pre',
				async load(id) {
					if (id.endsWith('/src/lib/components/chat/Chat.svelte'))
						return (await fs.readFile(id, 'utf8')).replace('</script>', hook + '\n</script>');
				}
			}
		],
		server: {
			port: 5197,
			strictPort: true,
			watch: { ignored: ['**/logs/**', '**/scripts/**', '**/docs/**'] }
		}
	});
	await server.listen();
	browser = await chromium.launch();
	for (const width of [1440, 390]) {
		page = await browser.newPage({ viewport: { width, height: 900 } });
		await installMobileOfflineApi(page);
		await page.addInitScript(() => {
			window.__cursorPositions = [];
			new MutationObserver(() => {
				const cursor = document.querySelector('[data-neve-cursor]');
				if (cursor) {
					const position = cursor.style.transform;
					const last = window.__cursorPositions.at(-1);
					if (last?.position !== position)
						window.__cursorPositions.push({ position, width: innerWidth, height: innerHeight });
				}
			}).observe(document, {
				subtree: true,
				childList: true,
				attributes: true,
				attributeFilter: ['style']
			});
		});
		const errors = [];
		page.on('pageerror', (error) => errors.push(error.message));
		await page.goto('http://localhost:5197', { waitUntil: 'networkidle', timeout: 90000 });
		await page.waitForFunction(() => window.__generations);
		await page.evaluate((content) => window.__generations.seed(content), source('First'));
		await page
			.getByRole('button', { name: /Pré-visualização|Artifact preview/ })
			.first()
			.click();
		const frame = page.frameLocator('[data-artifact-preview] iframe');
		await frame.locator('#generation').filter({ hasText: 'First' }).waitFor();
		await page.evaluate(() => window.__generations.event('chat:completion', { done: true }));
		await page.waitForFunction(() => window.__generations.state().done);
		await page.waitForTimeout(300);
		await page.evaluate(() => window.__generations.next('second'));
		await frame.locator('[data-neve-cursor]').evaluate((node) => {
			window.__cursorPositions = [];
		});
		await page.waitForTimeout(350);
		const waiting = await frame.locator('[data-neve-cursor]').evaluate((node) => ({
			transform: node.style.transform,
			opacity: getComputedStyle(node).opacity,
			width: innerWidth,
			height: innerHeight
		}));
		const waitingXY = waiting.transform
			.match(/translate\(([-\d.]+)px,\s*([-\d.]+)px\)/)
			?.slice(1)
			.map(Number);
		assert(
			waiting.opacity === '1' &&
				waitingXY &&
				Math.abs(waitingXY[0] - (waiting.width - 24) / 2) < 1 &&
				Math.abs(waitingXY[1] - (waiting.height - 28) / 2) < 1,
			'The cursor must start centered while the next response is still waiting for its first code block'
		);
		await page.evaluate(
			(content) => window.__generations.event('chat:completion', { content }),
			source('Second request')
		);
		await frame
			.locator('#generation')
			.filter({ hasText: 'Second request' })
			.waitFor({ timeout: 6000 });
		assert.equal((await page.evaluate(() => window.__generations.state())).selected, 'second:html');
		const checkCenter = async () => {
			const child = await (
				await page.locator('[data-artifact-preview] iframe').elementHandle()
			).contentFrame();
			const positions = await child.evaluate(() => window.__cursorPositions);
			assert(
				positions.some(({ position, width, height }) => {
					const p = position
						.match(/translate\(([-\d.]+)px,\s*([-\d.]+)px\)/)
						?.slice(1)
						.map(Number);
					return (
						p && Math.abs(p[0] - (width - 24) / 2) < 1 && Math.abs(p[1] - (height - 28) / 2) < 1
					);
				}),
				'Each live generation must place the cursor in the center before following changes'
			);
		};
		await checkCenter();
		// Multiple updates in one response must retain the same browsing context and input state.
		let child = await (
			await page.locator('[data-artifact-preview] iframe').elementHandle()
		).contentFrame();
		const identity = await child.evaluate(() => (window.__identity = Math.random()));
		await frame.locator('#keep').fill('retained');
		for (let i = 0; i < 12; i++) {
			await page.evaluate(
				(content) => window.__generations.event('chat:completion', { content }),
				source('Second chunk ' + i)
			);
			await page.waitForTimeout(40);
		}
		await frame.locator('#generation').filter({ hasText: 'Second chunk 11' }).waitFor();
		assert.equal(await child.evaluate(() => window.__identity), identity);
		assert.equal(await frame.locator('#keep').inputValue(), 'retained');
		const partialScript = source('HTML continues with incomplete JavaScript').replace(
			'</body>',
			'<script>function pending(</script></body>'
		);
		await page.evaluate(
			(content) => window.__generations.event('chat:completion', { content }),
			partialScript
		);
		await frame
			.locator('#generation')
			.filter({ hasText: 'HTML continues with incomplete JavaScript' })
			.waitFor();
		const validScript = source('JavaScript complete').replace(
			'</body>',
			'<script>document.getElementById("generation").dataset.executed="yes";</script></body>'
		);
		await page.evaluate(
			(content) => window.__generations.event('chat:completion', { content }),
			validScript
		);
		await frame.locator('#generation[data-executed="yes"]').waitFor();
		await page.evaluate(() => window.__generations.event('chat:completion', { done: true }));
		await page.waitForFunction(() => window.__generations.state().done);
		await page.waitForTimeout(300);
		assert.equal(
			await frame.locator('[data-neve-cursor]').evaluate((node) => getComputedStyle(node).opacity),
			'0'
		);
		await child.evaluate(() => {
			window.__cursorPositions = [];
		});
		await page.evaluate(() => window.__generations.regenerate());
		await page.waitForTimeout(650);
		assert.equal(
			(await page.evaluate(() => window.__generations.state())).opened,
			true,
			'Waiting for regenerated code must not close the panel'
		);
		assert.equal(
			await frame.locator('#generation').innerText(),
			'JavaScript complete',
			'The last preview must remain until replacement code arrives'
		);
		await page.evaluate(
			(content) => window.__generations.event('chat:completion', { content }),
			source('Regenerated')
		);
		await frame.locator('#generation').filter({ hasText: 'Regenerated' }).waitFor();
		await checkCenter();
		await page.evaluate(() => window.__generations.event('chat:completion', { done: true }));
		await page.waitForFunction(() => window.__generations.state().done);
		await page.waitForTimeout(300);
		await page.evaluate(() => window.__generations.next('third'));
		await page.evaluate(
			(content) => window.__generations.event('chat:completion', { content }),
			source('Third request')
		);
		await frame.locator('#generation').filter({ hasText: 'Third request' }).waitFor();
		await checkCenter();
		await page.screenshot({ path: `logs/artifact-generations-${width}.png` });
		assert.deepEqual(errors, []);
		results.push({
			width,
			new_request_updates: true,
			regeneration_updates: true,
			cursor_starts_center: true,
			stream_context_retained: true,
			input_retained: true,
			cursor_hides_on_finish: true,
			errors
		});
		console.log('PASS', width);
		await page.close();
	}
	await fs.writeFile('logs/artifact-generations-results.json', JSON.stringify(results, null, 2));
} catch (error) {
	console.log('FAILURE', error);
	try {
		console.log('STATE', await page?.evaluate(() => window.__generations?.state()));
	} catch {}
	await page?.screenshot({ path: 'logs/artifact-generations-failed.png' });
	throw error;
} finally {
	await browser?.close();
	await server?.close();
}
