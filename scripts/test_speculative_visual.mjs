import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {chromium} from '../logs/ui-image-26/node_modules/playwright/index.mjs';
import {installMobileOfflineApi} from './fixtures/mobile-offline-api.mjs';

const browser=await chromium.launch(),results=[];
try{
 for(const [width,height] of [[1440,1000],[390,1000],[1440,420],[390,420]])for(const theme of ['dark','light']){
  const page=await browser.newPage({viewport:{width,height}}),errors=[];
  await installMobileOfflineApi(page);
  await page.addInitScript(theme=>{localStorage.setItem('neveai.language','pt-BR');localStorage.setItem('theme',theme)},theme);
  page.on('pageerror',e=>errors.push(e.message));
  await page.goto('http://127.0.0.1:8080',{waitUntil:'networkidle',timeout:90000});
  async function settings(){await page.locator('#model-selector-0-button').click();await page.getByRole('button',{name:'Predefinições',exact:true}).click();}
  await settings();
  const method=page.locator('#load-setting-speculative-method');
  const cache=page.locator('#load-setting-cache');
  await method.waitFor();assert.equal(await method.innerText(),'Dinâmico');
  const methodBox=await method.boundingBox(),cacheBox=await cache.boundingBox();
  assert.equal(methodBox.width,cacheBox.width);assert.equal(methodBox.height,cacheBox.height);
  const rootFontSize=await page.evaluate(()=>parseFloat(getComputedStyle(document.documentElement).fontSize));
  assert(Math.abs(methodBox.width-4.625*rootFontSize)<.1);
  assert(methodBox.y>cacheBox.y);
  assert.equal(await method.evaluate(e=>getComputedStyle(e).borderRadius),await cache.evaluate(e=>getComputedStyle(e).borderRadius));
  const compaction=page.locator('#load-setting-compaction'),gpu=page.locator('#load-setting-gpu-priority');
  assert((await compaction.boundingBox()).y<(await gpu.boundingBox()).y);
  const panel=await page.locator('[data-model-load-settings]').boundingBox(),gpuBox=await gpu.boundingBox();
  if(height>700)assert(gpuBox.y+gpuBox.height<=panel.y+panel.height,'The last setting must fit when viewport space is available');
  assert.equal(await page.locator('#load-setting-compaction-label').innerText(),'Compactação de memória');
  for(const expected of ['Ngram','MTP','Dinâmico']){
   await method.click();assert.equal(await method.innerText(),expected);
   assert.equal(await page.evaluate(()=>localStorage.getItem('llamacpp_speculative_enabled')),'false');
  }
  await page.screenshot({path:`logs/speculative-presets-${width}-${height}-${theme}.png`});
  await page.keyboard.press('Escape');
  if(width>768){
   async function reasoning(){await page.locator('#thinking-dropdown-container > button').click();await page.locator('#reasoning-dropdown').waitFor();}
   await reasoning();const speed=page.locator('#reasoning-speed-control');
   assert.equal(await speed.getAttribute('data-mode'),'normal');
   assert.equal(await speed.getAttribute('aria-label'),'Velocidade: Normal');
   async function centeredIcon(){
    const error=await speed.evaluate(button=>{
     const b=button.getBoundingClientRect(),s=button.querySelector('svg').getBoundingClientRect();
     return {x:Math.abs(b.x+b.width/2-s.x-s.width/2),y:Math.abs(b.y+b.height/2-s.y-s.height/2)};
    });
    assert(error.x<.1&&error.y<.1,JSON.stringify(error));
    assert.equal(await speed.locator('.acceleration-indicator').count(),0);
   }
   await centeredIcon();
   assert.equal(await speed.locator('svg').getAttribute('fill'),'none');
   await speed.click();assert.equal(await speed.getAttribute('data-mode'),'speculative');
   assert.equal(await speed.getAttribute('aria-label'),'Velocidade: Especulativa');
   await centeredIcon();
   assert.equal(await speed.locator('svg').getAttribute('fill'),'currentColor');
   assert.equal(await speed.locator('path').getAttribute('d'),await page.locator('[data-acceleration-icon] path').getAttribute('d'));
   assert.equal(await speed.evaluate(e=>getComputedStyle(e).color),'rgb(59, 130, 246)');
   const range=page.locator('#reasoning-dropdown input[type=range]');
   await range.evaluate(e=>{e.value='2';e.dispatchEvent(new Event('input',{bubbles:true}))});
   const particle=page.locator('.effort-fluid span').first();await particle.waitFor();
   const first=await particle.evaluate(e=>getComputedStyle(e).transform);await page.waitForTimeout(120);
   assert.notEqual(await particle.evaluate(e=>getComputedStyle(e).transform),first,'Particles must really animate');
   assert.equal(await page.locator('.fast-flow').count(),0);
   await page.screenshot({path:`logs/speculative-reasoning-${theme}.png`});
   await speed.click();assert.equal(await speed.getAttribute('data-mode'),'normal');
   assert.equal(await page.locator('.effort-fluid').count(),0);
   assert(await page.locator('.effort-dots span').evaluateAll(nodes=>nodes.every(e=>getComputedStyle(e).animationName==='none')));
   await speed.click();await page.keyboard.press('Escape');
   await settings();await method.click();assert.equal(await method.innerText(),'Ngram');
   await page.locator('#load-setting-contextShift').click();await page.keyboard.press('Escape');
   await reasoning();assert(await speed.isDisabled());assert.equal(await page.locator('.effort-fluid').count(),0);
   await page.locator('#reasoning-reset-control').click();await page.keyboard.press('Escape');
   await settings();assert.equal(await method.innerText(),'Ngram');await page.locator('#load-setting-contextShift').click();
   await page.keyboard.press('Escape');await reasoning();assert.equal(await speed.getAttribute('data-mode'),'normal');
   assert(!await speed.isDisabled());
  }else{
   assert.equal(await page.locator('.mobile-reasoning-toggle').count(),1);
   assert.equal(await page.locator('#reasoning-speed-control').count(),0);
  }
  assert.deepEqual(errors,[]);results.push({width,theme,order:true,matching_control:true,two_speed_states:true,animation_verified:width>768});
  console.log('PASS',width,height,theme);await page.close();
 }
 await fs.writeFile('logs/speculative-visual.json',JSON.stringify(results,null,2));
}finally{await browser.close()}
