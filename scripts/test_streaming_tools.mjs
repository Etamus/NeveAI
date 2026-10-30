import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import { constants } from 'node:fs';
import { createServer } from 'vite';
import { chromium } from '../logs/ui-image-26/node_modules/playwright/index.mjs';

const dir=new URL('../src/routes/__streaming_test/',import.meta.url),file=new URL('+page.svelte',dir);
await fs.mkdir(dir,{recursive:true});
await fs.copyFile(new URL('./fixtures/streaming-tools.svelte',import.meta.url),file,constants.COPYFILE_EXCL);
let server,browser;
const results=[];
try {
	server=await createServer({server:{port:5188,strictPort:true,watch:{ignored:['**/logs/**']}}});await server.listen();
	browser=await chromium.launch({ignoreDefaultArgs:['--hide-scrollbars']});
	for(const [name,viewport] of [['desktop',{width:1440,height:1000}],['mobile',{width:390,height:844}]]) {
		const page=await browser.newPage({viewport});page.setDefaultTimeout(12000);
		const errors=[];page.on('pageerror',e=>errors.push(e.message));
		await page.route('**/api/chat/completions',r=>r.abort());
		await page.route('**/__tool_embed',r=>r.fulfill({contentType:'text/html',body:'<!doctype html><html><body>Embedded output</body></html>'}));
		await page.goto('http://localhost:5188/__streaming_test',{waitUntil:'networkidle'});
		await page.locator('#stream p').waitFor();await page.evaluate(()=>document.fonts.ready);
		const send=async(content,done=false)=>{
			await page.evaluate(detail=>window.dispatchEvent(new CustomEvent('neve-test-stream',{detail})),{content,done});
			await page.waitForTimeout(85);
		};
		const intro='Stable introduction.\n\n';
		const firstRect=await page.locator('#stream p').first().boundingBox();
		for(const text of ['**Analy','**Analyzing the request','*List item','`code fragment']) {
			await send(`<details type="reasoning" done="false" duration="0">\n<summary>Thinking</summary>\n&gt; ${text}\n</details>`);
			assert.equal(await page.locator('#stream > p').count(),0,'Reasoning leaked Markdown markers into the answer');
			assert.equal(await page.locator('#stream .reasoning-header').count(),1);
		}
		await send(intro);
		const cases=['**formatted words','*italic words','~~deleted words','`inline code'];
		const inline=[];
		for(const tail of cases) {
			await send(intro+tail);
			const before=await page.locator('#stream').boundingBox();
			const end=tail.startsWith('**')?'**':tail.startsWith('~~')?'~~':tail[0];
			await send(intro+tail+end,true);
			const after=await page.locator('#stream').boundingBox();
			assert(Math.abs(after.height-before.height)<=0.5,`${name}: inline completion changed height`);
			inline.push({tail,heightDelta:after.height-before.height});
		}
		await send(intro+'[Link label](https://example.com');
		const linkBefore=await page.locator('#stream').boundingBox();
		assert.equal(await page.locator('#stream a').count(),0);
		await send(intro+'[Link label](https://example.com)',true);
		const linkAfter=await page.locator('#stream').boundingBox();
		assert(Math.abs(linkBefore.height-linkAfter.height)<=0.5);
		assert.equal(await page.locator('#stream a').getAttribute('href'),'https://example.com');
		for(const tail of ['| Name | Value |','| Name | Value |\n| --']) {
			await send(intro+tail);assert(!(await page.locator('#stream').innerText()).includes('| Name'));
		}
		const table='| Name | Value |\n| --- | --- |\n| First row | Stable value |\n';
		await send(intro+table);
		const stableCell=await page.locator('#stream tbody tr').first().boundingBox();
		for(const extra of ['| Second','| Second row | longer cell','| Second row | '+ 'long words '.repeat(12)+' |\n\nFollowing paragraph.']) {
			await send(intro+table+extra);
			const cell=await page.locator('#stream tbody tr').first().boundingBox();
			assert(Math.abs(cell.x-stableCell.x)<=0.5&&Math.abs(cell.y-stableCell.y)<=0.5&&Math.abs(cell.width-stableCell.width)<=0.5,JSON.stringify({name,cell,stableCell}));
		}
		const samples=['# Heading\n\n- Item one\n- **Item two**','> Quote\n> continued','```python\nprint("sample")\n```',String.raw`Math $x^2$ and display:

$$
x^2 + y^2
$$`,'[site][ref]\n\n[ref]: https://example.com','<details type="reasoning" done="true" duration="2">\n<summary>Thought</summary>\n&gt; Thought content\n</details>'];
		for(const sample of samples) {
			for(const fraction of [0.25,0.5,0.75,1]) {
				await send(intro+sample.slice(0,Math.ceil(sample.length*fraction)));
				const rect=await page.locator('#stream > p').first().boundingBox();
				assert(Math.abs(rect.x-firstRect.x)<=0.5&&Math.abs(rect.y-firstRect.y)<=0.5,'Existing text shifted');
			}
			await send(intro+sample,true);
		}
		await send(intro+'Final **formatted** output.',true);
		for(const i of [0,1,2,3]) {
			const heading=page.locator(`#status-${i}`);
			const leading=heading.locator('svg');
			assert.equal(await leading.count(),1,`Non-media status ${i} has a leading icon`);
		}
		const mediaSize=await page.locator('#status-5 svg').evaluate(el=>({width:el.getBoundingClientRect().width,height:el.getBoundingClientRect().height}));
		for(const i of [4,5,6]) {
			assert.equal(await page.locator(`#status-${i} svg`).count(),1,'Media icon missing');
			const size=await page.locator(`#status-${i} svg`).evaluate(el=>({width:el.getBoundingClientRect().width,height:el.getBoundingClientRect().height}));
			assert.deepEqual(size,mediaSize,'Media status icon size differs');
			assert.equal(await page.locator(`#status-${i} button`).count(),0,'Media status became clickable');
		}
		await page.locator('#status-1 .web-search-block > div').first().click();
		await page.locator('#status-1 a').first().waitFor();assert.equal(await page.locator('#status-1 a').count(),8);
		await page.locator('#status-1 button').filter({hasText:'+3'}).last().click();assert.equal(await page.locator('#status-1 a').count(),11);
		await page.locator('#tool [data-message-expanded]').count();
		await page.locator('#tool .tool-call-heading').click();await page.getByText('Verified output',{exact:false}).waitFor();
		assert.equal(await page.locator('#tool .tool-call-heading svg').count(),1);
		assert.equal(await page.locator('#tool-running .tool-call-heading svg').count(),1);
		assert.equal(await page.locator('#tool-running .tool-call-heading.shimmer').count(),1);
		await page.frameLocator('#tool-embed iframe').getByText('Embedded output',{exact:true}).waitFor();
		await page.locator('#history > div > button').click();
		await page.getByText('first',{exact:true}).waitFor();
		for(const theme of ['light','dark']) {
			await page.evaluate(t=>document.documentElement.classList.toggle('dark',t==='dark'),theme);
			await page.locator('#tools-fixture').evaluate(el=>el.scrollTop=0);
			await page.screenshot({path:`logs/tools-minimal-${name}-${theme}.png`});
		}
		assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
		assert.deepEqual(errors,[]);results.push({name,inline,streamCases:samples.length,errors});await page.close();
	}
	await fs.writeFile('logs/streaming-tools-results.json',JSON.stringify(results,null,2));console.log(JSON.stringify(results));
} finally {await browser?.close();await server?.close();await fs.unlink(file);await fs.rmdir(dir);}
