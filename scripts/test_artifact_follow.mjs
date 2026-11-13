import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import { createServer } from 'vite';
import { chromium } from '../logs/ui-image-26/node_modules/playwright/index.mjs';
import { installMobileOfflineApi } from './fixtures/mobile-offline-api.mjs';

const hook = `onMount(()=>{window.__followStudy={async seed(content){
 cancelGenerationAnchorRAF();releaseGeneratingMessageAnchor();cancelMessagesBottomWheelLock();
 showArtifacts.set(false);showControls.set(false);artifactContents.set([]);artifactSelection.set(null);
 temporaryChatEnabled.set(true);chatId.set('local:follow-study');await tick();
 loading=false;loadedChatViewportReady=true;deferLoadedChatMessages=false;selectedModels=['local/mobile-fixture'];taskIds=[];autoScroll=false;
 history={currentId:'reply',messages:{question:{id:'question',role:'user',content:'Create a landing page',parentId:null,childrenIds:['reply'],timestamp:1700000000},reply:{id:'reply',role:'assistant',content,done:false,parentId:'question',childrenIds:[],model:'local/mobile-fixture',timestamp:1700000001}}};await tick();
 },append(content,done=false){history.messages.reply.content=content;history.messages.reply.done=done;history={...history};},hide(){showControls.set(false)},state(){return{active:$artifactPanelActive,opened:$showArtifacts,entries:$artifactContents}}};return()=>delete window.__followStudy;});`;
const source = (value, nested = false) =>
	'```html\n<html><head><style>body{margin:0;font:16px sans-serif}section{height:1600px}p{margin:0;height:48px}</style></head><body>' +
	(nested ? '<div id="scroller" style="height:220px;overflow:auto;margin:20px">' : '') +
	'<section>Top</section><p id="target">' +
	value +
	'</p><section>Footer</section>' +
	(nested ? '</div>' : '') +
	'</body></html>\n';
let server, browser, page;
const results = [];
try {
	server = await createServer({
		plugins: [
			{
				name: 'artifact-follow-study',
				enforce: 'pre',
				async load(id) {
					if (id.endsWith('/src/lib/components/chat/Chat.svelte'))
						return (await fs.readFile(id, 'utf8')).replace('</script>', hook + '\n</script>');
				}
			}
		],
		server: {
			port: 5199,
			strictPort: true,
			watch: { ignored: ['**/logs/**', '**/scripts/**', '**/docs/**'] }
		}
	});
	await server.listen();
	browser = await chromium.launch();
	for (const width of process.env.FOLLOW_MOBILE_ONLY ? [390] : [1440, 390]) {
		page = await browser.newPage({ viewport: { width, height: width === 390 ? 844 : 1000 } });
		await installMobileOfflineApi(page);
		await page.addInitScript(() => {
			const NativeObserver = window.IntersectionObserver;
			window.__panelIntersections = [];
			window.IntersectionObserver = class extends NativeObserver {
				constructor(callback, options) {
					super((entries, observer) => {
						for (const entry of entries)
							if (entry.target.id === 'artifacts-container')
								window.__panelIntersections.push({
									intersecting: entry.isIntersecting,
									rect: entry.intersectionRect.toJSON(),
									bounds: entry.boundingClientRect.toJSON()
								});
						callback(entries, observer);
					}, options);
				}
			};
		});
		const errors = [];
		page.on('pageerror', (error) => errors.push(error.message));
		await page.goto('http://localhost:5199', { waitUntil: 'networkidle', timeout: 90000 });
		await page.waitForFunction(() => window.__followStudy);
		await page.evaluate((content) => window.__followStudy.seed(content), source('Initial'));
		const open = async () => {
			await page
				.getByRole('button', { name: /Pré-visualização|Artifact preview/ })
				.first()
				.click();
			await page.waitForFunction(() => window.__followStudy.state().active);
		};
		await open();
		const frameLocator = page.frameLocator('[data-artifact-preview] iframe');
		await frameLocator.locator('#target').waitFor({ timeout: 45000 });
		let child = await (
			await page.locator('[data-artifact-preview] iframe').elementHandle()
		).contentFrame();
		await page.waitForTimeout(300);
		await child.evaluate(() => scrollTo(0, 0));
		const hostBefore = await page.locator('#messages-container').evaluate((node) => node.scrollTop);
		await page.evaluate(
			(content) => window.__followStudy.append(content),
			source('Below viewport')
		);
		await frameLocator.locator('#target').filter({ hasText: 'Below viewport' }).waitFor();
		await page.waitForTimeout(300);
		const windowFollow = await child.evaluate(() => {
			const b = document.querySelector('#target').getBoundingClientRect();
			return { scroll: scrollY, top: b.top, height: innerHeight };
		});
		assert(
			windowFollow.scroll > 0 &&
				windowFollow.top >= 0 &&
				windowFollow.top + 16 < windowFollow.height,
			'Window must reveal the changed target'
		);
		assert.equal(
			await page.locator('#messages-container').evaluate((node) => node.scrollTop),
			hostBefore,
			'Preview scrolling must not scroll the host chat'
		);
		await page.screenshot({ path: `logs/artifact-follow-${width}.png` });

		// Simulate the browser visibility signal without freezing the application under test.
		await page.evaluate(() => {
			window.__studyHidden = true;
			Object.defineProperty(document, 'visibilityState', {
				configurable: true,
				get: () => (window.__studyHidden ? 'hidden' : 'visible')
			});
			document.dispatchEvent(new Event('visibilitychange'));
		});
		await page.waitForFunction(() => !window.__followStudy.state().active);
		await page.waitForTimeout(200);
		await child.evaluate(() => scrollTo(0, 0));
		await page.evaluate((content) => window.__followStudy.append(content), source('Hidden change'));
		await page.waitForTimeout(800);
		assert.equal(
			await frameLocator.locator('#target').innerText(),
			'Below viewport',
			'Hidden panels must not compile source updates'
		);
		assert.equal(await child.evaluate(() => scrollY), 0);
		assert.equal(
			await frameLocator
				.locator('[data-neve-cursor]')
				.evaluate((node) => getComputedStyle(node).opacity),
			'0'
		);
		await page.evaluate(() => {
			window.__studyHidden = false;
			document.dispatchEvent(new Event('visibilitychange'));
		});
		await frameLocator.locator('#target').filter({ hasText: 'Hidden change' }).waitFor();
		await page.waitForTimeout(200);
		assert(
			(await child.evaluate(() => scrollY)) > 0,
			'Resume must apply the latest snapshot and reveal its target'
		);

		await page.evaluate(
			(content) => window.__followStudy.append(content),
			source('Nested initial', true)
		);
		await frameLocator.locator('#scroller').waitFor();
		await page.waitForTimeout(300);
		await child.evaluate(() => {
			scrollTo(0, 0);
			document.querySelector('#scroller').scrollTop = 0;
		});
		await page.evaluate(
			(content) => window.__followStudy.append(content),
			source('Nested change', true)
		);
		await frameLocator.locator('#target').filter({ hasText: 'Nested change' }).waitFor();
		await page.waitForTimeout(200);
		const nestedFollow = await child.evaluate(() => {
			const outer = document.querySelector('#scroller'),
				b = outer.getBoundingClientRect(),
				target = document.querySelector('#target').getBoundingClientRect();
			return {
				scroll: outer.scrollTop,
				top: target.top,
				containerTop: b.top,
				height: outer.clientHeight,
				windowScroll: scrollY
			};
		});
		assert(
			nestedFollow.scroll > 0 &&
				nestedFollow.top >= nestedFollow.containerTop &&
				nestedFollow.top + 16 < nestedFollow.containerTop + nestedFollow.height,
			'Nested scrollers must reveal their changed target'
		);
		await page.evaluate(
			(content) => window.__followStudy.append(content, true),
			source('Finished', true) + '```'
		);
		await frameLocator.locator('#target').filter({ hasText: 'Finished' }).waitFor();
		await page.waitForTimeout(300);
		await child.evaluate(() => {
			document.querySelector('#scroller').scrollTop = 0;
			document.querySelector('#target').textContent = 'Runtime change after completion';
		});
		await page.waitForTimeout(200);
		assert.equal(
			await child.evaluate(() => document.querySelector('#scroller').scrollTop),
			0,
			'Completed artifacts must not auto-follow runtime mutations'
		);

		const react =
			'```tsx App.tsx\nexport default function App(){return <p id="react">Active compiler</p>}\n';
		await page.evaluate((content) => window.__followStudy.seed(content), react);
		await open();
		await frameLocator.locator('#react').waitFor({ timeout: 45000 });
		assert(page.workers().length > 0, 'React compilation must actually create a worker');
		await page.evaluate(() => {
			window.__studyHidden = true;
			document.dispatchEvent(new Event('visibilitychange'));
		});
		await page.waitForFunction(() => !window.__followStudy.state().active);
		await page.waitForTimeout(200);
		assert.equal(page.workers().length, 0, 'Hidden previews must terminate compiler workers');
		await page.evaluate(
			(content) => window.__followStudy.append(content),
			react.replace('Active compiler', 'Resumed compiler')
		);
		await page.waitForTimeout(500);
		assert.equal(await frameLocator.locator('#react').innerText(), 'Active compiler');
		await page.evaluate(() => {
			window.__studyHidden = false;
			document.dispatchEvent(new Event('visibilitychange'));
		});
		await frameLocator.locator('#react').filter({ hasText: 'Resumed compiler' }).waitFor();
		await page
			.locator(
				'#artifacts-container button[title="Code"],#artifacts-container button[title="Código"]'
			)
			.click();
		await page.waitForTimeout(200);
		assert.equal(await page.locator('[data-artifact-preview] iframe').count(), 0);
		assert.equal(page.workers().length, 0, 'Code tab must not keep preview compiler workers');
		await page.evaluate(() => window.__followStudy.hide());
		await page.waitForTimeout(200);
		assert.equal((await page.evaluate(() => window.__followStudy.state())).active, false);
		const closedBefore = JSON.stringify(
			(await page.evaluate(() => window.__followStudy.state())).entries
		);
		await page.evaluate(
			(content) => window.__followStudy.append(content),
			react.replace('Active compiler', 'Closed update')
		);
		await page.waitForTimeout(600);
		assert.equal(
			JSON.stringify((await page.evaluate(() => window.__followStudy.state())).entries),
			closedBefore,
			'Closed panels must not extract new artifact snapshots'
		);
		assert.equal(page.workers().length, 0);
		assert.deepEqual(errors, []);
		results.push({
			width,
			windowFollow,
			nestedFollow,
			host_scroll_preserved: true,
			hidden_pauses_updates: true,
			resume_latest: true,
			finished_stops_following: true,
			hidden_terminates_worker: true,
			code_tab_terminates_worker: true,
			closed_stops_extraction: true,
			errors
		});
		console.log('PASS', width);
		await page.close();
	}
	await fs.writeFile('logs/artifact-follow-results.json', JSON.stringify(results, null, 2));
} catch (error) {
	const debug = await page?.evaluate(() => ({
		intersections: window.__panelIntersections,
		state: window.__followStudy?.state(),
		visibility: document.visibilityState,
		panels: [...document.querySelectorAll('#artifacts-container')].map((node) => {
			const ancestors = [];
			for (let p = node; p; p = p.parentElement)
				ancestors.push({
					tag: p.tagName,
					class: p.className,
					rect: p.getBoundingClientRect().toJSON(),
					overflow: getComputedStyle(p).overflow
				});
			return { rect: node.getBoundingClientRect().toJSON(), ancestors };
		})
	}));
	console.log('STATE', JSON.stringify(debug, null, 2));
	await page?.screenshot({ path: 'logs/artifact-follow-failed.png' });
	throw error;
} finally {
	await browser?.close();
	await server?.close();
}
