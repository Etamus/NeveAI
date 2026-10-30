import fs from 'node:fs/promises';
import {constants} from 'node:fs';
import assert from 'node:assert/strict';
import {createServer} from 'vite';
import {chromium} from '../logs/ui-image-26/node_modules/playwright/index.mjs';
import utils from '../logs/ui-image-26/node_modules/playwright-core/lib/utilsBundle.js';
const {PNG}=utils;
const dir=new URL('../src/routes/__fade_test/',import.meta.url),file=new URL('+page.svelte',dir);
await fs.mkdir(dir,{recursive:true});await fs.copyFile(new URL('./fixtures/text-fade.svelte',import.meta.url),file,constants.COPYFILE_EXCL);
let server,browser;
try{
 server=await createServer({plugins:process.env.FADE_BASELINE?[{name:'old-text-write',enforce:'pre',async load(id){if(id.endsWith('/MarkdownInlineTokens/TextToken.svelte'))return(await fs.readFile(id,'utf8')).replace("use:stableStreamingText={token?.raw ?? ''} ",'').replace('{initialText}</span>',"{token?.raw}</span>");}}]:[],server:{port:5188,strictPort:true,watch:{ignored:['**/logs/**']}}});await server.listen();browser=await chromium.launch();
 const page=await browser.newPage({viewport:{width:800,height:600}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
 // Vite may rebuild its dependency graph on the first isolated fixture bootstrap.
 await page.goto('http://localhost:5188/__fade_test',{waitUntil:'networkidle',timeout:90000});errors.length=0;
 await page.reload({waitUntil:'networkidle',timeout:90000});await page.waitForFunction(()=>window.__fadeProbe);await page.evaluate(()=>document.fonts.ready);
 await page.clock.install({time:new Date('2026-10-25T00:00:00Z')});await page.clock.pauseAt(new Date('2026-10-25T00:00:01Z'));
 const probe=page.locator('#probe');
 const ink=(buffer,light)=>{const p=PNG.sync.read(buffer);let sum=0;for(let i=0;i<p.data.length;i+=4)sum+=light?255-p.data[i]:p.data[i];return sum;};
 const metrics=[];
 for(const light of [false,true]){
  await probe.evaluate((el,light)=>{el.style.background=light?'white':'black';el.style.color=light?'black':'rgb(240,240,240)';},light);
  await page.evaluate(()=>window.__fadeProbe('Fading text',false));await page.clock.runFor(40);
  assert(await page.evaluate(()=>CSS.highlights.size>0));
  const partial=ink(await probe.screenshot({path:`logs/text-fade-${light?'light':'dark'}-partial.png`}),light);
  await page.clock.runFor(120);const complete=ink(await probe.screenshot({path:`logs/text-fade-${light?'light':'dark'}-complete.png`}),light);
  assert(partial>0&&partial<complete*0.85,JSON.stringify({light,partial,complete}));assert.equal(await page.evaluate(()=>CSS.highlights.size),0);
  await page.evaluate(()=>window.__fadeProbe('',true));await page.clock.runFor(1);metrics.push({light,partial,complete});
 }
 await page.evaluate(()=>window.__fadeProbe('First',false));await page.clock.runFor(25);
 const identity=await probe.evaluate(el=>{window.__probeText=el.querySelector('span').firstChild;return el.textContent;});assert(identity.includes('First'));
 await probe.evaluate(el=>{const name=[...CSS.highlights.keys()][0];window.__liveRangeEnds=[];window.__rangeObserver=new MutationObserver(()=>{const highlight=CSS.highlights.get(name);if(highlight)window.__liveRangeEnds.push([...highlight][0].endOffset);});window.__rangeObserver.observe(el,{characterData:true,subtree:true});});
 await page.evaluate(()=>window.__fadeProbe('First second',false));await page.clock.runFor(25);
 const liveRangeEnds=await page.evaluate(()=>window.__liveRangeEnds);assert(liveRangeEnds.length>0&&liveRangeEnds.every(end=>end===5),'An existing highlight collapsed during a text append: '+JSON.stringify(liveRangeEnds));await page.evaluate(()=>window.__rangeObserver.disconnect());
 assert(await probe.evaluate(el=>el.querySelector('span').firstChild===window.__probeText));assert.equal(await page.evaluate(()=>CSS.highlights.size),2);
 await page.evaluate(()=>window.__fadeProbe('First second',true));await page.clock.runFor(1);assert.equal(await page.evaluate(()=>CSS.highlights.size),0);
 await page.evaluate(()=>window.__fadeProbe('Unfinished',false));await page.clock.runFor(10);
 await page.evaluate(()=>window.__fadeProbe('',false,false));await page.clock.runFor(1);
 assert.equal(await page.evaluate(()=>CSS.highlights.size),0);
 assert.equal(await page.evaluate(()=>document.querySelector('style[data-streaming-text-fade]').sheet.cssRules.length),0);
 assert.deepEqual(errors,[]);console.log(JSON.stringify({metrics,append:true,identity:true,cleanup:true,errors}));
}finally{await browser?.close();await server?.close();await fs.unlink(file);await fs.rmdir(dir);}
