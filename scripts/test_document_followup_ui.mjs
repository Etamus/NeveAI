import fs from 'node:fs/promises';
import {constants} from 'node:fs';
import assert from 'node:assert/strict';
import {createServer} from 'vite';
import {chromium} from '../logs/ui-image-26/node_modules/playwright/index.mjs';
import {installMobileOfflineApi} from './fixtures/mobile-offline-api.mjs';

const origin='http://localhost:5188';
const routeDir=new URL('../src/routes/__document_status_test/',import.meta.url);
const routeFile=new URL('+page.svelte',routeDir);
const hook=`onMount(()=>{window.__titleTest=async(content)=>{
 temporaryChatEnabled.set(false);socket.set({id:'title-fixture',connected:true,on(){},off(){},emit(){},disconnect(){}});
 const model={id:'title-model',name:'Title fixture',owned_by:'openai',info:{meta:{}}};
 models.set([model]);selectedModels=[model.id];
 history={currentId:'question',messages:{question:{id:'question',role:'user',content,parentId:null,childrenIds:[]}}};
 await tick();return await initChatHandler(history);
};return()=>delete window.__titleTest;});`;
let server,browser;const results=[];
await fs.mkdir(routeDir,{recursive:true});
await fs.copyFile(new URL('./fixtures/document-status.svelte',import.meta.url),routeFile,constants.COPYFILE_EXCL);
try{
 server=await createServer({cacheDir:'node_modules/.vite-document-followups',plugins:[{
  name:'document-followup-test',enforce:'pre',configResolved(config){config.server.proxy=undefined;},
  async load(id){if(id.endsWith('/src/lib/components/chat/Chat.svelte'))return(await fs.readFile(id,'utf8')).replace('</script>',hook+'\n</script>');}
 }],server:{port:5188,strictPort:true,watch:{ignored:['**/logs/**','**/scripts/**','**/docs/**']}}});
 await server.listen();browser=await chromium.launch();
 for(const [name,viewport] of [['desktop',{width:1440,height:1000}],['mobile',{width:390,height:844}]]){
  const page=await browser.newPage({viewport});const errors=[];let records=[];let completions=0;
  page.on('pageerror',e=>{errors.push(e.message);console.log('PAGEERROR',e.stack);});
  await page.routeWebSocket('**/*',ws=>ws.close());
  await page.route('**/*',route=>{
   const url=new URL(route.request().url());
   if(url.origin===origin&&!/^\/(api|llamacpp|ws|dbg|openai|audio|retrieval|health|static)(\/|$)/.test(url.pathname))return route.continue();
   return route.fulfill({status:503,body:'Blocked by document fixture'});
  });
  await installMobileOfflineApi(page);
  await page.route('**/api/chat/completions',route=>{completions++;return route.fulfill({json:{}});});
  await page.route('**/api/v1/chats/**',route=>{
   const path=new URL(route.request().url()).pathname;
   if(path.endsWith('/new')&&route.request().method()==='POST'){
    const body=route.request().postDataJSON();
    const item={id:'initial-title',title:body.chat.title,chat:body.chat,updated_at:1700000000,user_id:'mobile-fixture-user'};
    records=[item];return route.fulfill({json:item});
   }
   if(path.endsWith('/initial-title'))return route.fulfill({json:records[0]});
   return route.fulfill({json:records});
  });
  await page.goto(origin,{waitUntil:'networkidle',timeout:120000});
  await page.waitForFunction(()=>window.__titleTest).catch(async error=>{
   console.log(page.url(),await page.locator('body').innerText(),errors);throw error;
  });
  await page.evaluate(()=>window.__titleTest('Qual a melhor temporada de GOT?'));
  assert.equal(records[0].title,'Qual a melhor temporada de GOT?');
  assert.equal(completions,0,'Title must not wait for any LLM completion');
  await page.goto(origin+'/__document_status_test',{waitUntil:'networkidle'});
  await page.locator('#document-status').getByText('Preparando arquivo...', {exact:true}).waitFor();
  assert.equal(await page.locator('#document-status button').count(),0);
  // No chevron is rendered while the document is being prepared.
  assert.equal(await page.locator('#document-status [aria-expanded]').count(),0);
  await page.screenshot({path:`logs/document-status-${name}-pending.png`});
  await page.locator('#complete-document').click();
  await page.locator('#document-status button').waitFor();
  assert.equal(await page.locator('#document-status button').getAttribute('aria-expanded'),'false');
  await page.locator('#document-status button').click();
  assert.equal(await page.locator('#document-status button').getAttribute('aria-expanded'),'true');
  await page.screenshot({path:`logs/document-status-${name}-complete.png`});
  assert.deepEqual(errors,[]);
  results.push({viewport:name,titleBeforeCompletion:records[0].title,pendingNotExpandable:true,completeExpandable:true});
  await page.close();
 }
 await fs.writeFile('logs/document-followup-ui.json',JSON.stringify(results,null,2));
 console.log(JSON.stringify(results));
}finally{
 await browser?.close();await server?.close();await fs.unlink(routeFile);await fs.rmdir(routeDir);
}
