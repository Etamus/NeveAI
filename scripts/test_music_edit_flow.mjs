import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
import {createServer} from 'vite';
import {chromium} from '../logs/ui-image-26/node_modules/playwright/index.mjs';
import {installMobileOfflineApi} from './fixtures/mobile-offline-api.mjs';

const chatHook = `onMount(()=>{window.__seedMusicEdit=async()=>{
 temporaryChatEnabled.set(true);await tick();
 socket.set({id:'music-edit-fixture',connected:true,on(){},off(){},emit(){},disconnect(){}});
 const model={id:'local/mobile-fixture',name:'Music planner',owned_by:'llamacpp',info:{meta:{}},llamacpp:{reasoning_control:'toggle'}};
 models.set([model]);selectedModels=[model.id];stableDiffusionEnabled=false;videoGenerationEnabled=false;musicGenerationEnabled=true;
 history={currentId:'old-reply',messages:{original:{id:'original',parentId:null,childrenIds:['old-reply'],role:'user',content:'Crie uma musica sobre o mar.',models:[model.id]},'old-reply':{id:'old-reply',parentId:'original',childrenIds:[],role:'assistant',content:'Previous music result',done:true,model:model.id,statusHistory:[{action:'music_generation',done:true}]}}};
 await tick();};return()=>delete window.__seedMusicEdit;});`;
const editHook = `auditMount(()=>{window.__editMusicRequest=()=>editMessage('original',{content:'Crie uma musica sobre as estrelas.',files:[]});return()=>delete window.__editMusicRequest;});`;
let server, browser;
const results=[];
try {
 server=await createServer({plugins:[{name:'music-edit-test',enforce:'pre',async load(id){
  if(id.endsWith('/src/lib/components/chat/Chat.svelte'))return(await fs.readFile(id,'utf8')).replace('</script>',chatHook+'\n</script>');
  if(id.endsWith('/src/lib/components/chat/Messages.svelte')){
   let source=(await fs.readFile(id,'utf8')).replace('<script lang="ts">','<script lang="ts">\nimport {onMount as auditMount} from "svelte";');
   const at=source.lastIndexOf('</script>');return source.slice(0,at)+editHook+source.slice(at);
  }
 }}],server:{port:5188,strictPort:true,watch:{ignored:['**/logs/**','**/scripts/**','**/docs/**']}}});await server.listen();browser=await chromium.launch();
 for(const width of [390,1440]) {
  const page=await browser.newPage({viewport:{width,height:1000}}),events=[],errors=[];
  let loaded=false;
  page.on('pageerror',error=>{errors.push(error.message);console.log('PAGEERROR',error.message);});
  page.on('console',message=>{if(message.type()==='error')console.log('CONSOLE',message.text());});
  await installMobileOfflineApi(page);
  await page.route('**/llamacpp/status',route=>route.fulfill({json:{server_binary_exists:true,automatic_context:true}}));
  await page.route('**/llamacpp/models/loaded',route=>route.fulfill({json:{models:loaded?[{id:'local/mobile-fixture',filename:'fixture.gguf',is_loaded:true,n_ctx:8192}]:[]}}));
  await page.route('**/llamacpp/models/load',async route=>{events.push('load-start');await new Promise(resolve=>setTimeout(resolve,250));loaded=true;events.push('load-complete');await route.fulfill({json:{id:'local/mobile-fixture',filename:'fixture.gguf',n_ctx:8192}});});
  await page.route('**/api/chat/completions',async route=>{
   assert(loaded,'Music submitted with the planner unloaded');
   const body=route.request().postDataJSON();assert.equal(body.features.music_generation,true);
   assert(body.messages.some(message=>message.content?.includes('estrelas')));
   events.push('music-request');
   await route.fulfill({json:{task_id:'music-edit-fixture-task'}});
  });
  await page.goto('http://localhost:5188',{waitUntil:'networkidle',timeout:90000});
  await page.waitForFunction(()=>window.__seedMusicEdit);await page.evaluate(()=>window.__seedMusicEdit());
  await page.waitForFunction(()=>window.__editMusicRequest);await page.evaluate(()=>{void window.__editMusicRequest();});
  for(let i=0;i<100&&!events.includes('music-request');i++)await page.waitForTimeout(100);
  assert.deepEqual(events,['load-start','load-complete','music-request']);assert.deepEqual(errors,[]);
  await page.screenshot({path:`logs/music-edit-${width}.png`});results.push({width,events});await page.close();
 }
 await fs.writeFile('logs/music-edit-flow.json',JSON.stringify(results,null,2));console.log('PASS edited music reload, desktop/mobile');
}catch(error){for(const page of browser?.contexts().flatMap(context=>context.pages())??[])await page.screenshot({path:'logs/music-edit-failure.png'}).catch(()=>{});throw error;}
finally{await browser?.close();await server?.close();}
