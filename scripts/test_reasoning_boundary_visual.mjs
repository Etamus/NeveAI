import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {constants} from 'node:fs';
import {createServer} from 'vite';
import {chromium} from '../logs/ui-image-26/node_modules/playwright/index.mjs';

const dir=new URL('../src/routes/__reasoning_boundary/',import.meta.url),file=new URL('+page.svelte',dir);
const captured=JSON.parse(await fs.readFile(process.env.BOUNDARY_LANDING?'logs/landing-investigation/live-clean.json':'logs/reasoning-boundary-live-before.json','utf8'));
const distinct=[...new Map(captured.frames.filter(frame=>process.env.BOUNDARY_LANDING||frame.leaked).map(frame=>[frame.content,frame])).values()];
assert(distinct.length>0,'No captured failing stream');
const samples=distinct.filter((_,index)=>index%4===0);samples.push(distinct.at(-1),{...captured.after,done:true});
let server,browser;const results=[];
await fs.mkdir(dir,{recursive:true});await fs.copyFile(new URL('./fixtures/streaming-tools.svelte',import.meta.url),file,constants.COPYFILE_EXCL);
try{
 server=await createServer({server:{port:5188,strictPort:true,watch:{ignored:['**/logs/**','**/scripts/**','**/docs/**']}}});await server.listen();browser=await chromium.launch();
 for(const viewport of [{width:1440,height:1000},{width:390,height:844}])for(const dark of [false,true]){
  const page=await browser.newPage({viewport});const errors=[];page.on('pageerror',error=>errors.push(error.message));
  await page.route('**/api/chat/completions',route=>route.abort());
  await page.route('**/__tool_embed',route=>route.fulfill({contentType:'text/html',body:'<!doctype html><html><body>Embedded output</body></html>'}));
  await page.goto('http://localhost:5188/__reasoning_boundary',{waitUntil:'networkidle',timeout:90000});await page.waitForFunction(()=>window.__streamingToolsReady);await page.evaluate(dark=>document.documentElement.classList.toggle('dark',dark),dark);
  const send=async detail=>{await page.evaluate(detail=>window.dispatchEvent(new CustomEvent('neve-test-stream',{detail})),detail);await page.waitForTimeout(100);};
  await send({content:captured.before.content,done:true});
  const outside=()=>page.locator('#stream').evaluate(root=>{const copy=root.cloneNode(true);copy.querySelectorAll('.reasoning-text').forEach(node=>node.remove());return copy.textContent;});
  const completed=await outside();await send({content:captured.before.content,done:false});assert.equal(await outside(),completed,'Continue rewrote the previous response before receiving new text');
  for(const frame of samples){
   await page.evaluate(detail=>window.dispatchEvent(new CustomEvent('neve-test-stream',{detail})),{content:frame.content,done:frame.done});await page.waitForTimeout(100);
   const state=await page.locator('#stream').evaluate(root=>{const clone=root.cloneNode(true);clone.querySelectorAll('.reasoning-text').forEach(node=>node.remove());return{blocks:root.querySelectorAll('.reasoning-text').length,outside:clone.textContent};});
   const expected=(frame.content.match(/<details type="reasoning"/g)??[]).length;
   assert.equal(state.blocks,expected,'Reasoning did not render as a block');assert(!/<details\b|<summary>|&gt;|Thinking Process:/.test(state.outside),'Captured private thought leaked outside the blocks');
   results.push({width:viewport.width,dark,done:frame.done,blocks:state.blocks,leaked:false});
  }
  await page.screenshot({path:'logs/reasoning-boundary-'+viewport.width+'-'+(dark?'dark':'light')+'.png'});assert.deepEqual(errors,[]);await page.close();
 }
 await fs.writeFile(process.env.BOUNDARY_LANDING?'logs/landing-investigation/boundary-visual.json':'logs/reasoning-boundary-visual.json',JSON.stringify(results,null,2));console.log('PASS '+results.length+' captured streaming states across desktop/mobile and light/dark');
}finally{await browser?.close();await server?.close();await fs.unlink(file);await fs.rmdir(dir);}
