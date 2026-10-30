import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
import { createServer } from 'vite';
import { chromium } from '../logs/ui-image-26/node_modules/playwright/index.mjs';
import { installMobileOfflineApi } from './fixtures/mobile-offline-api.mjs';

const output = process.env.MOBILE_CONTROLS_DIR ?? 'logs/mobile-controls-20261028';
const composerHook = `onMount(()=>{
 window.__mobileComposer={
  state:()=>({reasoningLevel,thinkingEnabled,thinkingExtendedEnabled,thinkingUnlimitedEnabled,effortBased,isCompact}),
  model:(effort)=>{const model={id:'local/mobile-fixture',name:'Mobile test model',owned_by:'llamacpp',info:{meta:{}},llamacpp:{reasoning_control:effort?'effort':'toggle'}};models.set([model,...$models.filter(m=>m.id!==model.id)]);selectedModels=[model.id];},
  integration:value=>{webSearchEnabled=value;},
 };
 return()=>delete window.__mobileComposer;
});`;
let server, browser;
const results = [];
try {
 await fs.mkdir(output,{recursive:true});
 server=await createServer({plugins:[{name:'mobile-controls-fixture',enforce:'pre',async load(id){
  if(id.endsWith('/src/lib/components/chat/MessageInput.svelte'))return(await fs.readFile(id,'utf8')).replace('</script>',composerHook+'\n</script>');
 }}],server:{port:5188,strictPort:true,watch:{ignored:['**/logs/**','**/scripts/**','**/docs/**']}}});
 await server.listen();browser=await chromium.launch();
 for(const width of (process.env.MOBILE_CONTROLS_WIDTHS??'320,390,430,639,640,767,768,1440').split(',').map(Number))for(const dark of [false,true]){
  const mobile=width<768,page=await browser.newPage({viewport:{width,height:Number(process.env.MOBILE_CONTROLS_HEIGHT??1000)},hasTouch:mobile}),errors=[];
  page.setDefaultTimeout(15000);page.on('pageerror',e=>{errors.push(e.message);console.log(e.stack);});
  await page.addInitScript(()=>localStorage.setItem('neveai.reasoningLevel','3'));
  if(process.env.MOBILE_OFFLINE)await installMobileOfflineApi(page);
  else await page.route('**/api/**',r=>r.request().method()==='GET'||r.request().url().includes('/auths/')?r.continue():r.fulfill({json:{}}));
  await page.goto('http://localhost:5188',{waitUntil:'networkidle',timeout:90000});
  await page.waitForFunction(()=>window.__mobileComposer);await page.evaluate(async dark=>{document.documentElement.classList.toggle('dark',dark);await document.fonts.ready;window.__mobileComposer.model(false);},dark);
  await page.waitForTimeout(300);
  const state=()=>page.evaluate(()=>window.__mobileComposer.state());
  const checkGauge=async()=>{if(!mobile)return;const box=await page.locator('.mobile-reasoning-toggle').evaluate(e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return{width:r.width,height:r.height,padding:s.padding,borderRadius:s.borderRadius};});assert.deepEqual(box,{width:38,height:38,padding:'0px',borderRadius:'50%'});};
  const initial=await state();assert.equal(initial.reasoningLevel,mobile?1:3);assert.equal(initial.isCompact,true);
  const input=page.locator('#chat-input');await input.waitFor();
  const compact=await page.locator('#message-input-container').boundingBox();
  await checkGauge();
  if(mobile){
   const gauge=page.locator('.mobile-reasoning-toggle');assert.equal(await gauge.count(),1);
   await gauge.click();assert.equal((await state()).reasoningLevel,0);assert.equal((await state()).thinkingEnabled,false);
   await gauge.click();assert.equal((await state()).reasoningLevel,1);assert.equal((await state()).thinkingExtendedEnabled,false);
   assert.equal((await state()).thinkingUnlimitedEnabled,false);assert.equal(await page.locator('#reasoning-dropdown').count(),0);
   await page.evaluate(()=>window.__mobileComposer.model(true));await page.waitForTimeout(100);
   assert.equal((await state()).effortBased,true);await gauge.click();assert.equal((await state()).reasoningLevel,0);
   assert.match(await gauge.getAttribute('aria-label'),/Leve|Light/i);await gauge.click();
   assert.equal((await state()).reasoningLevel,1);
  }else{
   assert.equal(await page.locator('.mobile-reasoning-toggle').count(),0);
   await page.locator('#thinking-dropdown-container > button').click();assert(await page.locator('#reasoning-dropdown').isVisible());await page.keyboard.press('Escape');
  }
  await input.fill('A short message');await page.waitForTimeout(250);assert.equal((await state()).isCompact,true);
  if(mobile){const boxes=await page.evaluate(()=>['#input-menu-button','#chat-input','#thinking-dropdown-container','#send-message-button'].map(s=>{const r=document.querySelector(s).getBoundingClientRect();return{x:r.x,y:r.y,w:r.width,h:r.height};}));assert(Math.max(...boxes.map(b=>b.y+b.h/2))-Math.min(...boxes.map(b=>b.y+b.h/2))<3,JSON.stringify(boxes));}
  await input.fill('A longer paragraph with words and spaces. '.repeat(20));await page.waitForTimeout(350);
  assert.equal((await state()).isCompact,false);const expanded=await page.locator('#message-input-container').boundingBox();assert(expanded.height>compact.height);
  await checkGauge();
  if(mobile){await page.locator('#input-menu-button').click();const longMenu=page.locator('.composer-integrations-menu');await longMenu.waitFor();assert.equal(await longMenu.getAttribute('data-side'),'top');await page.keyboard.press('Escape');}
  await input.click();await page.keyboard.press('Control+A');await page.keyboard.press('Backspace');await page.waitForTimeout(350);assert.equal((await state()).isCompact,true);
  await page.locator('#input-menu-button').click();const menu=page.locator('.composer-integrations-menu');await menu.waitFor();await page.waitForTimeout(150);
  const menuBox=await menu.boundingBox(),border=await menu.evaluate(e=>getComputedStyle(e).borderTopWidth);
  assert.equal(await menu.locator('button').filter({has:page.locator('[role="switch"]')}).count(),mobile?0:1);
  if(mobile){assert.equal(border,'0px');assert(menuBox.width<=261);assert(menuBox.x<40,JSON.stringify(menuBox));const plus=await page.locator('#input-menu-button').boundingBox();assert(plus.y-menuBox.y-menuBox.height>=0&&plus.y-menuBox.y-menuBox.height<=12,JSON.stringify({plus,menuBox}));assert.equal(await menu.evaluate(e=>getComputedStyle(e,'::-webkit-scrollbar').display),'none');}
  await page.screenshot({path:`${output}/composer-menu-${width}-${dark?'dark':'light'}.png`});await page.keyboard.press('Escape');
  await page.evaluate(()=>window.__mobileComposer.integration(true));await page.waitForTimeout(250);assert.equal((await state()).isCompact,false);
  await checkGauge();
  if(mobile){await page.locator('#input-menu-button').click();await menu.waitFor();await page.waitForTimeout(150);const box=await menu.boundingBox(),plus=await page.locator('#input-menu-button').boundingBox();assert(plus.y-box.y-box.height>=0&&plus.y-box.y-box.height<=12,JSON.stringify({box,plus}));await page.keyboard.press('Escape');}
  await page.evaluate(()=>window.__mobileComposer.integration(false));await page.waitForTimeout(250);assert.equal((await state()).isCompact,true);
  const modelButton=page.locator('[id^="model-selector-"][id$="-button"]').first();await modelButton.click();const modelMenu=page.locator('[data-model-selector-content]');await modelMenu.waitFor();
  const z=await modelMenu.evaluate(e=>Number(getComputedStyle(e).zIndex));assert.equal(z,mobile?1000000001:40);
  if(mobile){
   const overlap=await modelMenu.evaluate(e=>{const r=e.getBoundingClientRect(),toast=document.createElement('div');toast.id='toast-overlap-fixture';toast.style.cssText=`position:fixed;z-index:1000000000;left:${r.left+8}px;top:${r.top+8}px;width:80px;height:80px;background:gray`;document.body.append(toast);return e.contains(document.elementFromPoint(r.left+20,r.top+20));});assert(overlap,'Toast covers the model menu');await page.evaluate(()=>document.querySelector('#toast-overlap-fixture').remove());
  }
  await page.keyboard.press('Escape');await page.screenshot({path:`${output}/composer-${width}-${dark?'dark':'light'}.png`});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);assert.deepEqual(errors,[]);
  results.push({width,dark,initial,compact,expanded,menuBox,border,z});await page.close();console.log('PASS '+width+' '+dark);
 }
 await fs.writeFile(output+'/composer-results.json',JSON.stringify(results,null,2));
}catch(error){for(const page of browser?.contexts().flatMap(c=>c.pages())??[])await page.screenshot({path:output+'/failure.png'}).catch(()=>{});throw error;}
finally{await browser?.close();await server?.close();}
