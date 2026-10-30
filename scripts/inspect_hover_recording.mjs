import fs from 'node:fs/promises';
import {chromium} from '../logs/ui-image-26/node_modules/playwright/index.mjs';
const data=await fs.readFile('C:/Users/Administrador/Desktop/gravacao.mp4');
const browser=await chromium.launch({executablePath:'C:/Program Files/BraveSoftware/Brave-Browser/Application/brave.exe'});
try{
 const page=await browser.newPage();
 await page.route('http://capture.local/**',r=>r.request().url().endsWith('video.mp4')?r.fulfill({body:data,contentType:'video/mp4'}):r.fulfill({contentType:'text/html',body:'<video id="video" src="/video.mp4" muted preload="auto"></video><canvas id="canvas"></canvas>'}));
 await page.goto('http://capture.local/');
 await page.waitForFunction(()=>document.querySelector('video').readyState>=2);
 const info=await page.evaluate(()=>{const v=document.querySelector('video');return{duration:v.duration,width:v.videoWidth,height:v.videoHeight};});console.log(info);
 const frames=await page.evaluate(()=>new Promise(async(resolve,reject)=>{
  const v=document.querySelector('video'),c=document.querySelector('canvas');c.width=v.videoWidth;c.height=v.videoHeight;
  const frames=[];let last=-1;
  const capture=(now,meta)=>{if(meta.mediaTime-last>=0.09){c.getContext('2d').drawImage(v,0,0);frames.push({time:meta.mediaTime,data:c.toDataURL('image/png').split(',')[1]});last=meta.mediaTime;}if(!v.ended)v.requestVideoFrameCallback(capture);};
  v.onended=()=>resolve(frames);v.requestVideoFrameCallback(capture);try{await v.play();}catch(e){reject(String(e));}
 }));
 for(const frame of frames)await fs.writeFile(`logs/recording-live-${frame.time.toFixed(3)}.png`,Buffer.from(frame.data,'base64'));
 console.log(frames.map(f=>f.time));
}finally{await browser.close();}
