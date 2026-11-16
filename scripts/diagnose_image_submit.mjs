import fs from 'node:fs/promises';
import {execFileSync} from 'node:child_process';
import assert from 'node:assert/strict';
import {createServer} from 'vite';
import {chromium} from '../logs/ui-image-26/node_modules/playwright/index.mjs';
import {installMobileOfflineApi} from './fixtures/mobile-offline-api.mjs';

const output='logs/image-latency-20261114';
const data=JSON.parse(execFileSync('backend/neveai/venv/Scripts/python.exe',['-c',
 "import sqlite3,json;d=sqlite3.connect('file:backend/data/neve.db?mode=ro',uri=True);c=json.loads(d.execute('select chat from chat where id=?',('0016cbe4-0338-46ef-92fa-0763b4862db1',)).fetchone()[0]);print(json.dumps(dict(history=c['history'],files={r[0]:r[1] for r in d.execute('select id,path from file')})))"],{encoding:'utf8'}));
const reference=data.history.messages['e521afb0-9ac8-4d43-92c0-07f5332af98e'].files;
const hook=`onMount(()=>{
 const disconnected={id:'latency-fixture',connected:false,on(){},off(){},emit(){},disconnect(){}};
 window.__imageSubmit={
  async seed(quality,fixture,attachments){
   temporaryChatEnabled.set(true);socket.set(disconnected);chatId.set('local:image-latency');
   const model={id:'latency-fixture',name:'Latency fixture',owned_by:'openai',info:{meta:{}}};
   models.set([model]);selectedModels=[model.id];await tick();
   taskIds=null;submittingPrompt=false;history=structuredClone(fixture);files=structuredClone(attachments);chatFiles=[];
   stableDiffusionEnabled=true;stableDiffusionQuality=quality;videoGenerationEnabled=false;musicGenerationEnabled=false;
   prompt='Faça ela sorrindo de boca aberta';messageInput?.setText(prompt);await tick();
  },
  submit(){void submitPrompt('Faça ela sorrindo de boca aberta').catch(error=>window.__submitError=String(error));},
  progress(quality,width,height){const message=history.messages[history.currentId];if(message?.role==='assistant'){message.statusHistory=[{action:'stable_diffusion',quality,width,height,resolution:'auto',progress:0,done:false}];history=history;}},
  state(){return {currentId:history.currentId,role:history.messages[history.currentId]?.role};}
 };
 return()=>delete window.__imageSubmit;
});`;
let server,browser;
const results=[];
try{
 server=await createServer({cacheDir:'node_modules/.vite-image-submit-diagnostic',plugins:[{
  name:'image-latency-fixture',enforce:'pre',configResolved(c){c.server.proxy=undefined;},
  async load(id){if(id.endsWith('/src/lib/components/chat/Chat.svelte'))return (await fs.readFile(id,'utf8')).replace('</script>',hook+'\n</script>');}
 }],server:{port:5193,strictPort:true,watch:{ignored:['**/logs/**','**/scripts/**']}}});
 await server.listen();browser=await chromium.launch();
 for(const width of [1440,390]){
  const page=await browser.newPage({viewport:{width,height:1000}});const errors=[];
  page.on('pageerror',e=>{errors.push(e.message);console.error('PAGEERROR',e.message);});
  await page.routeWebSocket('**/*',socket=>socket.close());
  await installMobileOfflineApi(page);
  await page.route('**/api/v1/files/**',async route=>{
   const id=new URL(route.request().url()).pathname.split('/')[4];
   const file=data.files[id];
   if(!file)return route.fulfill({status:404,body:''});
   await route.fulfill({body:await fs.readFile(file),contentType:'image/png'});
  });
  await page.route('**/api/chat/completions',()=>{throw Error('No inference allowed from UI fixture');});
  await page.goto('http://localhost:5193',{waitUntil:'networkidle',timeout:120000});
  await page.waitForFunction(()=>window.__imageSubmit).catch(async error=>{console.error('BOOT',page.url(),await page.locator('body').innerText());await page.screenshot({path:output+'/submit-bootstrap.png'});throw error;});
  for(const quality of ['qwen_image_2s','qwen_image_2_1_official','minimax_h3_image']){
   await page.reload({waitUntil:'networkidle',timeout:120000});
   await page.waitForFunction(()=>window.__imageSubmit);
   await page.evaluate(async ({quality,history,reference})=>window.__imageSubmit.seed(quality,history,reference),{quality,history:data.history,reference});
   await page.waitForTimeout(1500);
   await page.evaluate(()=>{
    window.__longtasks=[];window.__rafgaps=[];let previous=performance.now();
    window.__taskObserver=new PerformanceObserver(list=>list.getEntries().forEach(e=>window.__longtasks.push({at:e.startTime,duration:e.duration})));
    window.__taskObserver.observe({type:'longtask'});
    function frame(now){if(now-previous>40)window.__rafgaps.push(now-previous);previous=now;window.__frame=requestAnimationFrame(frame);}
    window.__frame=requestAnimationFrame(frame);window.__submitStarted=performance.now();window.__imageSubmit.submit();
   });
   await page.waitForTimeout(1000);
   await page.waitForFunction(original=>window.__imageSubmit.state().currentId!==original && window.__imageSubmit.state().role==='assistant',data.history.currentId,{timeout:15000}).catch(async error=>{console.error('SUBMIT',quality,await page.evaluate(()=>({state:window.__imageSubmit.state(),error:window.__submitError,text:document.body.innerText})));throw error;});
   const dimensions=quality==='qwen_image_2s'?[1536,864]:quality==='minimax_h3_image'?[2720,1536]:[2368,1344];
   await page.evaluate(({quality,dimensions})=>window.__imageSubmit.progress(quality,...dimensions),{quality,dimensions});
   await page.waitForTimeout(2500);
   const metrics=await page.evaluate(()=>{window.__taskObserver.disconnect();cancelAnimationFrame(window.__frame);return {longTasks:window.__longtasks,rafGaps:window.__rafgaps,state:window.__imageSubmit.state(),error:window.__submitError};});
   results.push({width,quality,...metrics,errors:[...errors]});
   assert(!metrics.error);assert.equal(metrics.state.role,'assistant');
   await page.screenshot({path:output+'/submit-'+width+'-'+quality+'.png'});
  }
  await page.close();
 }
 await fs.writeFile(output+'/submit-browser.json',JSON.stringify(results,null,2));
 console.log(JSON.stringify(results));
}finally{await browser?.close();await server?.close();}
