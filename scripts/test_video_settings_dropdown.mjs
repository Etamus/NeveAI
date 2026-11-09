import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
import { createServer } from 'vite';
import { chromium } from '../logs/ui-image-26/node_modules/playwright/index.mjs';
import { installMobileOfflineApi } from './fixtures/mobile-offline-api.mjs';

const origin = 'http://localhost:5189';
const output = 'logs/video-settings-dropdown';
const trigger = '#video-resolution-dropdown-container > button';
const panel = '#video-settings-panel';
const hook = `onMount(() => {
 window.__videoSettingsFixture = async () => {
  temporaryChatEnabled.set(true);
  socket.set({id:'video-settings-fixture',connected:false,on(){},off(){},emit(){},disconnect(){}});
  chatId.set('local:video-settings-fixture');
  await tick();
  const model={id:'video-settings-model',name:'Video fixture',owned_by:'openai',info:{meta:{}}};
  models.set([model]); selectedModels=[model.id];
  await tick();
  taskIds=null; files=[]; prompt=''; messageInput?.setText('');
  stableDiffusionEnabled=false; musicGenerationEnabled=false; videoGenerationEnabled=true;
  history={currentId:null,messages:{}};
  await tick();
 };
 window.__videoSettingsState = () => ({videoGenerationResolution,videoGenerationDuration,videoGenerationModel});
 window.__videoSettingsFeatures = () => getFeatures();
 return () => delete window.__videoSettingsFixture;
});`;
let server, browser;
const results=[];
try {
 await fs.mkdir(output,{recursive:true});
 server=await createServer({cacheDir:'node_modules/.vite-video-settings-dropdown',plugins:[{
  name:'video-settings-fixture',enforce:'pre',
  configResolved(config){config.server.proxy=undefined;},
  async load(id){
   if(id.endsWith('/src/lib/components/chat/Chat.svelte'))
    return (await fs.readFile(id,'utf8')).replace('</script>',hook+'\n</script>');
  }
 }],server:{port:5189,strictPort:true,watch:{ignored:['**/logs/**','**/scripts/**','**/docs/**']}}});
 await server.listen();
 browser=await chromium.launch();
 for(const [name,viewport] of [['desktop',{width:1440,height:1000}],['mobile',{width:390,height:844}]]){
  const context=await browser.newContext({viewport,serviceWorkers:'block'});
  const page=await context.newPage();
  const errors=[];
  page.on('pageerror',error=>{errors.push(error.message);console.log('PAGEERROR',error.stack);});
  await page.routeWebSocket('**/*',ws=>ws.close());
  await page.route('**/*',route=>{
   const url=new URL(route.request().url());
   if(url.origin===origin&&!/^\/(api|llamacpp|ws|dbg|openai|audio|retrieval|health|static)(\/|$)/.test(url.pathname)) return route.continue();
   return route.fulfill({status:503,body:'Blocked by video settings fixture'});
  });
  await installMobileOfflineApi(page);
  await page.addInitScript(()=>{
   localStorage.setItem('neveai.videoResolution','672p');
   localStorage.setItem('neveai.videoDuration','8s');
  });
  async function boot(){
   await page.goto(origin,{waitUntil:'networkidle',timeout:90000});
   await page.waitForFunction(()=>window.__videoSettingsFixture).catch(async error=>{
    console.log('BOOT FAILURE',errors,await page.locator('body').innerText());
    throw error;
   });
   await page.evaluate(()=>window.__videoSettingsFixture());
   await page.locator('#video-model-dropdown-container > button').waitFor({state:'visible'});
  }
  await boot();
  assert.equal(await page.locator('#video-duration-dropdown-container').count(),0);
  if(name==='mobile'){
   for(const model of ['Neve Video 1','Neve Video 1.5']){
    await page.locator('#video-model-dropdown-container > button').click();
    await page.locator('[data-composer-dropdown-anchor="video-model-dropdown-container"]').getByRole('button',{name:model,exact:true}).click();
    assert.equal(await page.locator(trigger).count(),0);
    const features=await page.evaluate(()=>window.__videoSettingsFeatures());
    assert.equal(features.video_generation_resolution,'480p');
    assert.equal(features.video_generation_duration,'5s');
    assert.deepEqual(await page.evaluate(()=>[localStorage.getItem('neveai.videoResolution'),localStorage.getItem('neveai.videoDuration')]),['672p','8s']);
    for(const theme of ['dark','light']){
     await page.evaluate(theme=>document.documentElement.classList.toggle('dark',theme==='dark'),theme);
     await page.screenshot({path:`${output}/${name}-${theme}-${model.endsWith('1.5')?'vdn':'original'}.png`});
    }
   }
   await page.setViewportSize({width:1440,height:1000});
   await page.locator(trigger).waitFor({state:'visible'});
   assert.match(await page.locator(trigger).innerText(),/672p\s*•\s*8s/);
   assert.equal((await page.evaluate(()=>window.__videoSettingsFeatures())).video_generation_resolution,'672p');
   await page.locator(trigger).click();
   await page.locator(panel).waitFor({state:'visible'});
   await page.setViewportSize(viewport);
   await page.locator(trigger).waitFor({state:'detached'});
   assert.equal(await page.locator(panel).count(),0,'Resizing must remove a portaled desktop panel');
   assert.equal((await page.evaluate(()=>window.__videoSettingsFeatures())).video_generation_duration,'5s');
   await boot();
   assert.equal(await page.locator(trigger).count(),0);
   assert.equal((await page.evaluate(()=>window.__videoSettingsFeatures())).video_generation_resolution,'480p');
   assert.deepEqual(errors,[]);
   results.push({name,mobileDefaults:true,desktopPreferencesPreserved:true,resizeAndReload:true});
   await context.close();
   continue;
  }
  const chevron=await page.locator(trigger+' svg').evaluate(el=>({viewBox:el.getAttribute('viewBox'),path:el.querySelector('path').getAttribute('d'),width:el.getBoundingClientRect().width,height:el.getBoundingClientRect().height}));
  const modelChevron=await page.locator('#video-model-dropdown-container > button > svg').evaluate(el=>({viewBox:el.getAttribute('viewBox'),path:el.querySelector('path').getAttribute('d'),width:el.getBoundingClientRect().width,height:el.getBoundingClientRect().height}));
  assert.deepEqual(chevron,modelChevron,'Chevron must exactly match the adjacent selector');
  for(const model of ['Neve Video 1','Neve Video 1.5']){
   await page.locator('#video-model-dropdown-container > button').click();
   await page.locator('[data-composer-dropdown-anchor="video-model-dropdown-container"]').getByRole('button',{name:model,exact:true}).click();
   await page.locator(trigger).click();
   await page.locator(panel).waitFor({state:'visible'});
   const slider=page.locator(panel).getByRole('slider');
   assert.equal(await page.locator(panel).getByRole('button',{name:/1080p/}).count(),0);
   assert.equal(await page.locator(trigger+' svg').count(),1,'Only the chevron should remain');
   assert.equal(await page.locator(panel+' .effort-dots span').count(),4);
   for(const [index,[resolution,duration]] of [['480p','5s'],['480p','8s'],['672p','5s'],['672p','8s']].entries()){
    const track=await slider.boundingBox();
    await page.mouse.click(track.x+12+(track.width-24)*index/3,track.y+track.height/2);
    assert(await page.locator(panel).isVisible());
    assert.equal(await slider.inputValue(),String(index));
    assert.equal(await slider.getAttribute('aria-valuetext'),`${resolution} • ${duration}`);
    assert.match(await page.locator(trigger).innerText(),new RegExp(`${resolution}\\s*•\\s*${duration}`));
    const saved=await page.evaluate(()=>[localStorage.getItem('neveai.videoResolution'),localStorage.getItem('neveai.videoDuration')]);
    assert.deepEqual(saved,[resolution,duration]);
    assert.deepEqual(await page.evaluate(()=>window.__videoSettingsState()),{
     videoGenerationResolution:resolution,videoGenerationDuration:duration,
     videoGenerationModel:model==='Neve Video 1'?'minimax_h3':'vdn_h3'
    });
   }
   await slider.focus();
   await page.keyboard.press('Home');
   assert.equal(await slider.inputValue(),'0');
   await page.keyboard.press('ArrowRight');
   assert.equal(await slider.getAttribute('aria-valuetext'),'480p • 8s');
   await page.keyboard.press('End');
   assert.equal(await slider.inputValue(),'3');
   const bounds=await page.locator(panel).boundingBox();
   assert(bounds.x>=0&&bounds.y>=0&&bounds.x+bounds.width<=viewport.width+1&&bounds.y+bounds.height<=viewport.height+1);
   for(const theme of ['dark','light']){
    await page.evaluate(theme=>document.documentElement.classList.toggle('dark',theme==='dark'),theme);
    await page.waitForTimeout(200);
    await page.screenshot({path:`${output}/${name}-${theme}-${model.endsWith('1.5')?'vdn':'original'}.png`});
   }
   await page.keyboard.press('Escape');
   assert.equal(await page.locator(panel).count(),0);
   assert(await page.locator(trigger).evaluate(el=>el===document.activeElement));
   await page.locator(trigger).click();
   await page.mouse.click(viewport.width-5,100);
   await page.locator(panel).waitFor({state:'detached'});
   results.push({name,model,bounds,combinations:4});
  }
  await boot();
  assert.match(await page.locator(trigger).innerText(),/672p\s*•\s*8s/);
  assert.deepEqual(errors,[]);
  await context.close();
 }
 await fs.writeFile(`${output}/results.json`,JSON.stringify(results,null,2));
 console.log(JSON.stringify(results,null,2));
}finally{await browser?.close();await server?.close();}
