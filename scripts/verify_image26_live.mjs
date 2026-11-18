import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {chromium} from '../logs/ui-image-26/node_modules/playwright/index.mjs';

const out='logs/image-latency-20261114';
const cancelAfter=Number(process.env.IMAGE26_CANCEL_AFTER||0);
const persistent=process.env.IMAGE26_PERSISTENT==='1';
const lightProbe=process.env.IMAGE26_LIGHT_PROBE==='1';
const profileOnly=process.env.IMAGE26_PROFILE_ONLY==='1';
const blobExperiment=process.env.IMAGE26_BLOB_EXPERIMENT==='1';
const fakeGeneration=process.env.IMAGE26_FAKE_GENERATION==='1';
const validatePreview=process.env.IMAGE26_VALIDATE_PREVIEW==='1';
const mobile=process.env.IMAGE26_MOBILE==='1';
const suffix=(persistent?'-saved':'')+(cancelAfter?'-profile':'')+(lightProbe?'-light':'')+(blobExperiment?'-blob':'')+(fakeGeneration?'-offline':'')+(mobile?'-mobile':'');
const browser=await chromium.launch();
const page=await browser.newPage({viewport:mobile?{width:390,height:844}:{width:1440,height:1000}});
const errors=[],requests=[],health=[];
page.on('pageerror',e=>errors.push(e.message));
page.on('request',r=>{if(r.url().includes('/api/chat/completions'))requests.push({at:Date.now(),payload:lightProbe||profileOnly?null:r.postDataJSON()});});
let timer;
const uploadedIds=[];
page.on('response',async r=>{if(r.request().method()==='POST' && new URL(r.url()).pathname==='/api/v1/files/'){
 const file=await r.json().catch(()=>null);if(file?.id)uploadedIds.push(file.id);
}});
try{
 await page.addInitScript(()=>{
  const original=window.fetch;
  window.fetch=function(input,options){if(String(input).includes('/api/chat/completions'))window.__requestBodyType=options?.body instanceof Blob?'Blob':typeof options?.body;return original.apply(this,arguments);};
 });
 if(fakeGeneration)await page.route('**/api/chat/completions',route=>route.fulfill({json:{task_id:'base64-ui-probe'}}));
 if(blobExperiment)await page.addInitScript(()=>{
  let blobUrl='';
  document.addEventListener('change',e=>{const file=e.target?.files?.[0];if(file?.type.startsWith('image/'))blobUrl=URL.createObjectURL(file);},true);
  const descriptor=Object.getOwnPropertyDescriptor(HTMLImageElement.prototype,'src');
  Object.defineProperty(HTMLImageElement.prototype,'src',{...descriptor,set(value){descriptor.set.call(this,blobUrl && String(value).startsWith('data:image/')?blobUrl:value);}});
  const setAttribute=HTMLImageElement.prototype.setAttribute;
  HTMLImageElement.prototype.setAttribute=function(name,value){return setAttribute.call(this,name,name==='src' && blobUrl && String(value).startsWith('data:image/')?blobUrl:value);};
 });
 await page.goto('http://127.0.0.1:8080/'+(persistent?'':'?temporary-chat=true'),{waitUntil:'networkidle'});
 if(!persistent)assert.match(await page.locator('body').innerText(),/Chat temporário/);
 await page.locator('#input-menu-button').click();
 await page.getByText('Criar imagem',{exact:true}).click();
 await page.locator('#image-quality-dropdown-container > button').click();
 await page.getByText('Neve Image 2.8',{exact:true}).click();
 console.log('SELECTED',await page.locator('#image-quality-dropdown-container').innerText());
 await page.locator('input[type=file]').nth(1).setInputFiles('backend/data/uploads/0e335168-40a8-473e-a233-1dd5f1cfb0c6_image.png');
 await page.waitForFunction(()=>[...document.querySelectorAll('#message-input-container img')].some(i=>i.complete && i.naturalWidth>0),null,{timeout:30000});
 await page.locator('#chat-input').fill('Faça ela sorrindo de boca aberta');
 await page.waitForTimeout(1500);
 await page.locator('#send-message-button').waitFor({state:'visible'});
 await page.evaluate(()=>{
  window.__gaps=[];window.__tasks=[];let previous=performance.now();
  window.__observer=new PerformanceObserver(list=>window.__tasks.push(...list.getEntries().map(e=>({at:e.startTime,duration:e.duration}))));
  window.__observer.observe({type:'longtask'});
  function frame(now){if(now-previous>40)window.__gaps.push({at:now,duration:now-previous});previous=now;window.__raf=requestAnimationFrame(frame);}
  window.__raf=requestAnimationFrame(frame);
 });
 const cdp=await page.context().newCDPSession(page);
 if(!lightProbe){await cdp.send('Profiler.enable');await cdp.send('Profiler.start');}
 const began=Date.now();
 timer=setInterval(async()=>{const at=Date.now();try{const r=await fetch('http://127.0.0.1:8080/health');health.push({at,ms:Date.now()-at,status:r.status});}catch(e){health.push({at,error:String(e)});}},150);
 await page.locator('#send-message-button').click();
 await page.waitForTimeout(1000);
 assert.equal(requests.length,1,'One actual chat inference required');
 if(!lightProbe && !profileOnly){
  assert.equal(requests[0].payload.features.stable_diffusion,true);
  assert(requests[0].payload.messages.some(m=>Array.isArray(m.content) && m.content.some(c=>c.type==='image_url')),'Reference must be submitted');
 }
 await page.waitForTimeout(10000);
 if(!lightProbe){const profile=await cdp.send('Profiler.stop');await fs.writeFile(out+'/image26-page'+suffix+'.cpuprofile',JSON.stringify(profile.profile));}
 if(cancelAfter){await page.waitForTimeout(Math.max(0,cancelAfter*1000-11000));await page.locator('#send-message-button').click();}
 await page.waitForFunction(()=>document.querySelector('[data-composer-root]')?.dataset.generating==='false',null,{timeout:360000});
 await page.waitForTimeout(1000);
 const text=await page.locator('body').innerText();
 const metrics=await page.evaluate(()=>({requestBodyType:window.__requestBodyType,gaps:window.__gaps,longTasks:window.__tasks,images:[...document.querySelectorAll('img')].map(i=>({src:i.getAttribute('src'),w:i.naturalWidth,h:i.naturalHeight})).filter(i=>i.w>1000)}));
 await page.screenshot({path:out+'/image26-live'+suffix+'-complete.png'});
 const result={seconds:(Date.now()-began)/1000,...metrics,errors,health,text,url:page.url(),uploadedIds,requests:requests.map(r=>({at:r.at,features:r.payload?.features}))};
 result.images=result.images.map(i=>({...i,src:i.src.startsWith('data:')?'inline reference':i.src}));
 await fs.writeFile(out+'/image26-live'+suffix+'.json',JSON.stringify(result,null,2));
 console.log(JSON.stringify({seconds:result.seconds,images:result.images,errors,gaps:metrics.gaps,longTasks:metrics.longTasks,maxHealthMs:Math.max(...health.map(v=>v.ms||0)),text:text.slice(-1500)}));
 assert(!/Falha ao|Error:/.test(text),'Image generation must succeed');
 if(!cancelAfter)assert(metrics.images.some(i=>i.w===2368 && i.h===1344),'Generated image dimensions must be preserved');
 if(validatePreview){
  assert.equal(metrics.requestBodyType,'Blob','Large inline request must use the worker result');
  assert.deepEqual(uploadedIds,[],'Temporary input must not be uploaded');
  const image=page.locator('.user-message img').first(),source=await image.getAttribute('src');
  assert(source.startsWith('blob:'),'Temporary image should render from original local Blob');
  await image.click();
  const preview=page.locator('.modal').filter({has:page.locator(`img[src="${source}"]`)});
  await preview.waitFor({state:'visible'});
  const downloadPromise=page.waitForEvent('download');await preview.locator('button').nth(1).click();
  const download=await downloadPromise,path=await download.path();
  const sha=buffer=>createHash('sha256').update(buffer).digest('hex');
  assert.equal(sha(await fs.readFile(path)),sha(await fs.readFile('backend/data/uploads/0e335168-40a8-473e-a233-1dd5f1cfb0c6_image.png')));
  await preview.locator('button').first().click();
  await page.locator('#sidebar-new-chat-button:visible').first().click();await page.waitForTimeout(300);
  assert(await page.evaluate(async source=>{try{await fetch(source);return false;}catch{return true;}},source),'Original Blob URL must be revoked after leaving chat');
  console.log('Preview, original-byte download and Blob disposal passed');
 }
}finally{clearInterval(timer);await browser.close();}
