import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
import {createServer} from 'vite';
import {chromium} from '../logs/ui-image-26/node_modules/playwright/index.mjs';
import {installMobileOfflineApi} from './fixtures/mobile-offline-api.mjs';

const origin='http://localhost:5188',output='logs/chat-search-modal';
const data=[{id:'viagem',title:'Planejamento de viagem'},{id:'historia',title:'Conte uma história'},
 ...Array.from({length:65},(_,index)=>({id:'longa-'+index,title:'Conversa longa '+index}))]
 .map(item=>({...item,updated_at:1700000000}));
const chatHook=`onMount(()=>{window.__searchDraft={
 async seed(){
  temporaryChatEnabled.set(true);socket.set({id:'search-fixture',connected:true,on(){},off(){},emit(){},disconnect(){}});
  const model={id:'search-model',name:'Search fixture',owned_by:'openai',info:{meta:{}}};
  models.set([model]);selectedModels=[model.id];await tick();
  history={currentId:null,messages:{}};await tick();messageInput?.setText('Rascunho que nao deve ser enviado');await tick();
 },state(){return {prompt,messages:Object.keys(history.messages).length};}
};return()=>delete window.__searchDraft;});`;
let server,browser;const results=[];
try{
 await fs.mkdir(output,{recursive:true});
 server=await createServer({cacheDir:'node_modules/.vite-settings-memory-cleanup',plugins:[{
  name:'search-modal-fixture',enforce:'pre',configResolved(config){config.server.proxy=undefined;},
  async load(id){
   if(id.endsWith('/src/routes/(app)/+layout.svelte'))return(await fs.readFile(id,'utf8')).replace('</script>',`onMount(()=>{window.__openSearch=()=>showSearch.set(true);return()=>delete window.__openSearch;});\n</script>`);
   if(id.endsWith('/src/lib/components/chat/Chat.svelte'))return(await fs.readFile(id,'utf8')).replace('</script>',chatHook+'\n</script>');
  }
 }],server:{port:5188,strictPort:true,watch:{ignored:['**/logs/**','**/scripts/**','**/docs/**']}}});
 await server.listen();browser=await chromium.launch();
 for(const [name,viewport] of [['desktop',{width:1440,height:1000}],['mobile',{width:390,height:844}]]){
  const context=await browser.newContext({viewport,serviceWorkers:'block'});
  try{
   const page=await context.newPage();page.setDefaultTimeout(15000);
   const errors=[],searches=[],completions=[];let previewRequests=0;
   page.on('pageerror',error=>{errors.push(error.message);console.log('PAGEERROR',error.stack);});
   await page.routeWebSocket('**/*',ws=>ws.close());
   await page.route('**/*',route=>{
    const url=new URL(route.request().url());
    if(url.origin===origin&&!/^\/(api|llamacpp|ws|dbg|openai|audio|retrieval|health|static)(\/|$)/.test(url.pathname))return route.continue();
    return route.fulfill({status:503,body:'Blocked by search fixture'});
   });
   await installMobileOfflineApi(page);
   await page.route('**/api/chat/completions',route=>{
    completions.push(route.request().postDataJSON());return route.fulfill({json:{task_id:'blocked-search-submit'}});
   });
   await page.route('**/api/v1/chats/**',async route=>{
    const url=new URL(route.request().url());
    if(route.request().method()!=='GET')throw new Error('No chat writes allowed in search fixture');
    if(url.pathname.endsWith('/search')){
     const query=url.searchParams.get('text'),number=Number(url.searchParams.get('page')??1);
     searches.push({query,page:number});
     if(query==='lenta'){
      await new Promise(resolve=>setTimeout(resolve,1400));
      return route.fulfill({json:number===1?[{id:'old',title:'Resultado antigo',updated_at:1700000000}]:[]});
     }
     const filtered=data.filter(item=>item.title.toLowerCase().includes(query.toLowerCase()));
     return route.fulfill({json:filtered.slice((number-1)*60,number*60)});
    }
    if(/\/chats\/$/.test(url.pathname)){
     const number=Number(url.searchParams.get('page')??1);
     return route.fulfill({json:data.slice((number-1)*60,number*60)});
    }
    const id=url.pathname.split('/').at(-1),record=data.find(item=>item.id===id);
    if(record){
     previewRequests++;
     return route.fulfill({json:{...record,user_id:'mobile-fixture-user',chat:{models:['search-model'],history:{currentId:'answer',messages:{
      question:{id:'question',role:'user',content:'Mensagem '+id,parentId:null,childrenIds:['answer'],models:['search-model']},
      answer:{id:'answer',role:'assistant',content:'Resposta de prévia '+id,parentId:'question',childrenIds:[],done:true,model:'search-model'}
     }}}}});
    }
    return route.fulfill({json:[]});
   });
   await page.goto(origin,{waitUntil:'networkidle',timeout:90000});
   await page.waitForFunction(()=>window.__openSearch&&window.__searchDraft);
   await page.evaluate(()=>window.__searchDraft.seed());
   await page.locator('#chat-input').fill('Rascunho que nao deve ser enviado');
   await page.waitForFunction(()=>window.__searchDraft.state().prompt.includes('Rascunho'));
   const original=await page.evaluate(()=>window.__searchDraft.state());
   assert(original.prompt.includes('Rascunho'));
   await page.evaluate(()=>window.__openSearch());
   const input=page.locator('#search-input'),shell=page.locator('.search-modal-shell');
   const queryResult=query=>page.waitForResponse(response=>{
    const url=new URL(response.url());
    return url.pathname.endsWith('/chats/search')&&url.searchParams.get('text')===query&&url.searchParams.get('page')==='1';
   });
   await input.waitFor({state:'visible'});
   assert(await input.evaluate(el=>el===document.activeElement));
   const originalUrl=page.url();
   await Promise.all([queryResult('viagem'),input.fill('viagem')]);
   await shell.locator('a[href="/c/viagem"]').waitFor();
   assert(searches.some(item=>item.query==='viagem'&&item.page===1));
   await Promise.all([queryResult('viagem'),input.press('Enter')]);
   await shell.locator('a[href="/c/viagem"]').waitFor();
   assert(await input.isVisible());assert.equal(page.url(),originalUrl);
   assert.deepEqual(await page.evaluate(()=>window.__searchDraft.state()),original);
   await input.fill('p');await Promise.all([queryResult('p'),input.press('Enter')]);
   await page.waitForFunction(()=>document.querySelector('#search-input')?.value==='p');
   assert(await input.isVisible());assert.equal(completions.length,0);
   await Promise.all([queryResult('história'),input.fill('história')]);
   await shell.locator('a[href="/c/historia"]').waitFor();
   assert(searches.some(item=>item.query==='história'));
   await input.fill('lenta');
   await page.waitForRequest(request=>request.url().includes('/chats/search?')&&new URL(request.url()).searchParams.get('text')==='lenta');
   await input.fill('história');await Promise.all([queryResult('história'),input.press('Enter')]);
   await shell.locator('a[href="/c/historia"]').waitFor();
   await page.waitForTimeout(1500);
   assert.equal(await shell.getByText('Resultado antigo',{exact:true}).count(),0);
   assert(await shell.locator('a[href="/c/historia"]').isVisible());
   await Promise.all([queryResult('longa'),input.fill('longa')]);
   await shell.locator('a[href="/c/longa-0"]').waitFor();
   await shell.locator('.overflow-y-auto').first().evaluate(el=>el.scrollTop=el.scrollHeight);
   await shell.locator('a[href="/c/longa-64"]').waitFor();
   assert(searches.some(item=>item.query==='longa'&&item.page===2));
   await Promise.all([page.waitForResponse(response=>new URL(response.url()).pathname.endsWith('/chats/')),input.fill('')]);
   await shell.locator('a[href="/c/viagem"]').waitFor();
   await input.fill('sem resultados aqui');await input.press('Enter');
   await shell.getByText('Nenhum resultado encontrado',{exact:true}).waitFor();
   assert(await input.isVisible());assert.equal(page.url(),originalUrl);
   await input.fill('viagem');await shell.locator('a[href="/c/viagem"]').waitFor();
   for(const theme of ['dark','light']){
    await page.evaluate(theme=>document.documentElement.classList.toggle('dark',theme==='dark'),theme);
    await page.screenshot({path:`${output}/${name}-${theme}.png`});
   }
   await input.press('Escape');await input.waitFor({state:'hidden'});
   assert.deepEqual(await page.evaluate(()=>window.__searchDraft.state()),original);
   await page.evaluate(()=>window.__openSearch());await input.waitFor({state:'visible'});
   await shell.locator('a[href="/c/viagem"]').waitFor();
   await page.waitForTimeout(550);
   await input.press('ArrowDown');
   await shell.locator('a[href="/c/viagem"][data-arrow-selected="true"]').waitFor();
   await input.press('Enter');
   await page.waitForURL('**/c/viagem');await input.waitFor({state:'hidden'});
   assert.equal(completions.length,0);
   assert.deepEqual(errors,[]);
   results.push({name,searches,previewRequests,plainEnterSearches:true,noComposerSubmit:true,draftPreserved:true,latestQueryWins:true,pagination:true,keyboardNavigation:true,errors});
  }finally{await context.close();}
 }
 await fs.writeFile(`${output}/results.json`,JSON.stringify(results,null,2));
 console.log('PASS chat search '+JSON.stringify(results));
}finally{await browser?.close();await server?.close();}
