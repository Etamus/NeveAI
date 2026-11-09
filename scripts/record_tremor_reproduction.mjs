// Interactive, isolated reproduction. No saved chats or user preference writes.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {spawn} from 'node:child_process';
import {chromium} from '../logs/ui-image-26/node_modules/playwright/index.mjs';

const root=process.cwd(),output=path.resolve('logs/tremor-repro');
await fs.mkdir(output,{recursive:true});
const installed=JSON.parse(await fs.readFile('.desktop/installed.json','utf8'));
const host=spawn(path.resolve('.desktop',installed.host),['--root',root,'--runtime',path.resolve('.desktop',installed.runtime),'--profile',path.join(output,'profile'),'--url','http://localhost:8080/?temporary-chat=true'],{windowsHide:true,env:{...process.env,NEVE_WEBVIEW2_TEST_MODE:'1',NEVE_WEBVIEW2_DEBUG_PORT:'9236'}});
let browser,capture;
const tasks=new Set();let startCapture;
const captured=new Promise(resolve=>{startCapture=resolve;});
try{
 for(let i=0;i<100;i++){try{browser=await chromium.connectOverCDP('http://127.0.0.1:9236');break;}catch{await new Promise(r=>setTimeout(r,200));}}
 assert(browser,'Diagnostic window did not start');
 const page=browser.contexts()[0].pages()[0];
 page.on('response',async response=>{if(response.url().endsWith('/api/chat/completions')){try{const data=await response.json();if(data.task_id)tasks.add(data.task_id);}catch{}}});
 await page.waitForURL('http://localhost:8080/?temporary-chat=true',{waitUntil:'domcontentloaded',timeout:60000});
 await page.locator('#chat-input').waitFor({timeout:60000});
 await page.evaluate(()=>document.documentElement.classList.add('dark'));
 await page.locator('#chat-input').fill('Conte uma historia longa.');
 const box=await page.locator('#chat-pane').boundingBox(),dpr=await page.evaluate(()=>devicePixelRatio);
 capture=spawn('powershell.exe',['-NoProfile','-ExecutionPolicy','Bypass','-File','scripts/capture_tremor_window.ps1','-WindowProcessId',String(host.pid),'-OutputDirectory',path.join(output,'frames'),'-X',String(Math.round((box.x+Math.max(0,(box.width-800)/2))*dpr)),'-Y',String(Math.round((box.y+90)*dpr)),'-Width','800','-Height','450','-Count','240'],{windowsHide:true});
 capture.stderr.on('data',data=>console.error(String(data)));
 await new Promise((resolve,reject)=>{capture.stdout.on('data',data=>{if(String(data).includes('READY'))resolve();});capture.on('exit',code=>{if(code)reject(Error('Capture setup failed'));});});
 await page.exposeFunction('__startTremorCapture',()=>{capture.stdin.write('START\n');startCapture();});
 await page.evaluate(()=>{
  window.__tremorTrace={frames:[],wheel:[],started:performance.now()};let active=false;
  document.addEventListener('wheel',event=>{
   window.__tremorTrace.wheel.push({at:performance.now(),x:event.clientX,y:event.clientY,dy:event.deltaY,dx:event.deltaX,mode:event.deltaMode,target:event.target?.className});
  },{passive:true,capture:true});
  const sample=()=>{
   const v=document.querySelector('#messages-container');
   if(v){
    const paragraphs=[...v.querySelectorAll('.chat-assistant p')].filter(p=>!p.closest('.reasoning-text'));
    window.__tremorTrace.frames.push({at:performance.now(),top:v.scrollTop,left:v.scrollLeft,max:v.scrollHeight-v.clientHeight,paragraphs:paragraphs.map(p=>({rect:p.getBoundingClientRect().toJSON(),text:p.textContent}))});
    if(!active&&paragraphs.some(p=>p.textContent.trim())){active=true;window.__startTremorCapture();}
   }
   window.__tremorRAF=requestAnimationFrame(sample);
  };sample();
 });
 console.log('READY: isolated window, click Send and reproduce the downward wheel gesture.');
 let deadline;
 try {await Promise.race([captured,new Promise((_,reject)=>{deadline=setTimeout(()=>reject(Error('No reproduction submitted within three minutes')),180000);})]);}
 finally {clearTimeout(deadline);}
 await new Promise((resolve,reject)=>{if(capture.exitCode!==null)return capture.exitCode?reject(Error('Capture failed')):resolve();capture.on('exit',code=>code?reject(Error('Capture failed: '+code)):resolve());});
 const trace=await page.evaluate(()=>{cancelAnimationFrame(window.__tremorRAF);return window.__tremorTrace;});
 await fs.writeFile(path.join(output,'trace.json'),JSON.stringify(trace,null,2));
 await page.screenshot({path:path.join(output,'final.png')});
 console.log('CAPTURED',trace.wheel.length,'wheel events',trace.frames.length,'layout frames');
}finally{
 if(browser){
  const context=browser.contexts()[0];
  for(const task of tasks)try{await context.request.post('http://localhost:8080/api/tasks/stop/'+task);}catch{}
 }
 if(capture&&capture.exitCode===null)capture.kill();
 await browser?.close();host.kill();
}
