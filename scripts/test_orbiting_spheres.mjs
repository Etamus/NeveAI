import fs from 'node:fs/promises';
import path from 'node:path';
import {constants} from 'node:fs';
import {spawn} from 'node:child_process';
import assert from 'node:assert/strict';
import {createServer} from 'vite';
import {chromium} from '../logs/ui-image-26/node_modules/playwright/index.mjs';
import utils from '../logs/ui-image-26/node_modules/playwright-core/lib/utilsBundle.js';
const {PNG}=utils;
const dir=new URL('../src/routes/__orbit_test/',import.meta.url),file=new URL('+page.svelte',dir);
let server,browser,host;const results=[];
await fs.mkdir(dir,{recursive:true});await fs.copyFile(new URL('./fixtures/orbiting-spheres.svelte',import.meta.url),file,constants.COPYFILE_EXCL);
try{
 server=await createServer({server:{port:5188,strictPort:true,watch:{ignored:['**/logs/**','**/scripts/**','**/docs/**']}}});await server.listen();
 if(process.env.ORBIT_NATIVE){
  const state=JSON.parse(await fs.readFile('.desktop/installed.json','utf8'));
  host=spawn(path.resolve('.desktop',state.host),['--root',process.cwd(),'--runtime',path.resolve('.desktop',state.runtime),'--profile',path.resolve('logs/orbit-native/profile'),'--url','http://localhost:5188/__orbit_test'],{windowsHide:true,env:{...process.env,NEVE_WEBVIEW2_TEST_MODE:'1',NEVE_WEBVIEW2_DEBUG_PORT:'9233'}});
  for(let i=0;i<150;i++){try{browser=await chromium.connectOverCDP('http://127.0.0.1:9233');break;}catch{await new Promise(r=>setTimeout(r,200));}}
  assert(browser,'Native host did not start');
 }else browser=await chromium.launch();
 const page=process.env.ORBIT_NATIVE?browser.contexts()[0].pages()[0]:await browser.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
 if(!process.env.ORBIT_NATIVE)await page.goto('http://localhost:5188/__orbit_test',{waitUntil:'domcontentloaded',timeout:90000});
 await page.locator('.orbiting-spheres').first().waitFor({timeout:90000});
 if(process.env.ORBIT_PRODUCTION_CSS){
  const assets='build/_app/immutable/assets';let production;
  for(const name of await fs.readdir(assets))if(name.endsWith('.css')){
   const css=await fs.readFile(path.join(assets,name),'utf8');
   if(css.includes('.orbiting-spheres.')){production={name,css};break;}
  }
  assert(production,'Production loader CSS missing');
  const hash=production.css.match(/\.orbiting-spheres\.(svelte-[\w]+)/)?.[1];assert(hash);
  await page.evaluate(({css,hash})=>{
   for(const sheet of document.styleSheets)try{if([...sheet.cssRules].some(r=>r.cssText.includes('.orbiting-spheres.')))sheet.disabled=true;}catch{}
   for(const root of document.querySelectorAll('.orbiting-spheres'))for(const e of [root,...root.querySelectorAll('*')]){
    for(const c of [...e.classList])if(c.startsWith('svelte-'))e.classList.remove(c);e.classList.add(hash);
   }
   const style=document.createElement('style');style.textContent=css;document.head.appendChild(style);
  },{css:production.css,hash});
  console.log('Production CSS',production.name,hash);
 }
 console.log('OS preference',await page.evaluate(()=>matchMedia('(prefers-reduced-motion: reduce)').matches));
 for(const reducedMotion of ['no-preference','reduce'])for(const dark of [false,true]){
  await page.emulateMedia({reducedMotion});await page.evaluate(dark=>document.documentElement.classList.toggle('dark',dark),dark);
  for(const id of ['orbit-normal','orbit-compact']){
   const loader=page.locator('#'+id+' .orbiting-spheres');
   const read=()=>loader.evaluate(e=>[...e.querySelectorAll('*')].flatMap(n=>n.getAnimations()).map(a=>({state:a.playState,time:a.currentTime,duration:a.effect.getTiming().duration,delay:a.effect.getTiming().delay})));
   const before=await read(),a=PNG.sync.read(await loader.screenshot());await page.waitForTimeout(220);const b=PNG.sync.read(await loader.screenshot({path:`logs/orbit-${process.env.ORBIT_NATIVE?'native':'browser'}-${reducedMotion}-${dark?'dark':'light'}-${id}.png`})),after=await read();
   let pixels=0;for(let i=0;i<a.data.length;i+=4)if(a.data[i]!==b.data[i]||a.data[i+1]!==b.data[i+1]||a.data[i+2]!==b.data[i+2])pixels++;
   const paused=process.env.ORBIT_BASELINE&&reducedMotion==='reduce';
   assert.deepEqual(after.map(a=>a.duration),[2500,1500,1500]);assert.equal(after[2].delay,-750);
   assert(after.every(a=>a.state===(paused?'paused':'running')));
   if(paused)assert.equal(pixels,0);else {assert(pixels>0,'Rendered loader did not move');assert(after.every((a,i)=>a.time>before[i].time),'Animation timeline did not advance');}
   results.push({reducedMotion,dark,id,pixels,before,after});
  }
 }
 assert.deepEqual(errors,[]);await fs.writeFile(`logs/orbit-${process.env.ORBIT_PRODUCTION_CSS?'production':process.env.ORBIT_BASELINE?'before':process.env.ORBIT_NATIVE?'native-after':'after'}.json`,JSON.stringify(results,null,2));console.log('PASS',results.length,'animation/pixel cases',errors);
}finally{await browser?.close();host?.kill();await server?.close();await fs.unlink(file);await fs.rmdir(dir);}
