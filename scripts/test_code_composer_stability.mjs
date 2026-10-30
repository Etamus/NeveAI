import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import { constants } from 'node:fs';
import { createServer } from 'vite';
import { chromium } from '../logs/ui-image-26/node_modules/playwright/index.mjs';

const dir = new URL('../src/routes/__visual_test/',import.meta.url);
const file = new URL('+page.svelte',dir);
await fs.mkdir(dir,{recursive:true});
await fs.copyFile(new URL('./fixtures/code-reasoning.svelte',import.meta.url),file,constants.COPYFILE_EXCL);
let server,browser;
const results = [];
const baseline = process.env.BASELINE === '1';
try {
	server = await createServer({server:{port:5188,strictPort:true,watch:{ignored:['**/logs/**']}}});
	await server.listen();
	browser = await chromium.launch({ignoreDefaultArgs:['--hide-scrollbars']});
	for(const [name,viewport] of [['desktop',{width:1440,height:1000}],['narrow',{width:900,height:800}],['mobile',{width:390,height:844}]]) {
		const page = await browser.newPage({viewport});
		page.setDefaultTimeout(12000);
		const errors=[];
		page.on('pageerror',e=>errors.push(e.message));
		await page.goto('http://localhost:5188/__visual_test',{waitUntil:'networkidle'});
		await page.locator('.code-scroll').first().waitFor();
		await page.evaluate(()=>document.fonts.ready);
		if(!baseline) await page.evaluate(()=>{
			window.outerCodeWheelEvents=0;
			document.querySelector('#fixture-scroll').addEventListener('wheel',event=>{
				window.outerCodeWheelEvents++;
				event.preventDefault();
			},{passive:false});
		});
		const blocks=[];
		for(const selector of ['.code-scroll','#code-textarea-fixture-edit .cm-scroller','#code-textarea-fixture-long-edit .cm-scroller']) {
			const el=page.locator(selector).first();
			await el.scrollIntoViewIfNeeded();
			await el.hover();
			const samples=[];
			for(const target of [0,0.5,1]) {
				await el.evaluate((e,f)=>e.scrollTop=(e.scrollHeight-e.clientHeight)*f,target);
				await page.waitForTimeout(150);
				for(let i=0;i<6;i++) {
					await page.mouse.wheel(0,1000);
					await page.waitForTimeout(80);
					samples.push(await el.evaluate(e=>({top:e.scrollTop,height:e.clientHeight,total:e.scrollHeight,bottom:e.getBoundingClientRect().bottom,contentBottom:(e.querySelector('.cm-content')??e.querySelector('code')).getBoundingClientRect().bottom,outer:document.querySelector('#fixture-scroll').scrollTop})));
				}
			}
			const tail=samples.slice(-5);
			const drift=Math.max(...tail.map(s=>s.contentBottom))-Math.min(...tail.map(s=>s.contentBottom));
			const nudges=[];
			for(let i=0;i<5;i++) {
				await page.mouse.wheel(0,-1);
				await page.waitForTimeout(32);
				await page.mouse.wheel(0,1);
				await page.waitForTimeout(32);
				nudges.push(await el.evaluate(e=>({top:e.scrollTop,total:e.scrollHeight,contentBottom:(e.querySelector('.cm-content')??e.querySelector('code')).getBoundingClientRect().bottom,outer:document.querySelector('#fixture-scroll').scrollTop})));
			}
			blocks.push({selector,drift,samples,nudges});
			if(!baseline) {
				assert(drift<=0.5,`${name} ${selector}: bottom drift ${drift}`);
				assert.equal(await page.evaluate(()=>window.outerCodeWheelEvents),0,'Code wheel reached the chat handler');
				assert(samples[0].top>0,'Native internal scrolling was blocked');
				for(const n of nudges) {
					assert(Math.abs(n.contentBottom-tail.at(-1).contentBottom)<=0.5,`${name} ${selector}: 1px wheel nudge changed the bottom`);
					assert.equal(n.outer,tail.at(-1).outer,'Nudge moved the chat viewport');
				}
			}
		}
		if(!baseline) {
			const wideIndex=await page.locator('.code-scroll').evaluateAll(els=>els.findIndex(e=>e.scrollWidth>e.clientWidth&&e.scrollHeight<=e.clientHeight));
			assert(wideIndex>=0,'Expected a horizontally scrollable short codeblock');
			const wide=page.locator('.code-scroll').nth(wideIndex);
			await wide.scrollIntoViewIfNeeded();
			const propagation=await wide.evaluate(el=>{
				window.outerCodeWheelEvents=0;
				el.dispatchEvent(new WheelEvent('wheel',{bubbles:true,cancelable:true,deltaY:100}));
				const vertical=window.outerCodeWheelEvents;
				window.outerCodeWheelEvents=0;
				el.dispatchEvent(new WheelEvent('wheel',{bubbles:true,cancelable:true,deltaX:100}));
				return {vertical,horizontal:window.outerCodeWheelEvents};
			});
			assert.deepEqual(propagation,{vertical:1,horizontal:0});
		}
		await page.goto('http://localhost:5188',{waitUntil:'networkidle'});
		await page.locator('#message-input-container').waitFor();
		const geometry=()=>page.evaluate(()=>{
			const root=document.querySelector('#message-input-container'),r=root.getBoundingClientRect();
			return {height:r.height,compact:root.classList.contains('flex-row'),controls:Object.fromEntries(['#input-menu-button','#send-message-button','#thinking-dropdown-container > button','[data-token-usage-trigger]'].map(s=>{const e=root.querySelector(s),b=e?.getBoundingClientRect();return [s,b?{right:r.right-b.right,bottom:r.bottom-b.bottom,width:b.width,height:b.height}:null]}))};
		});
		const newCompact=await geometry();
		await page.locator('#chat-input').fill('First line\nSecond line');
		await page.waitForTimeout(350);
		const newExpanded=await geometry();
		if(!baseline) for(const [s,b] of Object.entries(newCompact.controls)) if(b&&newExpanded.controls[s]) {
			assert(Math.abs(newExpanded.controls[s].right-b.right)<=0.5,`${name}: new chat horizontal drift`);
			assert(Math.abs(newExpanded.controls[s].bottom-b.bottom)<=0.5,`${name}: new chat vertical drift`);
		}
		await page.locator('#chat-input').fill('');
		await page.waitForTimeout(350);
		const chats=await page.evaluate(async()=>{
			const response=await fetch('/api/v1/chats/?page=1',{headers:{authorization:`Bearer ${localStorage.token}`}});
			const list=await response.json();return list.map(({id,title})=>({id,title}));
		});
		const codeChat=chats.find(chat=>chat.title?.toLowerCase().includes('python'));
		if(codeChat) {
			await page.goto(`http://localhost:5188/c/${codeChat.id}`,{waitUntil:'networkidle'});
			await page.locator('#message-input-container').waitFor();
		}
		const codeIndex=await page.locator('.code-scroll').evaluateAll(els=>els.findIndex(e=>e.scrollHeight>e.clientHeight));
		const realCode=page.locator('.code-scroll').nth(Math.max(0,codeIndex));
		let chatCode=null;
		if(await realCode.count()) {
			await realCode.scrollIntoViewIfNeeded();
			await realCode.evaluate(el=>el.scrollTop=0);
			await realCode.hover();
			await page.mouse.wheel(0,150);
			await page.waitForTimeout(350);
			chatCode=await realCode.evaluate(el=>({top:el.scrollTop,total:el.scrollHeight,height:el.clientHeight}));
		}
		const compact=await geometry();
		await page.screenshot({path:`logs/composer-${name}-${baseline?'before':'after'}-compact.png`});
		await page.locator('#chat-input').fill('First line\nSecond line');
		await page.waitForTimeout(700);
		const expanded=await geometry();
		await page.screenshot({path:`logs/composer-${name}-${baseline?'before':'after'}-expanded.png`});
		const deltas=Object.fromEntries(Object.keys(compact.controls).map(s=>[s,compact.controls[s]&&expanded.controls[s]?{x:expanded.controls[s].right-compact.controls[s].right,y:expanded.controls[s].bottom-compact.controls[s].bottom}:null]));
		await page.locator('#chat-input').fill(Array.from({length:40},(_,i)=>`Line ${i}`).join('\n'));
		await page.waitForTimeout(350);
		const tall=await geometry();
		await page.locator('#chat-input-container').hover();
		await page.mouse.wheel(0,2000);
		await page.waitForTimeout(150);
		const tallScrolled=await geometry();
		const scrollbar=await page.locator('#chat-input-container').evaluate(el=>({width:getComputedStyle(el,'::-webkit-scrollbar').width,thumb:getComputedStyle(el,'::-webkit-scrollbar-thumb').backgroundColor}));
		await page.locator('#chat-input').fill('');
		await page.waitForTimeout(350);
		const retracted=await geometry();
		results.push({name,blocks,chatCode,newCompact,newExpanded,compact,expanded,tall,tallScrolled,retracted,scrollbar,deltas,errors});
		if(!baseline) {
			for(const [s,d] of Object.entries(deltas)) if(d) assert(Math.abs(d.x)<=0.5&&Math.abs(d.y)<=0.5,`${name} ${s}: ${JSON.stringify(d)}`);
			for(const state of [tall,tallScrolled,retracted]) for(const [s,b] of Object.entries(compact.controls)) if(b&&state.controls[s]) {
				assert(Math.abs(state.controls[s].right-b.right)<=0.5,`${name} ${s}: horizontal drift with tall input`);
				assert(Math.abs(state.controls[s].bottom-b.bottom)<=0.5,`${name} ${s}: vertical drift with tall input`);
			}
			assert.deepEqual(errors,[]);
		}
		await page.evaluate(()=>document.documentElement.classList.add('dark'));
		const navbarFade=await page.locator('#navbar-bg-gradient-to-b').evaluate(el=>getComputedStyle(el).backgroundImage);
		assert(!navbarFade.includes('255'),`Dark navbar contains white: ${navbarFade}`);
		await page.screenshot({path:`logs/navbar-tools-${name}-dark.png`});
		await page.close();
	}
	await fs.writeFile(`logs/code-composer-${baseline?'before':'after'}.json`,JSON.stringify(results,null,2));
	console.log(JSON.stringify(results.map(({name,deltas,blocks})=>({name,deltas,blocks:blocks.map(({selector,drift})=>({selector,drift}))}))));
} finally {await browser?.close();await server?.close();await fs.unlink(file);await fs.rmdir(dir);}
