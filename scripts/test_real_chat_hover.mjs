import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {spawn,execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {createServer} from 'vite';
import {chromium} from '../logs/ui-image-26/node_modules/playwright/index.mjs';
import utils from '../logs/ui-image-26/node_modules/playwright-core/lib/utilsBundle.js';
const {PNG}=utils;
const execute=promisify(execFile);
const physical=async(mode,point)=>execute('powershell.exe',['-NoProfile','-ExecutionPolicy','Bypass','-File','scripts/capture_test_window.ps1','-WindowProcessId',String(host.pid),'-OutputPath',path.resolve(`logs/physical-${mode}-${point}.png`)],{windowsHide:true});
const server=await createServer({server:{port:5188,strictPort:true,watch:{ignored:['**/logs/**','**/scripts/**','**/docs/**']}}});
await server.listen();
const state=JSON.parse(await fs.readFile('.desktop/installed.json','utf8'));
const origin=process.env.HOVER_PRODUCTION?'http://localhost:8080':'http://localhost:5188';
const host=spawn(path.resolve('.desktop',state.host),['--root',process.cwd(),'--runtime',path.resolve('.desktop',state.runtime),'--profile',path.resolve('logs/real-hover/profile'),'--url',origin+'/c/a0bf5564-5162-457b-af95-65c6d789ebaf'],{windowsHide:true,env:{...process.env,NEVE_WEBVIEW2_TEST_MODE:'1',NEVE_WEBVIEW2_DEBUG_PORT:'9231'}});
let browser;
let native;
const input=command=>native.stdin.write(JSON.stringify(command)+'\n');
const results=[];
try{
 for(let i=0;i<150;i++){try{browser=await chromium.connectOverCDP('http://127.0.0.1:9231');break;}catch{await new Promise(r=>setTimeout(r,200));}}
 assert(browser);
 const page=browser.contexts()[0].pages()[0];page.setDefaultTimeout(60000);
 if(!process.env.HOVER_PHYSICAL)await page.setViewportSize({width:1440,height:1000});
 await page.route('**/api/chat/completions',r=>r.abort());
 await page.route('**/api/v1/chats/**',async r=>{
  if(r.request().method()!=='GET')return r.abort();
  if(process.env.HOVER_SNAPSHOT&&new URL(r.request().url()).pathname==='/api/v1/chats/a0bf5564-5162-457b-af95-65c6d789ebaf'){
   const response=await r.fetch(),data=await response.json();const currentId='38278da3-657e-4153-b784-bf429899a50b';
   assert(data.chat.history.messages[currentId],'Recorded response no longer exists');
   const selected={};let id=currentId;while(id){const m=data.chat.history.messages[id];selected[id]=m;id=m.parentId;}
   data.chat.history={currentId,messages:selected};data.chat.messages=Object.values(selected).reverse();
   return r.fulfill({response,json:data});
  }
  return r.continue();
 });
 await page.locator('#messages-container .markdown-table').last().waitFor();await page.evaluate(()=>document.fonts.ready);
 if(process.env.HOVER_RELOAD){await page.reload({waitUntil:'domcontentloaded'});await page.locator('#messages-container .markdown-table').last().waitFor();await page.evaluate(()=>document.fonts.ready);await page.waitForTimeout(1000);}
 await page.evaluate(()=>document.documentElement.classList.add('dark'));
 if(process.env.HOVER_LAYER){
  const mode=process.env.HOVER_LAYER;
  const selector={viewport:'#messages-container',content:'[data-messages-content]',response:'.chat-assistant',table:'.markdown-table > table'}[mode];
  const variants={separate:'.markdown-table table{border-collapse:separate;border-spacing:0;}', 'no-clip':'#messages-container{clip-path:none !important;}', isolation:'[data-messages-content]{isolation:isolate;}',paint:'#messages-container{contain:paint;}',leaf:'.markdown-table td>div{transform:translateZ(0);}',antialias:'#messages-container{-webkit-font-smoothing:antialiased;text-rendering:geometricPrecision;}'};
  const content=variants[mode]??`${selector}{transform:translateZ(0);}`;
  await page.addStyleTag({content});
 }
 const viewport=page.locator('#messages-container');
 if(process.env.HOVER_NATIVE_INPUT){
  native=spawn('powershell.exe',['-NoProfile','-ExecutionPolicy','Bypass','-File','scripts/native_hover_input.ps1','-WindowProcessId',String(host.pid)],{windowsHide:true});
  await new Promise((resolve,reject)=>{native.stdout.on('data',b=>{if(String(b).includes('READY'))resolve();});native.stderr.on('data',b=>console.error(String(b)));native.on('exit',c=>{if(c)reject(Error('Native input failed'));});});
 }
 for(const mode of process.env.HOVER_BURST?['cross-hover']:['baseline','cross-hover','reload-cross-hover']){
  if(mode.startsWith('reload')){await page.reload({waitUntil:'domcontentloaded'});await page.locator('#messages-container .markdown-table').last().waitFor();await page.waitForTimeout(1500);await page.evaluate(()=>document.documentElement.classList.add('dark'));}
  await viewport.hover();await page.mouse.wheel(0,100000);await page.waitForTimeout(800);
  if(mode!=='baseline'){
   if(process.env.HOVER_BURST){
    await page.locator('#message-62eafa03-421e-4eb6-9334-9d39adda30ba .markdown-table').scrollIntoViewIfNeeded();
    const tableBox=await viewport.locator('.markdown-table').last().boundingBox(),area=await viewport.boundingBox();
    if(native)input({type:'move',x:tableBox.x+tableBox.width*0.55,y:area.y+area.height*0.4});
    else await page.mouse.move(tableBox.x+tableBox.width*0.55,area.y+area.height*0.4);
    for(let i=0;i<(native?32:18);i++){if(native)input({type:'wheel',delta:-480});else await page.mouse.wheel(0,800);await page.waitForTimeout(40);}
    await page.waitForTimeout(100);
   }else{
   for(let i=0;i<32;i++){
    const box=await viewport.boundingBox();await page.mouse.move(box.x+box.width*(i%2?0.35:0.65),box.y+box.height*(i%3?0.45:0.65));
    await page.mouse.wheel(0,-330);await page.waitForTimeout(60);
   }
   for(let i=0;i<34;i++){await page.mouse.wheel(0,390);await page.waitForTimeout(60);}
   const edge=await viewport.boundingBox();await page.mouse.move(edge.x+12,edge.y+edge.height/2);await page.mouse.wheel(0,100000);await page.waitForTimeout(800);
   }
  }
  const table=viewport.locator('.markdown-table').last();await table.waitFor();
  if(!process.env.HOVER_BURST){await page.mouse.move(2,2);await page.waitForTimeout(200);}
  const rect=await table.boundingBox();const clip={x:Math.floor(rect.x),y:Math.max(0,Math.floor(rect.y)),width:Math.ceil(rect.width),height:Math.min(Math.ceil(rect.height),Math.floor((await page.evaluate(()=>innerHeight))-Math.max(0,Math.floor(rect.y))))};
  const read=()=>table.evaluate(el=>{const r=el.getBoundingClientRect(),v=document.querySelector('#messages-container');return{x:r.x,y:r.y,w:r.width,h:r.height,scroll:v.scrollTop,total:v.scrollHeight,classes:v.className,thumb:getComputedStyle(v,'::-webkit-scrollbar-thumb').visibility};});
  const before=await read();
  if(process.env.HOVER_BURST){
   const prefix=path.resolve('logs/hover-burst-'+(process.env.HOVER_RESULT??((process.env.HOVER_NATIVE_INPUT?'native-':'')+(process.env.HOVER_LAYER?process.env.HOVER_LAYER+'-':'')+(process.env.HOVER_NO_TRANSITION?'no-transition':'baseline'))));
   if(process.env.HOVER_EXPECT_FIXED){assert.equal(before.thumb,'visible');assert.equal(await viewport.evaluate(el=>getComputedStyle(el).contain),'paint');}
   if(process.env.HOVER_NO_TRANSITION)await page.addStyleTag({content:'#messages-container * {transition-property: none !important;}'});
   const dpr=await page.evaluate(()=>devicePixelRatio);
   await table.evaluate(el=>{
    window.__burstGeometry=[];const end=performance.now()+10000;
    const sample=()=>{const r=el.getBoundingClientRect(),v=document.querySelector('#messages-container');window.__burstGeometry.push({time:performance.now(),y:r.y,scroll:v.scrollTop,rows:[...el.querySelectorAll('tbody tr')].map(r=>r.getBoundingClientRect().y)});if(performance.now()<end)requestAnimationFrame(sample);};sample();
   });
   const capture=spawn('powershell.exe',['-NoProfile','-ExecutionPolicy','Bypass','-File','scripts/capture_test_window.ps1','-WindowProcessId',String(host.pid),'-OutputPath',prefix,'-Count','150','-X',String(Math.round(rect.x*dpr)),'-Y',String(Math.round(rect.y*dpr)),'-Width',String(Math.round(rect.width*dpr)),'-Height',String(Math.round(rect.height*dpr))],{windowsHide:true});
   await new Promise((resolve,reject)=>{capture.stdout.on('data',b=>{if(String(b).includes('READY'))resolve();});capture.on('exit',code=>{if(code)reject(Error('Capture failed '+code));});capture.stderr.on('data',b=>console.error(String(b)));});
   await page.waitForTimeout(250);
   for(let i=0;i<24;i++){const x=rect.x+rect.width*0.5,y=rect.y+rect.height*(i%2?0.57:0.38);if(native)input({type:'move',x,y});else await page.mouse.move(x,y);await page.waitForTimeout(65);}
   await new Promise(resolve=>capture.on('exit',resolve));
   await fs.writeFile(prefix+'-geometry.json',JSON.stringify(await page.evaluate(()=>window.__burstGeometry),null,2));
   console.log('BURST',prefix,rect,dpr);break;
  }
  const base=PNG.sync.read(await page.screenshot({clip,path:`logs/real-hover-${mode}-before.png`}));const samples=[];
  if(!process.env.HOVER_PRODUCTION)assert.equal(before.thumb,'visible','Chat scrollbar disappeared while mouse was outside');
  if(process.env.HOVER_PHYSICAL)await physical(mode,'before');
  for(const [x,y] of [[0.1,0.1],[0.8,0.2],[0.2,0.7],[0.85,0.85],[0.5,0.5]]){
   await page.mouse.move(rect.x+rect.width*x,clip.y+clip.height*y);await page.waitForTimeout(100);
   if(process.env.HOVER_PHYSICAL)await physical(mode,`${x}-${y}`);
   const after=await read();const shot=PNG.sync.read(await page.screenshot({clip,path:`logs/real-hover-${mode}-${x}-${y}.png`}));
   if(!process.env.HOVER_PRODUCTION)assert.equal(after.thumb,'visible');
   for(const key of ['x','y','w','h','scroll','total'])assert.equal(after[key],before[key],`Hover changed ${key}`);
   let changed=0,brightChanged=0;for(let i=0;i<base.data.length;i+=4){if(base.data[i]!==shot.data[i]||base.data[i+1]!==shot.data[i+1]||base.data[i+2]!==shot.data[i+2]){changed++;if(Math.min(...base.data.subarray(i,i+3))>180||Math.min(...shot.data.subarray(i,i+3))>180)brightChanged++;}}
   samples.push({after,changed,brightChanged});
  }
  results.push({mode,before,samples});console.log(JSON.stringify(results.at(-1)));
 }
 await fs.writeFile('logs/real-hover-results.json',JSON.stringify(results,null,2));
}finally{if(native&&native.exitCode===null){input({type:'quit'});native.stdin.end();await new Promise(r=>native.on('exit',r));}await browser?.close();host.kill();await server.close();}
