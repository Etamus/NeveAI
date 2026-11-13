import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {chromium} from '../logs/ui-image-26/node_modules/playwright/index.mjs';
import {installMobileOfflineApi} from './fixtures/mobile-offline-api.mjs';
const browser=await chromium.launch(),results=[];
try{
 for(const width of [1440,390])for(const count of [2,12])for(const loaded of [false,true])for(const theme of ['dark','light']){
  const context=await browser.newContext({viewport:{width,height:1000}}),page=await context.newPage(),errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  await page.addInitScript(theme=>{localStorage.setItem('neveai.language','pt-BR');localStorage.setItem('theme',theme);},theme);
  await installMobileOfflineApi(page);
  await page.route('**/api/v1/models/model/profile/image?**',route=>route.fulfill({path:'static/user.png',contentType:'image/png'}));
  const local=Array.from({length:count},(_,i)=>({id:`local/Fixture-${i}`,filename:`Fixture-${i}.gguf`,file_size:1e9,file_size_human:'1 GB',is_loaded:loaded&&i===0,n_ctx:8192,n_gpu_layers:-1,cache_type:'q8_0',mmproj_filename:'',speculative_decoding:'off',token_prediction:'off',context_shift:'off'}));
  const admin=local.map(model=>({id:model.id,name:model.filename.replace('.gguf',''),is_active:true,owned_by:'llamacpp',meta:{profile_image_url:'/static/static/favicon.png'},llamacpp:model,info:{meta:{}}}));
  await page.route('**/api/models',route=>route.fulfill({json:{data:admin}}));
  await page.route('**/api/v1/models/base',route=>route.fulfill({json:admin}));
  await page.route('**/llamacpp/models',route=>route.fulfill({json:{models:local}}));
  await page.route('**/llamacpp/models/loaded',route=>route.fulfill({json:{models:local.filter(item=>item.is_loaded)}}));
  await page.route('**/llamacpp/media-state',route=>route.fulfill({json:{epoch:'spacing',revision:1,busy:false,loaded_models:local.filter(item=>item.is_loaded)}}));
  await page.goto('http://localhost:8080',{waitUntil:'networkidle'});
  await page.getByRole('button',{name:/^(Models|Modelos)$/}).click();
  await page.locator('.unified-model-card').first().waitFor();
  const expand=page.getByRole('button',{name:'Mostrar modelos',exact:true});if(await expand.isVisible())await expand.click();
  await page.waitForTimeout(250);
  await page.waitForFunction(()=>[...document.querySelectorAll('.model-avatar img')].every(image=>image.complete&&image.naturalWidth>0));
  const geometry=await page.locator('.unified-model-card').evaluateAll(cards=>cards.map(card=>{
   const b=card.getBoundingClientRect(),shell=card.closest('.unified-models-shell').getBoundingClientRect(),avatar=card.querySelector('.model-avatar').getBoundingClientRect(),toggle=card.querySelector('[role="switch"]')?.getBoundingClientRect();
   return {left:b.left-shell.left,right:shell.right-b.right,avatarInset:avatar.left-b.left,toggleInset:toggle?b.right-toggle.right:null};
  }));
  assert(geometry.length>=2,JSON.stringify({width,count,loaded,geometry}));
  for(const card of geometry){assert(Math.abs(card.left-card.right)<=1,JSON.stringify({width,count,loaded,card}));assert(card.avatarInset>=11.9);if(card.toggleInset!==null)assert(card.toggleInset>=11.9);}
  const viewport=await page.locator('.unified-model-list').evaluate(node=>({overflow:node.scrollHeight>node.clientHeight,gutter:getComputedStyle(node).scrollbarGutter}));
  if(width>=768)assert.equal(viewport.gutter,'stable both-edges');
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  await page.screenshot({path:`logs/unified-spacing-${width}-${count}-${loaded}-${theme}.png`});
  assert.deepEqual(errors,[]);results.push({width,count,loaded,theme,geometry,viewport,errors});await context.close();
 }
 await fs.writeFile('logs/unified-card-spacing-results.json',JSON.stringify(results,null,2));
 console.log('PASS unified cards: equal margins, avatar/toggle insets, loaded/unloaded and short/scrolling lists, desktop/mobile, both themes');
}finally{await browser.close();}
