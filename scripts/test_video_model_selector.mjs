import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
import {createServer} from 'vite';
import {chromium} from '../logs/ui-image-26/node_modules/playwright/index.mjs';
import {installMobileOfflineApi} from './fixtures/mobile-offline-api.mjs';

const origin = 'http://localhost:5188';
const output = 'logs/video-model-selector';
const panelSelector = '[data-composer-dropdown-anchor="video-model-dropdown-container"]';
const triggerSelector = '#video-model-dropdown-container > button';
const chatHook = `onMount(() => {
 const fixtureSocket = (connected) => ({id:'video-selector-fixture',connected,on(){},off(){},emit(){},disconnect(){}});
 window.__videoFixture = {
  async seed(kind = 'empty') {
   temporaryChatEnabled.set(true);
   socket.set(fixtureSocket(false));
   chatId.set('local:video-selector-fixture');
   await tick();
   const model = {id:'video-selector-model',name:'Video fixture',owned_by:'openai',info:{meta:{}}};
   models.set([model]); selectedModels=[model.id];
   await tick();
   taskIds=null; files=[]; prompt=''; messageInput?.setText('');
   stableDiffusionEnabled=false; musicGenerationEnabled=false; videoGenerationEnabled=true;
   window.__videoWaitingForSocket=false;
   window.__videoActionError=null;
   window.__videoActionDone=true;
   if (kind === 'empty') history={currentId:null,messages:{}};
   else {
    const status = {action:'video_generation',done:true,resolution:'672p',duration:'8s',aspect_ratio:'9:16',
     ...(kind === 'legacy' ? {} : {video_generation_model: kind === 'unknown' ? 'obsolete' : 'vdn_h3'})};
    history={currentId:'reply',messages:{
     original:{id:'original',parentId:null,childrenIds:['reply'],role:'user',content:'Fixture video prompt',models:[model.id]},
     reply:{id:'reply',parentId:'original',childrenIds:[],role:'assistant',content:'Fixture result',done:true,model:model.id,statusHistory:[status]}
    }};
   }
   await tick();
  },
  submit() { window.__videoActionDone=false; void submitPrompt('Fixture video prompt').catch(error => window.__videoActionError=String(error)).finally(() => window.__videoActionDone=true); },
  regenerate() { window.__videoActionDone=false; void regenerateResponse(history.messages.reply).catch(error => window.__videoActionError=String(error)).finally(() => window.__videoActionDone=true); },
  release() { socket.set(fixtureSocket(true)); },
  state() { return structuredClone({videoGenerationModel,videoGenerationEnabled,history,submittingPrompt}); }
  ,async toggle(kind) { stableDiffusionEnabled=kind==='image'; videoGenerationEnabled=kind==='video'; musicGenerationEnabled=false; await tick(); }
 };
 return () => delete window.__videoFixture;
});`;
const editHook = `auditMount(() => {
 window.__editVideoRequest = () => { window.__videoActionDone=false; void editMessage('original',{content:'Edited fixture video prompt',files:[]})
  .catch(error => window.__videoActionError=String(error)).finally(() => window.__videoActionDone=true); };
 return () => delete window.__editVideoRequest;
});`;

let server, browser;
const results = [];
try {
 await fs.mkdir(output, {recursive:true});
 server = await createServer({
  cacheDir:'node_modules/.vite-video-model-selector',
  plugins:[{
   name:'video-model-selector-fixture', enforce:'pre',
   configResolved(config) { config.server.proxy = undefined; },
   async load(id) {
    if (id.endsWith('/src/lib/components/chat/Chat.svelte')) {
     const source = await fs.readFile(id,'utf8');
     assert(source.includes('const waitForChatSocketReady = async'));
     return source.replace('</script>',chatHook+'\n</script>')
      .replace(/(const waitForChatSocketReady = async \([^)]*\)\s*(?::[^=]*?)?=> \{)/,
       '$1\nwindow.__videoWaitingForSocket=true;');
    }
    if (id.endsWith('/src/lib/components/chat/Messages.svelte')) {
     const source = (await fs.readFile(id,'utf8')).replace('<script lang="ts">',
      '<script lang="ts">\nimport {onMount as auditMount} from "svelte";');
     const at = source.lastIndexOf('</script>');
     return source.slice(0,at)+editHook+source.slice(at);
    }
   }
  }],
  server:{port:5188,strictPort:true,watch:{ignored:['**/logs/**','**/scripts/**','**/docs/**']}}
 });
 await server.listen();
 browser = await chromium.launch();
 for (const [name,viewport] of [['desktop',{width:1440,height:1000}],['mobile',{width:390,height:844}]]) {
  const context = await browser.newContext({viewport,serviceWorkers:'block'});
  try {
   const page = await context.newPage();
   page.setDefaultTimeout(15000);
   const errors = [], captured = [], forbidden = [];
   page.on('pageerror',error => { errors.push(error.message); console.error('PAGEERROR',error.message); });
   page.on('console',message => { if (message.type() === 'error') console.error('CONSOLE',message.text()); });
   // No network WebSocket, GPU request, backend call or chat persistence can escape this fixture.
   await page.routeWebSocket('**/*', ws => ws.close());
   await page.route('**/*',route => {
    const url = new URL(route.request().url());
    if (url.origin === origin && !/^\/(api|llamacpp|ws|dbg|openai|audio|retrieval|health|static)(\/|$)/.test(url.pathname)) return route.continue();
    forbidden.push(route.request().method()+' '+url.href);
    console.error('BLOCKED',route.request().method(),url.href);
    return route.fulfill({status:503,body:'Blocked by video selector fixture'});
   });
   await installMobileOfflineApi(page);
   await page.route('**/llamacpp/models/loaded',route => route.fulfill({json:{models:[{id:'local/fixture',filename:'fixture.gguf',n_ctx:8192}]}}));
   await page.route('**/llamacpp/models/unload',route => {
    forbidden.push('unload-on-toggle');return route.fulfill({json:{status:'unloaded'}});
   });
   await page.route('**/api/v1/chats/**',route => {
    if (route.request().method() !== 'GET') forbidden.push('chat-persistence '+route.request().url());
    return route.fulfill({json:[]});
   });
   await page.route('**/api/chat/completions',async route => {
    captured.push(route.request().postDataJSON());
    await route.fulfill({json:{task_id:'video-selector-intercepted'}});
   });
   async function boot() {
    console.log(name,'boot');
    await page.goto(origin,{waitUntil:'networkidle',timeout:90000});
    await page.waitForFunction(() => window.__videoFixture);
    await page.evaluate(() => window.__videoFixture.seed());
    await page.locator(triggerSelector).waitFor({state:'visible'});
   }
   async function seed(kind) {
    console.log(name,'seed',kind);
    await page.evaluate(kind => window.__videoFixture.seed(kind),kind);
    await page.locator(triggerSelector).waitFor({state:'visible'});
   }
   async function select(label) {
    await page.locator(triggerSelector).click();
    const panel = page.locator(panelSelector);
    await panel.waitFor({state:'visible'});
    const removed = await panel.getByRole('button',{name:label,exact:true}).evaluate(async (button,selector) => {
     button.click();
     await new Promise(requestAnimationFrame);
     return !document.querySelector(selector);
    },panelSelector);
    assert(removed,'Dropdown persisted after the next frame (stale exit animation)');
    assert.equal((await page.locator(triggerSelector).innerText()).trim(),label);
   }
   async function assertRequest(action,expected,changeTo) {
    console.log(name,action,expected);
    const count = captured.length;
    await page.evaluate(action => {
     if (action === 'edit') window.__editVideoRequest();
     else window.__videoFixture[action]();
    },action);
    await page.waitForFunction(() => window.__videoWaitingForSocket || window.__videoActionError, null, {timeout:15000});
    assert.equal(await page.evaluate(() => window.__videoActionError),null);
    assert.equal(captured.length,count,'Request escaped the disconnected fixture socket');
    await select(changeTo);
    const response = page.waitForResponse(response => response.url().endsWith('/api/chat/completions'),{timeout:15000});
    await page.evaluate(() => window.__videoFixture.release());
    await page.waitForFunction(() => !window.__videoFixture.state().submittingPrompt && !window.__videoActionError);
    await response;
    await page.waitForFunction(() => window.__videoActionDone);
    assert.equal(await page.evaluate(() => window.__videoActionError),null);
    assert.equal(captured.length,count+1,'Expected exactly one intercepted video request');
    const body = captured[count];
    assert.equal(body.features.video_generation,true);
    assert.equal(body.features.video_generation_model,expected);
    if(name==='mobile'){
     assert.equal(body.features.video_generation_resolution,'480p');
     assert.equal(body.features.video_generation_duration,'5s');
     if(action==='submit'){
      assert.equal(body.parent_message.video_generation_features.video_generation_resolution,'480p');
      assert.equal(body.parent_message.video_generation_features.video_generation_duration,'5s');
     }
    }
    assert.equal(body.background_tasks.follow_up_generation,false);
    return body;
   }

   await boot();
   for(const kind of ['image','video','none','video']) {
    await page.evaluate(kind => window.__videoFixture.toggle(kind),kind);
    await page.waitForTimeout(150);
   }
   assert.deepEqual(forbidden,[],'Selecting a media integration must not unload the LLM');
   assert.equal((await page.locator(triggerSelector).innerText()).trim(),'Neve Video 1');
   await page.locator(triggerSelector).click();
   const panel = page.locator(panelSelector);
   await panel.waitFor({state:'visible'});
   assert.deepEqual((await panel.getByRole('button').allTextContents()).map(label => label.trim()),['Neve Video 1','Neve Video 1.5']);
   const bounds = await panel.boundingBox();
   assert(bounds && bounds.x>=0 && bounds.y>=0 && bounds.x+bounds.width<=viewport.width && bounds.y+bounds.height<=viewport.height);
   await page.screenshot({path:`${output}/${name}-open.png`});
   if(name==='desktop'){
    await page.locator('#video-resolution-dropdown-container > button').click();
    assert.equal(await panel.count(),0,'Opening resolution must dismiss the model selector immediately');
    await page.locator('#video-resolution-dropdown-container > button').click();
   }else{
    assert.equal(await page.locator('#video-resolution-dropdown-container').count(),0);
    await page.mouse.click(viewport.width-5,100);
    await panel.waitFor({state:'detached'});
   }
   await select('Neve Video 1.5');
   assert.equal(await page.evaluate(() => localStorage.getItem('neveai.videoModel')),'vdn_h3');
   assert.equal(await page.evaluate(() => document.documentElement.scrollWidth>innerWidth),false);
   await page.screenshot({path:`${output}/${name}-selected.png`});
   await boot();
   assert.equal((await page.locator(triggerSelector).innerText()).trim(),'Neve Video 1.5','Selection must survive reload');

   const sent = await assertRequest('submit','vdn_h3','Neve Video 1');
   assert.equal(sent.parent_message.video_generation_features.video_generation_model,'vdn_h3');
   await seed('status');
   await select('Neve Video 1');
   const regenerated = await assertRequest('regenerate','vdn_h3','Neve Video 1');
   assert.equal(regenerated.features.video_generation_resolution,name==='mobile'?'480p':'672p');
   assert.equal(regenerated.features.video_generation_duration,name==='mobile'?'5s':'8s');
   await seed('status');
   await page.waitForFunction(() => window.__editVideoRequest);
   await select('Neve Video 1');
   const edited = await assertRequest('edit','vdn_h3','Neve Video 1');
   assert(edited.messages.some(message => message.content?.includes('Edited fixture video prompt')));
   for (const kind of ['legacy','unknown']) {
    await seed(kind);
    await select('Neve Video 1.5');
    await assertRequest('regenerate','minimax_h3','Neve Video 1.5');
   }
   for (const saved of ['obsolete','']) {
    await page.evaluate(saved => {localStorage.setItem('neveai.videoModel',saved);sessionStorage.clear();},saved);
    await boot();
    assert.equal((await page.locator(triggerSelector).innerText()).trim(),'Neve Video 1');
   }
   assert.deepEqual(errors,[]);
   assert.deepEqual(forbidden,[]);
   results.push({name,viewport,requests:captured.map(body => body.features.video_generation_model),
    labels:true,immediateClose:true,responsive:true,persistence:true,frozenRequest:true,
    statusFieldRestoration:true,edit:true,legacyDefaults:true,actualGenerations:0,chatPersistence:0,errors});
  } catch (error) {
   for (const page of context.pages()) {
    await page.screenshot({path:`${output}/${name}-failure.png`}).catch(() => {});
    console.error(name,await page.evaluate(() => ({error:window.__videoActionError,state:window.__videoFixture?.state(),waiting:window.__videoWaitingForSocket})).catch(() => null));
   }
   throw error;
  } finally { await context.close(); }
 }
 await fs.writeFile(`${output}/results.json`,JSON.stringify(results,null,2));
 console.log('PASS video model selector: '+JSON.stringify(results));
} catch(error) {
 for (const [index,page] of (browser?.contexts().flatMap(context => context.pages())??[]).entries()) {
  await page.screenshot({path:`${output}/failure-${index}.png`}).catch(() => {});
 }
 throw error;
} finally {
 await browser?.close();
 await server?.close();
}
