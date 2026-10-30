import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import { createServer } from 'vite';
import { chromium } from '../logs/ui-image-26/node_modules/playwright/index.mjs';

const baseline=process.env.BASELINE==='1';
const server=await createServer({server:{port:5188,strictPort:true,watch:{ignored:['**/logs/**']}}});
await server.listen();
const browser=await chromium.launch({ignoreDefaultArgs:['--hide-scrollbars']});
const results=[];
try {
	for(const [name,viewport] of [['desktop',{width:1440,height:1000}],['mobile',{width:390,height:844}]]) {
		const page=await browser.newPage({viewport});
		// Keep a keyboard-regression mistake from ever starting real inference.
		await page.route('**/api/chat/completions',route=>route.abort());
		await page.route('**/api/v1/chats/new',route=>route.abort());
		const errors=[];
		page.on('pageerror',error=>errors.push(error.message));
		await page.goto('http://localhost:5188',{waitUntil:'networkidle'});
		await page.locator('#chat-input').waitFor();
		await page.evaluate(()=>document.fonts.ready);
		const input=page.locator('#chat-input'), scroller=page.locator('#chat-input-container');
		await input.fill(Array.from({length:40},(_,i)=>`Line ${i} with some text`).join('\n'));
		await page.waitForTimeout(250);
		await input.press('Control+End');
		const samples=[];
		await page.evaluate(()=>{
			window.typingFrames=[];window.trackTyping=true;
			const frame=()=>{if(!window.trackTyping)return;const e=document.querySelector('#chat-input-container');const p=e.querySelector('.ProseMirror').lastElementChild;
				window.typingFrames.push({top:e.scrollTop,total:e.scrollHeight,gap:e.getBoundingClientRect().bottom-p.getBoundingClientRect().bottom});requestAnimationFrame(frame);};requestAnimationFrame(frame);
		});
		await page.keyboard.type('       space words    more text       ',{delay:30});
		await page.waitForTimeout(100);
		const typingFrames=await page.evaluate(()=>{window.trackTyping=false;return window.typingFrames;});
		const reversals=typingFrames.slice(1).filter((f,i)=>f.total===typingFrames[i].total&&f.top<typingFrames[i].top-1);
		if(!baseline) assert.equal(reversals.length,0,`${name}: typing scroll bounced ${JSON.stringify(reversals)}`);
		const measure=()=>scroller.evaluate(el=>({top:el.scrollTop,max:el.scrollHeight-el.clientHeight,height:el.clientHeight,total:el.scrollHeight,bottom:el.getBoundingClientRect().bottom,last:el.querySelector('.ProseMirror').lastElementChild.getBoundingClientRect().bottom}));
		for(let i=0;i<3;i++) {
			if(i===1) await page.keyboard.press('Shift+Enter');
			await page.keyboard.type(' more text');
			await page.waitForTimeout(150);
			const before=await measure();
			await scroller.hover();
			await page.mouse.wheel(0,1000);
			await page.waitForTimeout(150);
			const after=await measure();
			samples.push({before,after,extra:after.top-before.top});
			if(!baseline) assert(Math.abs(after.top-before.top)<=0.5,`${name}: extra scroll after typing ${JSON.stringify({before,after})}`);
		}
		if(!baseline) {
			for(const mode of ['light','dark']) {
				await page.evaluate(mode=>document.documentElement.classList.toggle('dark',mode==='dark'),mode);
				await page.screenshot({path:`logs/composer-scroll-${name}-${mode}.png`});
			}
			await scroller.evaluate(el=>el.scrollTop=0);
			await page.waitForTimeout(100);
			assert.equal(await scroller.evaluate(el=>getComputedStyle(el).maskImage),'none');
			await scroller.evaluate(el=>el.scrollTop=100);
			await page.waitForTimeout(100);
			assert.notEqual(await scroller.evaluate(el=>getComputedStyle(el).maskImage),'none');
			await input.press('Control+Home');
			await page.keyboard.type('Edit start ');
			await page.waitForTimeout(150);
			assert((await measure()).top<50,'Editing the beginning jumped to the end');
			await input.fill('Short text');
			await page.waitForTimeout(150);
			assert.equal(await scroller.evaluate(el=>getComputedStyle(el).maskImage),'none');
			assert.deepEqual(errors,[]);
		}
		results.push({name,samples,typingFrames,errors});
		await page.close();
	}
	await fs.writeFile(`logs/composer-scroll-${baseline?'before':'after'}.json`,JSON.stringify(results,null,2));
	console.log(JSON.stringify(results));
} finally {await browser.close();await server.close();}
