import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {createServer} from 'vite';
import {chromium} from '../logs/ui-image-26/node_modules/playwright/index.mjs';
import {installMobileOfflineApi} from './fixtures/mobile-offline-api.mjs';

const hook=`import {getUsageTotalTokens} from '$lib/utils/chatUsage';onMount(()=>{window.__cacheStudy={async seed(usage){
 for(const id of [..._contentBuffers.keys()])stopContentFlush(id);cancelGenerationAnchorRAF();releaseGeneratingMessageAnchor();cancelMessagesBottomWheelLock();
 temporaryChatEnabled.set(true);chatId.set('local:cache-study');await tick();
 loading=false;loadedChatViewportReady=true;deferLoadedChatMessages=false;selectedModels=['local/mobile-fixture'];taskIds=[];autoScroll=false;
 history={currentId:'reply',messages:{question:{id:'question',role:'user',content:'Write code',parentId:null,childrenIds:['reply'],timestamp:1700000000},reply:{id:'reply',role:'assistant',content:'Partial code retained.',done:true,usage,parentId:'question',childrenIds:[],model:'local/mobile-fixture',timestamp:1700000001}}};await tick();
 },event(data){return chatEventHandler({chat_id:$chatId,message_id:'reply',data:{type:'chat:completion',data}},()=>{});},state(){const m=history.messages.reply;return{finish:m.finish_reason,content:m.content,total:getUsageTotalTokens(m.usage)}}};return()=>delete window.__cacheStudy;});`;
let server,browser,page;
const results=[];
try{
 server=await createServer({plugins:[{name:'context-cache-study',enforce:'pre',async load(id){if(id.endsWith('/src/lib/components/chat/Chat.svelte'))return(await fs.readFile(id,'utf8')).replace('</script>',hook+'\n</script>')}}],server:{port:5197,strictPort:true,watch:{ignored:['**/logs/**','**/scripts/**','**/docs/**']}}});
 await server.listen();browser=await chromium.launch();
 for(const width of [1440,390]){
  page=await browser.newPage({viewport:{width,height:900}});await installMobileOfflineApi(page);
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  await page.goto('http://localhost:5197',{waitUntil:'networkidle',timeout:90000});await page.waitForFunction(()=>window.__cacheStudy);
  const raw={cache_n:8811,prompt_n:4565,predicted_n:3008,predicted_per_second:98,context_window:16384};
  for(const usage of [raw,{...raw,prompt_tokens:13376,completion_tokens:3008,total_tokens:16384}]){
   await page.evaluate(value=>window.__cacheStudy.seed(value),usage);
   const trigger=page.locator('[data-token-usage-trigger]');if(width===390)await trigger.click();else await trigger.hover();
   const popup=page.locator('[data-token-usage-popup]');await popup.waitFor();
   assert((await popup.innerText()).includes('100.0%'));
   assert.equal((await page.evaluate(()=>window.__cacheStudy.state())).total,16384);
   if(width===390)await trigger.click();else await page.mouse.move(1,1);
  }
  await page.evaluate(usage=>window.__cacheStudy.event({usage,done:true,finish_reason:'length'}),raw);
  await page.getByText(/A resposta atingiu o limite de tokens antes de terminar\.|The response reached the token limit before finishing\./).waitFor();
  assert.equal((await page.evaluate(()=>window.__cacheStudy.state())).finish,'length');
  assert.equal((await page.evaluate(()=>window.__cacheStudy.state())).content,'Partial code retained.');
  await page.screenshot({path:`logs/context-cache-${width}.png`});
  await page.evaluate(()=>window.__cacheStudy.event({done:true,finish_reason:'stop'}));
  assert.equal((await page.evaluate(()=>window.__cacheStudy.state())).finish,'stop');
  assert.deepEqual(errors,[]);results.push({width,raw_and_canonical_total:16384,utilization_percent:100,finish_reason_preserved:true,partial_content_unchanged:true,errors});
  console.log('PASS',width);await page.close();
 }
 await fs.writeFile('logs/context-cache-visual.json',JSON.stringify(results,null,2));
}catch(error){await page?.screenshot({path:'logs/context-cache-failed.png'});throw error}finally{await browser?.close();await server?.close()}
