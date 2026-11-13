import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {chromium} from '../logs/ui-image-26/node_modules/playwright/index.mjs';

const browser=await chromium.launch();
const results=[];
try{
 for(const mobile of [false,true])for(const theme of ['light','dark']){
  const context=await browser.newContext({viewport:mobile?{width:390,height:844}:{width:1440,height:1000}});
  const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.addInitScript(theme=>{localStorage.setItem('theme',theme);localStorage.setItem('llamacpp_load_context','auto');localStorage.setItem('neveai.language','pt-BR');},theme);
  await page.route('**/api/version/updates',route=>route.fulfill({json:{current_tag:'v3.1.83',latest_tag:'v3.2.0',neve_update_available:true,llama_cpp:{current_tag:'b100',latest_tag:'b101',update_available:true}}}));
  await page.route('**/api/updater/state',route=>route.fulfill({json:{status:'idle'}}));
  await page.goto('http://localhost:8080',{waitUntil:'networkidle'});
  await page.evaluate(theme=>document.documentElement.classList.toggle('dark',theme==='dark'),theme);
  const icons=await page.evaluate(()=>{
   const model=document.querySelector('button[aria-label="Models"] svg path');
   const neighbor=document.querySelector('#chat-parameters-button svg rect') || document.querySelector('#temporary-chat-button svg path');
   return [model,neighbor].map(node=>({stroke:getComputedStyle(node).stroke,width:getComputedStyle(node).strokeWidth}));
  });
  assert.equal(icons[0].stroke,icons[1].stroke);assert.equal(icons[0].width,'1.5px');
  assert.equal(await page.locator('button[aria-label="Models"] svg path').count(),2);
  await page.locator('#model-selector-0-button').click();
  await page.getByRole('button',{name:'Predefinições',exact:true}).click();
  assert.equal(await page.locator('#load-setting-context').innerText(),'Dinâmico');
  await page.keyboard.press('Escape');
  const menu=async()=>{
   const user=page.getByRole('button',{name:/Usuário|User menu/i});
   if(!await user.isVisible())await page.locator('.chat-navbar-sidebar button').click();
   await user.click();
  };
  const samples=[];
  async function open(item,expected){
   await menu();
   await page.evaluate(()=>{
    window.__settingsSamples=[];
    const sample=()=>{
     const shell=document.querySelector('.settings-shell');const modal=shell?.closest('[role="dialog"]');
     if(modal?.getAttribute('aria-hidden')==='false' && getComputedStyle(modal).display!=='none'){
      const tab=shell.querySelector('[role="tab"][aria-selected="true"]')?.getAttribute('aria-controls');
      window.__settingsSamples.push(tab);
     }
    };
    window.__settingsObserver=new MutationObserver(sample);window.__settingsObserver.observe(document.body,{subtree:true,childList:true,attributes:true,attributeFilter:['class','aria-hidden','aria-selected']});
    window.__settingsFrame=()=>{sample();window.__settingsRaf=requestAnimationFrame(window.__settingsFrame)};window.__settingsFrame();
   });
   await page.getByRole('menuitem').filter({hasText:item}).click();
   await page.locator(`[role="tab"][aria-controls="tab-${expected}"][aria-selected="true"]`).waitFor({state:'attached'});
   await page.waitForTimeout(220);
   const frames=await page.evaluate(()=>{window.__settingsObserver.disconnect();cancelAnimationFrame(window.__settingsRaf);return window.__settingsSamples;});
   assert(frames.length>0);assert(frames.every(value=>value===`tab-${expected}`),`${item}: ${JSON.stringify(frames)}`);
   samples.push({item,first:frames[0],frames:frames.length});
  }
  async function close(){await page.keyboard.press('Escape');await page.locator('.settings-shell').waitFor({state:'hidden'});}
  await open('Configurações','general');
  const generalGap=mobile?0:await page.evaluate(()=>{
   const first=document.getElementById('stream-response-label').parentElement.getBoundingClientRect();
   const second=document.getElementById('enable-message-queue-label').parentElement.getBoundingClientRect();
   return second.top-first.bottom;
  });
  await page.getByRole('tab',{name:'Atualizações',exact:true}).click();
  await close();
  await menu();assert.equal(await page.getByRole('menuitem').filter({hasText:'Sobre'}).count(),0);await page.keyboard.press('Escape');
  await open('Personalização','personalization');await close();
  await open('Configurações','general');
  if(mobile)await page.getByRole('tab',{name:'Notificações',exact:true}).click();
  else await page.getByRole('tab',{name:'Notificações',exact:true}).click();
  for(const label of ['Notificar status dos modelos','Notificar downloads em andamento','Notificar falhas de sistema'])assert(await page.getByRole('switch',{name:label,exact:true}).isVisible());
  const gaps=await page.locator('#tab-notifications > div').evaluateAll(rows=>rows.slice(1).map((row,i)=>row.getBoundingClientRect().top-rows[i].getBoundingClientRect().bottom));
  assert(gaps.slice(1).every(gap=>Math.abs(gap-generalGap)<0.1));
  assert(Math.abs(gaps[0]-await page.evaluate(()=>parseFloat(getComputedStyle(document.documentElement).fontSize)*0.5))<0.05);
  assert.equal(await page.locator('#notification-master-label').evaluate(node=>getComputedStyle(node).fontWeight),'500');
  await page.screenshot({path:`logs/settings-opening-${mobile?'mobile':'desktop'}-${theme}.png`});
  assert.deepEqual(errors,[]);results.push({mobile,theme,icons,samples,errors});await context.close();
 }
 await fs.writeFile('logs/settings-opening-results.json',JSON.stringify(results,null,2));console.log(JSON.stringify(results));
}finally{await browser.close();}
