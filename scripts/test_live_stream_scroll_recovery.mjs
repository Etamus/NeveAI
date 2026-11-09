import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {spawn} from 'node:child_process';
import { chromium } from '../logs/ui-image-26/node_modules/playwright/index.mjs';

const base = 'http://localhost:8080';
let browser,host,native,capture;
if(process.env.LIVE_NATIVE){
 const installed=JSON.parse(await fs.readFile('.desktop/installed.json','utf8'));
 host=spawn(path.resolve('.desktop',installed.host),['--root',process.cwd(),'--runtime',path.resolve('.desktop',installed.runtime),'--profile',path.resolve('logs/first-native/profile'),'--url',base+'/?temporary-chat=true'],{windowsHide:true,env:{...process.env,NEVE_WEBVIEW2_TEST_MODE:'1',NEVE_WEBVIEW2_DEBUG_PORT:'9234'}});
 for(let i=0;i<150;i++){try{browser=await chromium.connectOverCDP('http://127.0.0.1:9234');break;}catch{await new Promise(r=>setTimeout(r,200));}}
 assert(browser,'Native test window did not start');
}else browser=await chromium.launch();
const results = [];
try {
 for (const width of process.env.LIVE_NATIVE?[1440]:[1440, 390]) {
  const page = process.env.LIVE_NATIVE?browser.contexts()[0].pages()[0]:await browser.newPage({viewport:{width,height:1000},deviceScaleFactor:Number(process.env.LIVE_DPR??1)});
  const ownTasks=new Set();
  page.on('response',async response=>{if(response.url().endsWith('/api/chat/completions')){try{const data=await response.json();if(data.task_id)ownTasks.add(data.task_id);}catch{}}});
  let chatId;
  const api = async (path, options) => {
   const response = await page.request.fetch(base + path, options);
   assert(response.ok(), `${path}: ${response.status()}`);
   return response.json();
  };
  try {
   assert.deepEqual((await api('/api/tasks')).tasks, []);
   const model = (await api('/llamacpp/models/loaded')).models[0].id;
   const history = process.env.LIVE_FIRST?{}:{
    prior: {id:'prior',role:'user',content:'Mostre uma tabela.',parentId:null,childrenIds:['previous'],done:true},
    previous: {id:'previous',role:'assistant',content:('| Item | Valor |\n| --- | --- |\n| A | 10 |\n\nTexto anterior.\n\n').repeat(20),parentId:'prior',childrenIds:[],done:true,model}
   };
   if(!process.env.LIVE_FIRST)chatId = (await api('/api/v1/chats/new',{method:'POST',data:{chat:{title:'Temporary live scroll recovery',models:[model],history:{currentId:'previous',messages:history},messages:Object.values(history),params:{reasoning_mode:'quick',no_think:true,max_tokens:1800}}}})).id;
   if(process.env.LIVE_FIRST)await page.route('**/api/chat/completions',route=>{
    const body=route.request().postDataJSON();
    return route.continue({postData:JSON.stringify({...body,params:{...body.params,max_tokens:process.env.LIVE_REASONING?6144:1800,...(process.env.LIVE_REASONING?{}:{reasoning_mode:'quick',no_think:true})}})});
   });
   await page.goto(process.env.LIVE_FIRST?`${base}/?temporary-chat=true`:`${base}/c/${chatId}`,{waitUntil:'networkidle'});
   if(process.env.LIVE_DARK)await page.evaluate(()=>document.documentElement.classList.add('dark'));
   const input = page.locator('#chat-input');
   await input.fill('Escreva uma historia longa em portugues sobre uma biblioteca. Use 20 paragrafos, listas e duas tabelas. Comece diretamente, sem introducao.');
   await page.locator('#send-message-button').click();
   await page.locator('#messages-container').waitFor();
   if(!process.env.LIVE_FIRST)await page.waitForFunction(()=>document.querySelectorAll('.chat-assistant p').length>22);
   await page.evaluate(()=>{
    window.__liveFrames=[];
    window.__sampleLive=true;
    const user=[...document.querySelectorAll('.chat-user-content')].at(-1);
    const sample=()=>{
     const viewport=document.querySelector('#messages-container');
     const paragraph=document.querySelector('.chat-assistant p');
     window.__liveFrames.push({at:performance.now(),top:viewport.scrollTop,max:viewport.scrollHeight-viewport.clientHeight,anchor:user?.isConnected?user.getBoundingClientRect().top+viewport.scrollTop:null,paragraph:paragraph?.getBoundingClientRect().toJSON(),text:paragraph?.textContent});
     if(window.__sampleLive)requestAnimationFrame(sample);
    };sample();
   });
   const box=await page.locator('#messages-container').boundingBox();
   await page.mouse.move(process.env.LIVE_CENTER?box.x+box.width/2:box.x+12,box.y+box.height*0.65);
   if(process.env.LIVE_NATIVE){
    await page.waitForFunction(()=>[...document.querySelectorAll('.chat-assistant p')].some(p=>p.textContent.length>60),null,{timeout:90000});
    const paragraph=await page.locator('.chat-assistant p').filter({hasText:/.{60}/}).first().boundingBox(),dpr=await page.evaluate(()=>devicePixelRatio);
    const prefix=process.env.LIVE_DARK?'logs/first-stream-dark-pixel':'logs/first-stream-pixel';
    capture=spawn('powershell.exe',['-NoProfile','-ExecutionPolicy','Bypass','-File','scripts/capture_test_window.ps1','-WindowProcessId',String(host.pid),'-OutputPath',path.resolve(prefix),'-Count','90','-X',String(Math.round(paragraph.x*dpr)),'-Y',String(Math.round(paragraph.y*dpr)),'-Width',String(Math.round(250*dpr)),'-Height',String(Math.round(22*dpr))],{windowsHide:true});
    await new Promise((resolve,reject)=>{capture.stdout.on('data',b=>{if(String(b).includes('READY'))resolve();});capture.on('exit',c=>{if(c)reject(Error('Physical capture failed'));});});
   }
   let inputError;
   if(process.env.LIVE_PHYSICAL){
    native=spawn('powershell.exe',['-NoProfile','-ExecutionPolicy','Bypass','-File','scripts/native_hover_input.ps1','-WindowProcessId',String(host.pid)],{windowsHide:true});
    native.stdin.on('error',error=>{inputError=error;});
    await new Promise((resolve,reject)=>{native.stdout.on('data',b=>{if(String(b).includes('READY'))resolve();});native.on('exit',code=>{if(code)reject(Error('Native input failed'));});});
    native.stdin.write(JSON.stringify({type:'move',x:box.x+box.width/2,y:box.y+box.height*0.65})+'\n');
   }
   for(let i=0;i<(process.env.LIVE_FIRST?900:160);i++){
    if(inputError)throw inputError;
    if(native)native.stdin.write('{"type":"wheel","delta":-120}\n');else await page.mouse.wheel(0,1400);
    await page.waitForTimeout(4);
   }
   if(native&&native.exitCode===null){native.stdin.write('{"type":"quit"}\n');native.stdin.end();await new Promise(resolve=>native.on('exit',resolve));}
   if(capture&&capture.exitCode===null)await new Promise(resolve=>capture.on('exit',resolve));
   for(let i=0;i<90;i++){
    if(!(await api('/api/tasks')).tasks.length)break;
    await page.waitForTimeout(1000);
   }
   assert.deepEqual((await api('/api/tasks')).tasks, [], 'Generation must finish');
   const frames=await page.evaluate(()=>{window.__sampleLive=false;return window.__liveFrames;});
   const backwards=frames.filter((frame,i)=>i&&frame.top<frames[i-1].top-0.5);
   const anchors=frames.map(f=>f.anchor).filter(n=>n!==null);
   const anchorRange=Math.max(...anchors)-Math.min(...anchors);
   results.push({width,backwardFrames:backwards.length,anchorRange,frames});
   await page.screenshot({path:`logs/recovery-live-scroll-${width}.png`});
   console.log(JSON.stringify({width,backwardFrames:backwards.length,anchorRange}));
  } finally {
   const active=(await api('/api/tasks')).tasks;
   for(const id of ownTasks)if(active.includes(id))await api('/api/tasks/stop/'+id,{method:'POST'});
   // Only this test's chat is eligible for cancellation and deletion.
   if(chatId){
    const tasks=(await api('/api/tasks')).tasks;
    assert.equal(tasks.length,0,'Do not delete a chat with a running test generation');
    await api(`/api/v1/chats/${chatId}`,{method:'DELETE'});
   }
   await page.close();
  }
 }
 await fs.writeFile(process.env.LIVE_FIRST?'logs/first-live-scroll.json':'logs/recovery-live-scroll.json',JSON.stringify(results,null,2));
} finally {if(native&&native.exitCode===null)native.kill();if(capture&&capture.exitCode===null)capture.kill();await browser.close();host?.kill();}
