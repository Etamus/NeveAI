import fs from 'node:fs/promises';
import { chromium } from '../logs/ui-image-26/node_modules/playwright/index.mjs';

const output='logs/image-latency-20261114';
await fs.mkdir(output,{recursive:true});
const browser=await chromium.launch();
const page=await browser.newPage({viewport:{width:1440,height:1000}});
const errors=[];
page.on('pageerror',error=>errors.push(error.message));
try{
 await page.goto('http://127.0.0.1:8080',{waitUntil:'networkidle'});
 await page.evaluate(()=>{
  window.__frames=[];window.__tasks=[];window.__previous=performance.now();
  window.__observer=new PerformanceObserver(list=>{for(const entry of list.getEntries())window.__tasks.push({start:performance.timeOrigin+entry.startTime,duration:entry.duration});});
  window.__observer.observe({type:'longtask',buffered:false});
  function frame(now){const duration=now-window.__previous;if(duration>40)window.__frames.push({at:performance.timeOrigin+now,duration});window.__previous=now;window.__raf=requestAnimationFrame(frame);}
  window.__raf=requestAnimationFrame(frame);
 });
 const samples=[];
 const began=Date.now();
 while(Date.now()-began<600000){
  const start=performance.now();
  const status=await fetch('http://127.0.0.1:8080/health').then(r=>r.status).catch(()=>0);
  samples.push({at:Date.now(),healthStatus:status,healthMs:performance.now()-start});
  const measurements=await page.evaluate(()=>({frames:window.__frames,tasks:window.__tasks}));
  await fs.writeFile(output+'/browser-idle-during-gpu.json',JSON.stringify({began,samples,...measurements,errors},null,2));
  if(await fs.stat(output+'/image2-warm-result.json').then(()=>true,()=>false))break;
  await page.waitForTimeout(1000);
 }
 await page.screenshot({path:output+'/browser-during-gpu.png'});
 console.log('Browser monitoring finished',samples.length,'samples',errors);
}finally{await browser.close();}
