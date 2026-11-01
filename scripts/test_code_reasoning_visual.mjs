import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import { constants } from 'node:fs';
import { createServer } from 'vite';
import { installMobileOfflineApi } from './fixtures/mobile-offline-api.mjs';
import { chromium } from '../logs/ui-image-26/node_modules/playwright/index.mjs';
import utils from '../logs/ui-image-26/node_modules/playwright-core/lib/utilsBundle.js';
const {PNG}=utils;

// The route exists only during this test; no inference or chat writes.
const routeDir = new URL('../src/routes/__visual_test/', import.meta.url);
const routeFile = new URL('+page.svelte', routeDir);
await fs.mkdir(routeDir, {recursive:true});
await fs.copyFile(new URL('./fixtures/code-reasoning.svelte',import.meta.url),routeFile,constants.COPYFILE_EXCL);
let server;
let browser;
const results = [];
try {
	server = await createServer({server:{port:5188,strictPort:true,watch:{ignored:['**/logs/**']}}});
	await server.listen();
	browser = await chromium.launch({ignoreDefaultArgs:['--hide-scrollbars']});
	for (const [name,viewport] of [['desktop',{width:1440,height:1000}],['mobile',{width:390,height:844}]]) {
		const page = await browser.newPage({viewport, permissions:['clipboard-read','clipboard-write']});
		await installMobileOfflineApi(page);
		page.setDefaultTimeout(15000);
		const errors = [];
		page.on('pageerror', e => errors.push(e.message));
		await page.goto('http://localhost:5188/__visual_test', {waitUntil:'domcontentloaded',timeout:90000});
		await page.locator('.code-scroll').first().waitFor();
		await page.evaluate(() => document.fonts.ready);
		const scrollbar=await page.locator('.code-scroll').first().evaluate(el=>({visibility:getComputedStyle(el,'::-webkit-scrollbar-thumb').visibility,inset:el.closest('.code-body').getBoundingClientRect().right-el.getBoundingClientRect().right}));
		assert.equal(scrollbar.visibility,'visible');
		assert.equal(scrollbar.inset,4);
		assert.equal(await page.locator('.cm-scroller').first().evaluate(el=>getComputedStyle(el,'::-webkit-scrollbar-thumb').visibility),'visible');
		for (const mode of ['dark','light']) {
			await page.evaluate(mode => document.documentElement.classList.toggle('dark',mode==='dark'),mode);
			const wide=page.locator('.code-scroll').last();
			await wide.scrollIntoViewIfNeeded();
			const corner=await wide.evaluate(el=>{
				el.scrollTop=el.scrollHeight;el.scrollLeft=el.scrollWidth;
				return {background:getComputedStyle(el,'::-webkit-scrollbar-corner').backgroundColor,vertical:el.scrollHeight>el.clientHeight,horizontal:el.scrollWidth>el.clientWidth,width:el.offsetWidth-el.clientWidth,height:el.offsetHeight-el.clientHeight};
			});
			assert(corner.vertical&&corner.horizontal,'Both scrollbars must exist');
			assert.equal(corner.background,'rgba(0, 0, 0, 0)');
			const shot=PNG.sync.read(await wide.screenshot({path:`logs/code-corner-${name}-${mode}.png`}));
			const pixel=(shot.height-3)*shot.width*4+(shot.width-3)*4;
			if(mode==='dark')assert(Math.max(...shot.data.subarray(pixel,pixel+3))<70,'Scrollbar corner is light');
			await page.locator('.code-scroll').first().scrollIntoViewIfNeeded();
			const metrics = await page.locator('.code-scroll').first().evaluate(el => ({height:el.clientHeight,scrollHeight:el.scrollHeight,width:el.clientWidth,scrollWidth:el.scrollWidth}));
			assert(metrics.scrollHeight > metrics.height);
			assert(metrics.height <= 366);
			await page.locator('.code-scroll').first().hover();
			const outer = await page.locator('#fixture-scroll').evaluate(el => el.scrollTop);
			await page.mouse.wheel(0,180);
			await page.waitForTimeout(200);
			assert(await page.locator('.code-scroll').first().evaluate(el => el.scrollTop > 0));
			assert.equal(await page.locator('#fixture-scroll').evaluate(el => el.scrollTop),outer);
			await page.locator('.code-scroll').first().evaluate(el => el.scrollTop = 0);
			assert.equal(await page.locator('#fixture-reasoning').evaluate(el => getComputedStyle(el).backgroundColor),'rgba(0, 0, 0, 0)');
			assert.equal(await page.locator('#fixture-reasoning .reasoning-header svg').count(),1); // Chevron only.
			assert.equal(await page.locator('[aria-label="Copy reasoning"]').count(),0);
			await page.screenshot({path:`logs/code-reasoning-${name}-${mode}.png`});
			results.push({name,mode,metrics,corner});
		}
		// Target the wrapper's empty strip, not the mobile toast card itself.
		const toastTop = await page.locator('[data-neve-toast] > div').evaluate(el => el.getBoundingClientRect().top);
		await page.locator('#navbar-hit').evaluate((el, top) => el.style.top = `${top - 20}px`, toastTop);
		await page.locator('#navbar-hit').click();
		assert((await page.locator('#navbar-hit').innerText()).endsWith('1'));
		await page.locator('[data-neve-toast]').evaluate(el => el.remove());
		await page.locator('#fixture-reasoning .reasoning-header').click();
		assert.equal(await page.locator('#fixture-reasoning [aria-hidden]').first().getAttribute('aria-hidden'),'true');
		await page.locator('#fixture-reasoning .reasoning-header').click();
		const scroll = page.locator('.code-scroll').first();
		await scroll.evaluate(el => el.scrollTop = 80);
		await page.locator('#append-code').click();
		await page.waitForTimeout(250);
		assert.equal(await scroll.evaluate(el => el.scrollTop),80);
		await page.locator('#stream-reasoning').click();
		await page.locator('#finish').click();
		assert.equal(await page.locator('#fixture-reasoning [aria-hidden]').first().getAttribute('aria-hidden'),'true');
		assert(await page.locator('.cm-scroller').first().evaluate(el => el.clientHeight <= 366 && el.scrollHeight > el.clientHeight));
		await page.locator('.copy-code-button').first().click();
		assert((await page.evaluate(() => navigator.clipboard.readText())).includes('New line'));
		const downloadPromise = page.waitForEvent('download');
		await page.locator('.code-toolbar').first().locator('button').nth(2).click();
		assert.equal((await downloadPromise).suggestedFilename(),'code.python');
		await page.locator('#fixture-preview .code-toolbar button').last().click();
		assert.equal(await page.locator('#preview-count').innerText(),'1');
		await page.route('**/api/v1/utils/code/execute',route => route.fulfill({json:{stdout:'Execution verified',stderr:'',result:null}}));
		await page.locator('#mock-execution').click();
		await page.locator('.run-code-button').first().click();
		await page.getByText('Execution verified',{exact:true}).waitFor();
		await page.locator('#error-toast').click();
		await page.locator('[data-sonner-toast]').waitFor();
		await page.locator('[data-close-button]').click();
		await page.locator('[data-sonner-toast]').waitFor({state:'detached'});
		assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth),false);
		assert(await page.locator('.code-scroll').last().evaluate(el => el.scrollWidth > el.clientWidth));
		await page.locator('#fixture-parsed .reasoning-header').click();
		await page.getByText('First paragraph.',{exact:true}).waitFor();
		assert.equal(await page.locator('#fixture-parsed blockquote').evaluate(el => getComputedStyle(el).borderLeftWidth),'0px');
		assert.equal(await page.locator('#fixture-interpreter').evaluate(el => getComputedStyle(el).borderTopWidth),'0px');
		assert.deepEqual(errors,[]);
		await page.close();
	}
	await fs.writeFile('logs/code-reasoning-results.json', JSON.stringify(results,null,2));
	console.log(JSON.stringify(results));
} finally {
	await browser?.close();
	await server?.close();
	await fs.unlink(routeFile);
	await fs.rmdir(routeDir);
}
