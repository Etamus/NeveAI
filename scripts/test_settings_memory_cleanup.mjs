import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
import {createServer} from 'vite';
import {chromium} from '../logs/ui-image-26/node_modules/playwright/index.mjs';
import {installMobileOfflineApi} from './fixtures/mobile-offline-api.mjs';

const output='logs/settings-memory-cleanup';
const origin='http://localhost:5188';
const hook=`let auditMemoryOpen=false, auditFilesOpen=false, auditMemory;
onMount(()=>{
 window.__cleanup={
  async settings(tab='general'){showSettingsTab.set(tab);showSettings.set(true);await tick();},
  async poll(){await checkForVersionUpdates();await tick();},
  async memory(){showSettings.set(false);await auditMemory.open();await tick();},
  async files(){showSettings.set(false);auditFilesOpen=true;await tick();},
  async close(){showSettings.set(false);auditFilesOpen=false;auditMemoryOpen=false;await tick();}
 };
 return()=>delete window.__cleanup;
});`;
let server,browser;
const results=[];
try{
 await fs.mkdir(output,{recursive:true});
 server=await createServer({cacheDir:'node_modules/.vite-settings-memory-cleanup',plugins:[{
  name:'settings-memory-cleanup-fixture',enforce:'pre',
  configResolved(config){config.server.proxy=undefined;},
  async load(id){
   if(id.endsWith('/src/routes/(app)/+layout.svelte')){
    let source=await fs.readFile(id,'utf8');
    source=source.replace('<script lang="ts">','<script lang="ts">\nimport AuditMemory from "$lib/components/chat/Settings/Personalization/ManageModal.svelte";\nimport AuditFiles from "$lib/components/layout/FilesModal.svelte";');
    return source.replace('</script>',hook+'\n</script>')+'\n<AuditMemory bind:this={auditMemory} bind:show={auditMemoryOpen}/><AuditFiles bind:show={auditFilesOpen}/>';
   }
   if(id.endsWith('/src/lib/components/chat/Chat.svelte')){
    const source=await fs.readFile(id,'utf8');
    return source.replace('</script>',`onMount(()=>{window.__cleanupText=(value)=>messageInput?.setText(value);return()=>delete window.__cleanupText;});\n</script>`);
   }
  }
 }],server:{port:5188,strictPort:true,watch:{ignored:['**/logs/**','**/scripts/**','**/docs/**']}}});
 await server.listen();
 browser=await chromium.launch({ignoreDefaultArgs:['--hide-scrollbars']});
 for(const [name,viewport] of [['desktop',{width:1440,height:1000}],['mobile',{width:390,height:844}]]){
  const context=await browser.newContext({viewport,serviceWorkers:'block'});
  try{
   const page=await context.newPage();page.setDefaultTimeout(15000);
   const errors=[];page.on('pageerror',e=>{errors.push(e.message);console.log('PAGEERROR',e.stack);});
   let memories=[{id:'one',content:'Meu nome e Marina',updated_at:1700000000},{id:'two',content:'Prefiro respostas curtas',updated_at:1700000001}];
   let deletes=0,updates=0,reads=0,adds=0;
   let updateAvailable=true;
   await page.routeWebSocket('**/*',ws=>ws.close());
   await page.route('**/*',route=>{
    const url=new URL(route.request().url());
    if(url.origin===origin&&!/^\/(api|llamacpp|ws|dbg|openai|audio|retrieval|health|static)(\/|$)/.test(url.pathname))return route.continue();
    return route.fulfill({status:503,body:'Blocked by settings cleanup fixture'});
   });
   await installMobileOfflineApi(page);
   await page.route('**/api/v1/memories/**',async route=>{
    const path=new URL(route.request().url()).pathname;
    if(route.request().method()==='GET'){
     reads++;await new Promise(resolve=>setTimeout(resolve,700));
     return route.fulfill({json:memories});
    }
    if(route.request().method()==='DELETE'){
     deletes++;memories=memories.filter(m=>!path.endsWith('/'+m.id));
     return route.fulfill({json:true});
    }
    if(path.endsWith('/add')){
     adds++;await new Promise(resolve=>setTimeout(resolve,500));
     const memory={id:'added-'+adds,content:route.request().postDataJSON().content,updated_at:1700000002};
     memories=[...memories,memory];
     return route.fulfill({json:memory});
    }
    if(path.endsWith('/update')){
     updates++;await new Promise(resolve=>setTimeout(resolve,500));
     const id=path.split('/').at(-2),content=route.request().postDataJSON().content;
     memories=memories.map(m=>m.id===id?{...m,content}:m);
     return route.fulfill({json:memories.find(m=>m.id===id)});
    }
    throw new Error('Unexpected memory request '+path);
   });
   await page.route('**/api/v1/files/search**',route=>route.fulfill({json:Array.from({length:30},(_,i)=>({id:'file-'+i,filename:'document-'+i+'.txt',created_at:1700000000,meta:{size:1024}}))}));
   await page.route('**/api/version/updates',async route=>{
    const available=updateAvailable;
    await new Promise(resolve=>setTimeout(resolve,1200));
    return route.fulfill({json:{current_tag:'v3.1.01',latest_tag:available?'v3.1.02':'v3.1.01',neve_update_available:available,llama_cpp:{update_available:false}}});
   });
   await page.goto(origin,{waitUntil:'networkidle',timeout:90000});
   await page.waitForFunction(()=>window.__cleanup&&window.__cleanupText);
   await page.evaluate(()=>document.fonts.ready);
   const shot=async(label)=>page.screenshot({path:`${output}/${name}-${label}.png`});
   await page.evaluate(()=>window.__cleanup.settings());
   assert.equal(await page.locator('#chat-background-label').count(),0);
   assert.equal(await page.getByText('Imagem de fundo do chat',{exact:true}).count(),0);
   await page.evaluate(()=>window.__cleanup.poll());
   await page.evaluate(()=>window.__cleanup.settings('about'));
   await page.locator('#tab-about button').filter({hasText:/^Atualizar$/}).waitFor({timeout:500});
   await shot('about-immediate');
   await page.waitForTimeout(1300);
   assert(await page.locator('#tab-about button').filter({hasText:/^Atualizar$/}).isVisible());
   updateAvailable=false;
   await page.evaluate(()=>window.__cleanup.poll());
   assert.equal(await page.locator('#tab-about button').filter({hasText:/^Atualizar$/}).count(),0,'No button when fully updated');
   await page.evaluate(()=>window.__cleanup.close());
   await page.evaluate(()=>window.__cleanup.settings('about'));
   assert.equal(await page.locator('#tab-about button').filter({hasText:/^Atualizar$/}).count(),0,'No stale button on reopen');
   await page.evaluate(()=>window.__cleanup.settings('personalization'));
   await page.locator('#tab-personalization').getByRole('button',{name:'Gerenciar',exact:true}).click();
   await page.getByRole('cell',{name:'Meu nome e Marina',exact:true}).waitFor({timeout:500});
   assert.equal(await page.locator('.modal[aria-hidden="false"] [role="status"]').count(),0);
   await page.keyboard.press('Escape');
   await page.getByRole('cell',{name:'Meu nome e Marina',exact:true}).waitFor({state:'detached'});
   await page.evaluate(()=>window.__cleanup.memory());
   assert.equal(await page.locator('.modal[aria-hidden="false"] [role="status"]').count(),0);
   assert.equal(await page.getByText('Memórias acessíveis pela Neve serão mostradas aqui.',{exact:true}).count(),0);
   await page.getByRole('cell',{name:'Meu nome e Marina',exact:true}).waitFor({timeout:500});
   const deleteButton=page.getByRole('row').filter({hasText:'Meu nome e Marina'}).getByRole('button',{name:'Excluir',exact:true});
   await deleteButton.hover();
   await page.getByRole('tooltip').filter({hasText:/^Excluir$/}).waitFor();
   await page.getByRole('row').filter({hasText:'Meu nome e Marina'}).getByRole('button',{name:'Excluir',exact:true}).click();
   await page.getByText('Excluir memória',{exact:true}).waitFor();
   assert.equal(await page.getByText('Excluir memória',{exact:true}).evaluate(el=>{
    const box=el.closest('[tabindex]')??el.closest('.rounded-2xl')??el.parentElement.parentElement;
    return box.getAnimations({subtree:true}).filter(animation=>animation.playState==='running').length;
   }),0);
   assert.equal(deletes,0);
   await shot('delete-confirm');
   await page.getByRole('button',{name:'Cancelar',exact:true}).click();
   assert.equal(deletes,0);
   await page.getByRole('row').filter({hasText:'Meu nome e Marina'}).getByRole('button',{name:'Excluir',exact:true}).click();
   await page.getByRole('button',{name:'Excluir',exact:true}).last().click();
   await page.waitForFunction(()=>!document.body.textContent.includes('Meu nome e Marina'));
   assert.equal(deletes,1);
   await page.getByRole('row').filter({hasText:'Prefiro respostas curtas'}).getByRole('button',{name:'Editar',exact:true}).click();
   const editModal=page.locator('.modal[aria-hidden="false"]').last();
   const animation=await editModal.locator(':scope > div').evaluate(el=>getComputedStyle(el).transform);
   assert.equal(animation,'none');
   async function checkMemoryCorner(modal,label){
    for(const mode of ['dark','light']){
     await page.evaluate(mode=>document.documentElement.classList.toggle('dark',mode==='dark'),mode);
     await modal.locator('textarea').fill(('Linha de memoria\n').repeat(80));
     const corner=await modal.locator('textarea').evaluate(el=>({
      corner:getComputedStyle(el,'::-webkit-scrollbar-corner').backgroundColor,
      resizer:getComputedStyle(el,'::-webkit-resizer').backgroundColor,
      top:getComputedStyle(el,'::-webkit-scrollbar-track').marginTop,
      bottom:getComputedStyle(el,'::-webkit-scrollbar-track').marginBottom,
      overflow:el.scrollHeight>el.clientHeight
     }));
     assert(corner.overflow);
     assert.equal(corner.corner,'rgba(0, 0, 0, 0)');
     assert.equal(corner.resizer,'rgba(0, 0, 0, 0)');
     assert.equal(corner.top,'10px');
     assert.equal(corner.bottom,'10px');
     await modal.locator('textarea').evaluate(el=>el.scrollTop=el.scrollHeight);
     await modal.locator('textarea').screenshot({path:`${output}/${name}-${label}-corner-${mode}.png`});
    }
   }
   await checkMemoryCorner(editModal,'edit');
   await editModal.locator('textarea').fill('Prefiro exemplos praticos');
   const beforeEditReads=reads;
   await editModal.getByRole('button',{name:'Atualizar',exact:true}).click();
   assert.equal(await editModal.getByRole('button',{name:'Atualizar',exact:true}).locator('svg').count(),0);
   assert(await editModal.getByRole('button',{name:'Atualizar',exact:true}).isDisabled());
   await page.getByRole('cell',{name:'Prefiro exemplos praticos',exact:true}).waitFor();
   assert.equal(updates,1);
   assert.equal(reads,beforeEditReads,'Editing must not reload the list');
   assert.equal(await page.locator('.modal[aria-hidden="false"] [role="status"]').count(),0);
   await page.locator('.modal[aria-hidden="false"]').last().getByRole('button',{name:'Adicionar',exact:true}).click();
   const addModal=page.locator('.modal[aria-hidden="false"]').last();
   await checkMemoryCorner(addModal,'add');
   await addModal.locator('textarea').fill('Meu projeto usa Rust');
   const beforeAddReads=reads;
   await addModal.getByRole('button',{name:'Adicionar',exact:true}).click();
   assert.equal(await addModal.getByRole('button',{name:'Adicionar',exact:true}).locator('svg').count(),0);
   assert(await addModal.getByRole('button',{name:'Adicionar',exact:true}).isDisabled());
   await page.getByRole('cell',{name:'Meu projeto usa Rust',exact:true}).waitFor();
   assert.equal(reads,beforeAddReads,'Adding must not reload the list');
   assert.equal(adds,1);
   await page.evaluate(()=>window.__cleanup.close());
   await page.evaluate(()=>window.__cleanup.memory());
   await page.getByRole('cell',{name:'Prefiro exemplos praticos',exact:true}).waitFor({timeout:500});
   assert.equal(await page.locator('.modal[aria-hidden="false"] [role="status"]').count(),0);
   assert(reads>=2);
   await shot('memory');
   await page.locator('.modal[aria-hidden="false"]').last().getByRole('button',{name:'Limpar',exact:true}).click();
   await page.getByText('Limpar memória',{exact:true}).waitFor();
   assert.equal(await page.getByText('Limpar memória',{exact:true}).evaluate(el=>{
    const box=el.closest('[tabindex]')??el.parentElement.parentElement;
    return box.getAnimations({subtree:true}).filter(animation=>animation.playState==='running').length;
   }),0);
   await page.getByRole('button',{name:'Cancelar',exact:true}).click();
   assert.equal(deletes,1,'Cancelling clear must preserve all memories');
   await page.evaluate(()=>window.__cleanup.close());
   await page.evaluate(()=>window.__cleanup.files());
   await page.locator('.files-list-scroll > div').nth(3).waitFor();
   const files=await page.locator('.files-list-scroll').evaluate(el=>{
    const box=el.getBoundingClientRect(),card=el.children[1].getBoundingClientRect();
    return {gap:box.right-card.right,padding:getComputedStyle(el).paddingRight,overflow:el.scrollHeight>el.clientHeight};
   });
   assert(files.gap>=12&&files.overflow);
   await shot('files');
   await page.evaluate(()=>window.__cleanup.close());
   for(const theme of ['dark','light']){
    await page.evaluate(theme=>document.documentElement.classList.toggle('dark',theme==='dark'),theme);
    await page.evaluate(()=>window.__cleanupText(Array.from({length:60},(_,i)=>'Linha '+i+' '+('texto '.repeat(40))).join('\n')));
    const corner=await page.locator('.chat-input-scroll').evaluate(el=>{
     el.scrollTop=el.scrollHeight;
     return {color:getComputedStyle(el,'::-webkit-scrollbar-corner').backgroundColor,overflow:el.scrollHeight>el.clientHeight};
    });
    assert.equal(corner.color,'rgba(0, 0, 0, 0)');assert(corner.overflow);
    await shot('composer-'+theme);
   }
   await page.evaluate(()=>window.__cleanupText(''));
   const models=page.locator('button[aria-label="Models"]');await models.click();
   await page.locator('.unified-models-shell').waitFor();
   assert.equal(await page.locator('.unified-global-settings').count(),0);
   await shot('models');
   await page.waitForTimeout(800);
   assert.deepEqual(errors,[]);
   results.push({name,deletes,updates,adds,reads,files,immediateReadyList:true,noListSpinner:true,noAddSpinner:true,memoryCornersTransparent:true,updateImmediate:true,noEditAnimation:true,noEditSpinner:true,noDeleteAnimation:true,globalSettingsRemoved:true,errors});
  }finally{await context.close();}
 }
 await fs.writeFile(`${output}/results.json`,JSON.stringify(results,null,2));
 console.log('PASS settings cleanup '+JSON.stringify(results));
}finally{await browser?.close();await server?.close();}
