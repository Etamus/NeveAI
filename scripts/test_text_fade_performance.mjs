import fs from 'node:fs/promises';
import {constants} from 'node:fs';
import assert from 'node:assert/strict';
import {createServer} from 'vite';
import {chromium} from '../logs/ui-image-26/node_modules/playwright/index.mjs';
const dir=new URL('../src/routes/__fade_perf/',import.meta.url),file=new URL('+page.svelte',dir);
await fs.mkdir(dir,{recursive:true});await fs.copyFile(new URL('./fixtures/text-fade.svelte',import.meta.url),file,constants.COPYFILE_EXCL);
let browser,server;
try{
 server=await createServer({server:{port:5188,strictPort:true,watch:{ignored:['**/logs/**']}}});await server.listen();browser=await chromium.launch();
 const page=await browser.newPage({viewport:{width:1000,height:800}});const errors=[];page.on('pageerror',e=>{errors.push(e.stack??e.message);console.log('pageerror',e.stack);});await page.goto('http://localhost:5188/__fade_perf',{waitUntil:'domcontentloaded',timeout:90000});await page.waitForFunction(()=>window.__fadeProbe);await page.evaluate(()=>document.fonts.ready);await page.waitForTimeout(1000);
 const result=await page.evaluate(async()=>{
  const probe=document.querySelector('#probe');Object.assign(probe.style,{width:'720px',height:'400px',overflow:'auto'});
  const longTasks=[],frames=[];const observer=new PerformanceObserver(list=>longTasks.push(...list.getEntries().map(e=>e.duration)));observer.observe({type:'longtask'});
  let active=true,last=performance.now();const sample=now=>{frames.push(now-last);last=now;if(active)requestAnimationFrame(sample);};requestAnimationFrame(sample);
  let text='';for(let i=0;i<40;i++){text+='Stable typography and unchanged text spacing. '.repeat(5);window.__fadeProbe(text,false);await new Promise(r=>setTimeout(r,64));probe.scrollTop=probe.scrollHeight;}
  const nodesDuring=probe.querySelectorAll('span').length;
  window.__fadeProbe(text,true);await new Promise(r=>setTimeout(r,180));active=false;observer.disconnect();frames.sort((a,b)=>a-b);
  return{characters:text.length,nodesDuring,nodesAfter:probe.querySelectorAll('span').length,frameP95:frames[Math.floor(frames.length*0.95)],longTasks,highlights:CSS.highlights?.size??0};
 });
 assert.deepEqual(errors,[]);assert.equal(result.highlights,0);assert.equal(result.nodesDuring,1);assert.equal(result.nodesAfter,1);
 await fs.writeFile('logs/text-fade-performance-after.json',JSON.stringify(result,null,2));console.log(JSON.stringify(result));
}finally{await browser?.close();await server?.close();await fs.unlink(file);await fs.rmdir(dir);}
