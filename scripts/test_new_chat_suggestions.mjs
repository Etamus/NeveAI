import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
import {createServer} from 'vite';
import {chromium} from '../logs/ui-image-26/node_modules/playwright/index.mjs';
import {installMobileOfflineApi} from './fixtures/mobile-offline-api.mjs';

const output='logs/new-chat-suggestions',origin='http://localhost:5196';
const hook=`import {showSettings as fixtureSettingsModal, showSettingsTab as fixtureSettingsTab} from '$lib/stores';
onMount(()=>{window.__suggestionsTemporary=async(value)=>{temporaryChatEnabled.set(value);await tick();};return()=>delete window.__suggestionsTemporary;});
onMount(()=>{window.__suggestions={async use(integration,text='Fixture request'){models.update(items=>items.map(model=>({...model,owned_by:'openai'})));setNativeIntegration(integration);await tick();await submitPrompt(text);},async fresh(){history={currentId:null,messages:{}};taskIds=[];setNativeIntegration(null);await tick();},openSettings(){fixtureSettingsTab.set('general');fixtureSettingsModal.set(true);},closeSettings(){fixtureSettingsModal.set(false);},async select(integration){setNativeIntegration(integration);await tick();},state(){return {webSearchEnabled,deepSearchEnabled,learningEnabled,stableDiffusionEnabled,musicGenerationEnabled,videoGenerationEnabled,prompt,selectedToolIds};},async existing(){history={currentId:'a',messages:{u:{id:'u',role:'user',content:'Question',parentId:null,childrenIds:['a']},a:{id:'a',role:'assistant',content:'Answer',done:true,parentId:'u',childrenIds:[],model:'local/mobile-fixture'}}};await tick();}};return()=>delete window.__suggestions;});`;
let server,browser,page;
try{
 await fs.mkdir(output,{recursive:true});
 server=await createServer({cacheDir:'node_modules/.vite-new-chat-suggestions',plugins:[{name:'new-chat-fixture',enforce:'pre',configResolved(c){c.server.proxy=undefined;},async load(id){if(id.endsWith('/src/lib/components/chat/Chat.svelte'))return(await fs.readFile(id,'utf8')).replace('recordIntegrationUse($user?.id, requestFeatures);','recordIntegrationUse($user?.id, requestFeatures); if ((window as any).__suggestionSubmitOnly) return;').replace('</script>',hook+'\n</script>');}}],server:{port:5196,strictPort:true,watch:{ignored:['**/logs/**','**/scripts/**','**/docs/**']}}});
 await server.listen();browser=await chromium.launch();
 const results=[];
 for(const width of [1440,390])for(const theme of ['dark','light']){
  const context=await browser.newContext({viewport:{width,height:900},serviceWorkers:'block'});page=await context.newPage();
  const errors=[];page.on('pageerror',e=>{errors.push(e.message);console.error('PAGEERROR',e.message);});
  await page.routeWebSocket('**/*',ws=>ws.close());
  await page.route('**/*',r=>new URL(r.request().url()).origin===origin?r.continue():r.fulfill({status:503,body:'Offline fixture'}));
  await installMobileOfflineApi(page);
  const saved=[];
  await page.route('**/users/user/settings/update',r=>{saved.push(r.request().postDataJSON());return r.fulfill({json:{}});});
  const waitSaved=async value=>{for(let i=0;i<100&&!saved.some(body=>body.ui?.enableSuggestions===value);i++)await page.waitForTimeout(50);assert(saved.some(body=>body.ui?.enableSuggestions===value),'preference is persisted');};
  await page.route('**/api/config',r=>r.fulfill({json:{name:'Neve AI',version:'3.0.20',default_models:'local/mobile-fixture',features:{auth:false,enable_websocket:false,enable_web_search:true,enable_stable_diffusion:true,enable_music_generation:true,enable_video_generation:true},file:{max_file_count:10}}}));
  await page.addInitScript(()=>{localStorage.token='fixture';localStorage.locale='pt-BR';window.__suggestionSubmitOnly=true;});
  await page.goto(origin,{waitUntil:'networkidle',timeout:120000});
  await page.waitForFunction(()=>window.__suggestions);await page.evaluate(()=>window.__suggestions.select(null));
  await page.evaluate(theme=>{document.documentElement.classList.toggle('dark',theme==='dark');document.documentElement.classList.toggle('light',theme==='light');},theme);
  const suggestions=page.locator('[data-new-chat-suggestions]');await suggestions.waitFor();
  const originalSuggestions=await suggestions.locator('[data-suggest-integration]').allTextContents();
  await page.evaluate(()=>window.__suggestionsTemporary(true));await suggestions.waitFor({state:'hidden'});
  await page.evaluate(()=>window.__suggestionsTemporary(false));await suggestions.waitFor();
  assert.deepEqual(await suggestions.locator('[data-suggest-integration]').allTextContents(),originalSuggestions,'leaving temporary chat restores the same suggestions');
  const composerShadow=await page.locator('#message-input-container').evaluate(el=>getComputedStyle(el).boxShadow);
  if(theme==='light')assert.equal(composerShadow,'none','new chat has no composer shadow in the light theme');
  else assert.notEqual(composerShadow,'none','dark theme composer shadow is preserved');
  assert.deepEqual(await suggestions.locator('[data-suggest-integration]').allTextContents(),['Crie uma imagem','Aprenda algo novo','Busque na web']);
  const alignment=await suggestions.evaluate(el=>{
   const composer=document.querySelector('#message-input-container').getBoundingClientRect(),plus=document.querySelector('#input-menu-button svg').getBoundingClientRect();
   return [...el.children].map(button=>{const r=button.getBoundingClientRect(),icon=button.querySelector('svg').getBoundingClientRect();return {left:r.left-composer.left,right:r.right-composer.right,icon:icon.left+icon.width/2-plus.left-plus.width/2};});
  });
  for(const row of alignment){assert(Math.abs(row.left)<1&&Math.abs(row.right)<1,'hover and click zone span the composer width');assert(Math.abs(row.icon)<1,'suggestion icon is aligned with Plus');}
  const firstSuggestion=suggestions.locator('[data-suggest-integration]').first();
  await firstSuggestion.hover();assert.notEqual(await firstSuggestion.evaluate(el=>getComputedStyle(el.parentElement).backgroundColor),'rgba(0, 0, 0, 0)','full row has a visible hover');
  const position=await suggestions.evaluate(el=>{
   const wrapper=el.parentElement,read=()=>{const r=wrapper.getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height};};
   const shown=read();el.style.display='none';const original=read();el.style.removeProperty('display');
   return {shown,original,gap:el.getBoundingClientRect().top-wrapper.getBoundingClientRect().bottom};
  });
  assert.deepEqual(position.shown,position.original,'suggestions do not change the original composer position or height');
  assert(position.gap>=0,'suggestions stay below the composer');
  const geometry=await suggestions.evaluate(el=>{const r=el.getBoundingClientRect();return {left:r.left,right:r.right,bottom:r.bottom,rows:[...el.children].map(c=>{const b=c.getBoundingClientRect();return {left:b.left,top:b.top,bottom:b.bottom};})};});
  assert(geometry.left>=0&&geometry.right<=width&&geometry.bottom<=900,'suggestions fit viewport');
  assert(geometry.rows.every(r=>r.left===geometry.rows[0].left),'rows share a left edge');
  assert(geometry.rows[1].top>=geometry.rows[0].bottom&&geometry.rows[2].top>=geometry.rows[1].bottom);
  await page.screenshot({path:`${output}/${width}-${theme}.png`});
  await page.evaluate(()=>window.__suggestions.openSettings());
  const suggestionToggle=page.getByRole('switch',{name:'Habilitar sugestões',exact:true});await suggestionToggle.waitFor();
  assert.equal(await suggestionToggle.getAttribute('aria-checked'),'true','suggestions default to enabled');
  const order=await page.locator('#enable-message-queue-label,#enable-suggestions-label').evaluateAll(nodes=>nodes.map(el=>({id:el.id,y:el.getBoundingClientRect().top})));
  assert.equal(order[1].id,'enable-suggestions-label');assert(order[1].y>order[0].y,'new option follows message queue');
  await suggestionToggle.click();await suggestions.waitFor({state:'hidden'});
  await page.evaluate(()=>window.__suggestionsTemporary(true));
  await page.evaluate(()=>window.__suggestionsTemporary(false));
  assert.equal(await suggestions.count(),0,'leaving temporary chat does not override disabled suggestions');
  await waitSaved(false);
  await page.waitForFunction(()=>document.querySelector('[aria-labelledby="enable-suggestions-label"]')?.getAttribute('aria-checked')==='false');
  await page.evaluate(()=>window.__suggestions.closeSettings());
  await suggestionToggle.waitFor({state:'hidden'});
  await page.evaluate(()=>window.__suggestions.openSettings());await suggestionToggle.waitFor();
  assert.equal(await suggestionToggle.getAttribute('aria-checked'),'false','disabled preference survives reopening settings');
  await suggestionToggle.click();await suggestions.waitFor();
  await waitSaved(true);
  await page.evaluate(()=>window.__suggestions.closeSettings());await suggestionToggle.waitFor({state:'hidden'});
  assert(saved.some(body=>body.ui?.enableSuggestions===false)&&saved.some(body=>body.ui?.enableSuggestions===true),'preference uses existing persistent settings API');
  const composerBackground=await page.locator('#message-input-container').evaluate(el=>getComputedStyle(el).backgroundColor);
  await page.locator('#input-menu-button').click();
  const integration=page.locator('.composer-integrations-menu button[aria-pressed]').first();await integration.waitFor();
  assert.equal(await integration.evaluate(el=>parseFloat(getComputedStyle(el).borderRadius)/parseFloat(getComputedStyle(document.documentElement).fontSize)),.5,'integration hover corners are slightly rounder');
  const menuColor=await integration.evaluate(el=>getComputedStyle(el.closest('.composer-integrations-menu')).backgroundColor);
  assert.equal(await page.locator('#message-input-container').evaluate(el=>getComputedStyle(el).backgroundColor),composerBackground,'opening More does not change the composer background');
  const expectedBackground=await page.locator('#message-input-container').evaluate((el,dark)=>{
   const probe=document.createElement('div');probe.style.backgroundColor=dark?'var(--color-gray-850)':'var(--color-gray-50)';el.append(probe);const color=getComputedStyle(probe).backgroundColor;probe.remove();return color;
  },theme==='dark');
  assert.equal(composerBackground,expectedBackground,'light composer is gray-50 and the dark surface is unchanged');
  if(theme==='light'){
   const contrast=await page.evaluate(()=>{
    const ctx=document.createElement('canvas').getContext('2d');
    return ['#message-input-container','.composer-integrations-menu'].map(selector=>{ctx.clearRect(0,0,1,1);ctx.fillStyle=getComputedStyle(document.querySelector(selector)).backgroundColor;ctx.fillRect(0,0,1,1);return ctx.getImageData(0,0,1,1).data[0];});
   });
   assert(contrast[1]<contrast[0],'More is darker than the light composer');
  }
  assert.notEqual(menuColor,theme==='dark'?'oklch(0.27 0 0)':'rgb(255, 255, 255)','More menu has a slightly darker surface');
  await integration.hover();assert.notEqual(await integration.evaluate(el=>getComputedStyle(el).backgroundColor),menuColor,'option hover stays distinct from the darker menu');
  await page.screenshot({path:`${output}/${width}-${theme}-more.png`});
  await page.keyboard.press('Escape');
  if(width>=768){
   await page.locator('#thinking-dropdown-container > button').click();
   const speed=page.locator('#reasoning-speed-control');await speed.waitFor();
   const rect=()=>speed.evaluate(el=>{const b=el.getBoundingClientRect(),s=el.querySelector('svg').getBoundingClientRect();return {x:s.x-b.x,y:s.y-b.y,width:s.width,height:s.height,buttonWidth:b.width,buttonHeight:b.height};});
   const initial=await rect();assert.equal(initial.width,21);assert.equal(initial.height,21);assert.equal(initial.buttonWidth,32);assert.equal(initial.buttonHeight,32);
   await speed.click();assert.deepEqual(await rect(),initial,'bolt geometry remains stable between speed modes');
   await speed.click();assert.deepEqual(await rect(),initial);
   await page.screenshot({path:`${output}/${width}-${theme}-speed.png`});
   await page.keyboard.press('Escape');
  }
  for(const [integration,field] of [['stable_diffusion','stableDiffusionEnabled'],['guided_learning','learningEnabled'],['web_search','webSearchEnabled']]){
   const row=page.locator(`[data-suggest-integration="${integration}"]`),bounds=await row.boundingBox();
   await row.click({position:{x:bounds.width-8,y:bounds.height/2}});await suggestions.waitFor({state:'hidden'});
   const state=await page.evaluate(()=>window.__suggestions.state());assert.equal(state[field],true);assert.equal(state.prompt,'');
   assert.equal(Object.entries(state).filter(([key,value])=>key.endsWith('Enabled')&&value).length,1,'same exclusive integration state as Plus menu');
   await page.evaluate(()=>window.__suggestions.select(null));await suggestions.waitFor();
  }
  for(const integration of ['deep_search','video_generation','music_generation']){
   await page.evaluate(i=>window.__suggestions.select(i),integration);await suggestions.waitFor({state:'hidden'});
   await page.evaluate(()=>window.__suggestions.select(null));await suggestions.waitFor();
  }
  const defaults=['Crie uma imagem','Aprenda algo novo','Busque na web'];
  const dismissFirst=suggestions.getByRole('button',{name:'Remover: Crie uma imagem'});
  await page.mouse.move(0,0);
  assert.equal(await dismissFirst.evaluate(el=>getComputedStyle(el).opacity),'0');
  await firstSuggestion.hover();
  assert.equal(await dismissFirst.evaluate(el=>getComputedStyle(el).opacity),'1');
  await dismissFirst.click();
  assert.deepEqual(await suggestions.locator('[data-suggest-integration]').allTextContents(),defaults.slice(1),'dismissal does not select or immediately replace a suggestion');
  await page.evaluate(()=>window.__suggestions.use('stable_diffusion'));await page.evaluate(()=>window.__suggestions.fresh());await suggestions.waitFor();
  assert.deepEqual(await suggestions.locator('[data-suggest-integration]').allTextContents(),defaults,'selection alone does not change ranking');
  await page.evaluate(()=>window.__suggestions.use('video_generation',''));await page.evaluate(()=>window.__suggestions.fresh());await suggestions.waitFor();
  assert.deepEqual(await suggestions.locator('[data-suggest-integration]').allTextContents(),defaults,'rejected empty submissions do not change ranking');
  for(const [integration,expected] of [
   ['video_generation',['Crie um vídeo','Crie uma imagem','Aprenda algo novo']],
   ['music_generation',['Crie uma música','Crie um vídeo','Crie uma imagem']],
   ['web_search',['Busque na web','Crie uma música','Crie um vídeo']],
   ['web_search',['Busque na web','Crie uma música','Crie um vídeo']],
   ['guided_learning',['Aprenda algo novo','Busque na web','Crie uma música']],
   ['stable_diffusion',defaults],['deep_search',defaults],[null,defaults],
   ['music_generation',['Crie uma música','Crie uma imagem','Aprenda algo novo']]
  ]){
   await page.evaluate(i=>window.__suggestions.use(i),integration);await page.evaluate(()=>window.__suggestions.fresh());await suggestions.waitFor();
   assert.deepEqual(await suggestions.locator('[data-suggest-integration]').allTextContents(),expected,`accepted ${integration} updates recency without duplicates`);
  }
  await page.reload({waitUntil:'networkidle'});await suggestions.waitFor();
  await page.evaluate(theme=>{document.documentElement.classList.toggle('dark',theme==='dark');document.documentElement.classList.toggle('light',theme==='light');},theme);
  assert.deepEqual(await suggestions.locator('[data-suggest-integration]').allTextContents(),['Crie uma música','Crie uma imagem','Aprenda algo novo'],'ranking survives reloading the page');
  await page.evaluate(()=>document.fonts.ready);await page.waitForTimeout(350);await page.mouse.move(1,1);
  await page.screenshot({path:`${output}/${width}-${theme}-recent.png`});
  await page.evaluate(()=>window.__suggestions.existing());await suggestions.waitFor({state:'hidden'});
  await page.waitForFunction(()=>{const composer=document.querySelector('#message-input-container');return composer&&!composer.closest('.chat-placeholder')&&getComputedStyle(composer).boxShadow!=='none';});
  assert.equal(await page.locator('#message-input-container').evaluate(el=>getComputedStyle(el).backgroundColor),expectedBackground,'existing chats use the same composer surface');
  assert.deepEqual(errors,[]);results.push({width,theme,geometry,position,integrations:6,existingChat:'hidden'});await context.close();
 }
 await fs.writeFile(`${output}/results.json`,JSON.stringify(results,null,2));console.log(JSON.stringify(results,null,2));
}catch(error){await page?.screenshot({path:`${output}/failed.png`});throw error;}finally{await browser?.close();await server?.close();}
