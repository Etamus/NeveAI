import fs from 'node:fs/promises';
import {constants} from 'node:fs';
import assert from 'node:assert/strict';
import {createServer} from 'vite';
import {chromium} from '../logs/ui-image-26/node_modules/playwright/index.mjs';
import {execFileSync} from 'node:child_process';
import {installMobileOfflineApi} from './fixtures/mobile-offline-api.mjs';
const dir=new URL('../src/routes/__mobile_refinements/',import.meta.url),file=new URL('+page.svelte',dir);
const results=[];let server,browser;
const output=process.env.REFINEMENT_DIR??'logs/mobile-20261028';
const fixtureCount=Number(process.env.REFINEMENT_MODEL_COUNT??2);
const models=Array.from({length:fixtureCount},(_,i)=>({id:'local/fixture-'+i,filename:'Example model '+i+'.gguf',file_size:123456,file_size_human:'4.0 GB',is_loaded:i===0,n_ctx:8192,cache_type:'q8_0',context_shift:'off',token_prediction:'off',speculative_decoding:'off'}));
const wave=Buffer.alloc(44+16000);wave.write('RIFF');wave.writeUInt32LE(wave.length-8,4);wave.write('WAVEfmt ',8);wave.writeUInt32LE(16,16);wave.writeUInt16LE(1,20);wave.writeUInt16LE(1,22);wave.writeUInt32LE(8000,24);wave.writeUInt32LE(16000,28);wave.writeUInt16LE(2,32);wave.writeUInt16LE(16,34);wave.write('data',36);wave.writeUInt32LE(16000,40);
await fs.mkdir(output,{recursive:true});await fs.mkdir(dir,{recursive:true});await fs.copyFile(new URL('./fixtures/mobile-refinements.svelte',import.meta.url),file,constants.COPYFILE_EXCL);
try{
 server=await createServer({plugins:process.env.BASELINE_VARIABLES?[{name:'original-variables',enforce:'pre',load(id){if(id.endsWith('/src/lib/components/chat/MessageInput/InputVariablesModal.svelte'))return execFileSync('git',['show','HEAD:src/lib/components/chat/MessageInput/InputVariablesModal.svelte'],{encoding:'utf8'});}}]:[],server:{port:5188,strictPort:true,watch:{ignored:['**/logs/**','**/scripts/**','**/docs/**']}}});await server.listen();browser=await chromium.launch();
 for(const width of (process.env.REFINEMENT_WIDTHS??'320,390,767,1440').split(',').map(Number))for(const dark of process.env.REFINEMENT_LIGHT_ONLY?[false]:[false,true]){
  const mobile=width<768,page=await browser.newPage({viewport:{width,height:1000},hasTouch:mobile}),errors=[];page.setDefaultTimeout(15000);page.on('pageerror',e=>{errors.push(e.message);console.log('PAGEERROR',e.stack);});
  if(process.env.MOBILE_OFFLINE)await installMobileOfflineApi(page);
  await page.route('**/api/**',async route=>{
   const path=new URL(route.request().url()).pathname,match=path.match(/\/api\/v1\/files\/fixture-(\w+)(\/content)?$/);
   if(match){const extension=match[1],mime={png:'image/png',mp4:'video/mp4',wav:'audio/wav',pdf:'application/pdf',txt:'text/plain'}[extension];
    if(!match[2])return route.fulfill({json:{id:'fixture-'+extension,filename:'Example.'+extension,meta:{content_type:mime},data:{content:'Example file content'}}});
    const body=extension==='wav'?wave:extension==='txt'?Buffer.from('Example file content'):await fs.readFile('logs/webview2-native-test/'+({png:'attachment.png',mp4:'probe.mp4',pdf:'probe.pdf'}[extension]));
    return route.fulfill({contentType:mime,body});}
   if(process.env.MOBILE_OFFLINE)return route.fallback();
   return route.request().method()==='GET'||path.includes('/auths/')?route.continue():route.fulfill({json:{}});
  });
  await page.route('**/llamacpp/models',r=>r.fulfill({json:{models}}));await page.route('**/llamacpp/models/loaded',r=>r.fulfill({json:{models:[models[0]]}}));
  await page.goto('http://localhost:5188/__mobile_refinements',{waitUntil:'networkidle',timeout:90000});await page.waitForFunction(()=>window.__mobileRefinements);await page.evaluate(()=>document.fonts.ready);
  for(const kind of process.env.REFINEMENT_CASES?.split(',')??['unified','download','model','settings','search','project','profile','memory','variables','tools','code','confirm','inpaint','outpaint','file-png','file-mp4','file-wav','file-pdf','file-txt']){
   console.log('CASE '+width+' '+dark+' '+kind);
   await page.evaluate(({kind,dark})=>window.__mobileRefinements.open(kind,dark),{kind,dark});await page.waitForTimeout(450);
   if(kind==='parameters'){await page.evaluate(()=>window.__mobileParameters());await page.waitForTimeout(250);}
   const dialog=kind==='parameters'?page.locator('div.fixed').filter({has:page.locator('#close-chat-parameters-button')}).last():kind==='confirm'?page.locator('body > div.fixed').filter({hasText:'No action will be executed.'}).last():page.locator('.modal[aria-hidden="false"], .modal:not([aria-hidden])').last();await dialog.waitFor({state:'visible'});
   const backs=dialog.locator('.mobile-modal-back');if(!process.env.BASELINE_VARIABLES)assert.equal(await backs.count(),mobile?1:0,kind+' mobile Back visibility');
   if(mobile)for(const close of await dialog.locator('[data-mobile-modal-close]').all())assert.equal(await close.isVisible(),false,kind+' mobile close icon is visible');
   const metrics={width,dark,kind};
   if(kind==='parameters')assert.equal(await page.locator('#model-settings-content').evaluate(e=>getComputedStyle(e).paddingLeft),mobile?'24px':await page.evaluate(()=>getComputedStyle(document.documentElement).fontSize));
   if(kind==='settings'&&mobile){
    const tabs=page.locator('.tabs button');
    for(let index=0;index<await tabs.count();index++){
     await tabs.nth(index).click();
     assert.equal(await page.locator('.settings-content').evaluate(e=>getComputedStyle(e).paddingLeft),'28px');
     assert.equal(await page.locator('.settings-content').evaluate(e=>e.scrollWidth>e.clientWidth),false);
     await page.goBack();await page.waitForTimeout(100);
    }
   }
   if(kind==='unified'){
    assert.equal(await dialog.getByText('VRAM',{exact:true}).count(),mobile?0:1);
    metrics.cards=await page.locator('.unified-model-card').evaluateAll(es=>es.map(e=>{const r=e.getBoundingClientRect(),avatar=e.querySelector('.model-avatar').getBoundingClientRect(),last=e.lastElementChild.getBoundingClientRect(),n=e.querySelector('.unified-model-name').getBoundingClientRect(),m=e.querySelector('.unified-model-meta').getBoundingClientRect();return{left:avatar.left-r.left,right:r.right-last.right,gap:m.top-n.bottom};}));
    if(mobile)assert(metrics.cards.every(c=>c.left>=9&&c.right>=9&&c.gap>=2&&c.gap<=4),JSON.stringify(metrics));
    if(mobile&&fixtureCount>30){assert(metrics.cards.length>=fixtureCount,'Mobile list is paginated');metrics.list=await page.locator('.unified-model-list').evaluate(e=>({height:e.clientHeight,total:e.scrollHeight,overflow:getComputedStyle(e).overflowY}));assert.equal(metrics.list.overflow,'visible');assert(Math.abs(metrics.list.height-metrics.list.total)<=1);const body=page.locator('.unified-models-body');await body.evaluate(e=>e.scrollTop=e.scrollHeight);const last=await page.locator('.unified-model-card').last().boundingBox(),bounds=await body.boundingBox();assert(last.y>=bounds.y&&last.y+last.height<=bounds.y+bounds.height+1,'Last model is not reachable');}
   }
   if(kind==='download'){
    metrics.descriptions=await page.locator('.catalog-model-description').allTextContents();if(mobile)assert(metrics.descriptions.every(t=>t.trim().length<=42));
    metrics.selectionLeft=await page.locator('.catalog-selection-toggle').evaluate(e=>e.getBoundingClientRect().left);if(mobile)assert(metrics.selectionLeft>=22);
   }
   if(kind==='model'){
    assert.equal(await page.locator('.model-editor-features').getByText('Criar imagem',{exact:true}).count(),0);
    assert.equal(await page.locator('.model-editor-features').getByText('Criar vídeo',{exact:true}).count(),0);
    assert.equal(await page.locator('.model-editor-features').isVisible(),!mobile);
    metrics.identity=await page.locator('.model-editor-profile').evaluate(e=>{const image=e.querySelector('img').getBoundingClientRect(),identity=e.querySelector('.model-editor-identity').getBoundingClientRect(),name=e.querySelector('input[placeholder]').getBoundingClientRect(),description=e.querySelector('textarea').getBoundingClientRect();return{gap:identity.left-image.right,name:name.left,description:description.left};});
    if(mobile)assert(metrics.identity.gap>=19&&Math.abs(metrics.identity.name-metrics.identity.description)<=1,JSON.stringify(metrics.identity));
    metrics.params=await page.locator('.model-editor-advanced-params-window').evaluate(e=>({max:getComputedStyle(e).maxHeight,client:e.clientHeight,scroll:e.scrollHeight}));
     if(mobile)assert.equal(metrics.params.max,'none');
     else if(metrics.params.scroll>metrics.params.client){
      const panel=page.locator('.model-editor-advanced-params-window');
      await panel.evaluate(e=>e.scrollTop=0);await panel.hover();await page.mouse.wheel(0,120);await page.waitForTimeout(100);
      metrics.parameterWheel=await panel.evaluate(e=>e.scrollTop);
      assert(metrics.parameterWheel>0&&metrics.parameterWheel<=48,'Coarse wheel must advance at most 48px');
     }
    assert.equal(await page.locator('.model-editor-params-scroll').evaluate(e=>getComputedStyle(e).paddingLeft),mobile?'24px':await page.evaluate(()=>getComputedStyle(document.documentElement).fontSize));
   }
   if(kind.startsWith('file-')){
    const size=await page.locator('.file-viewer-size').boundingBox(),name=await page.locator('[title="Example.'+kind.slice(5)+'"]').boundingBox();metrics.metadata={size,name};
    if(mobile)assert(size.y>=name.y+name.height-1&&Math.abs(size.x-name.x)<=1,'File size is not below and left-aligned with its name: '+JSON.stringify(metrics));
    assert(await page.locator('.file-viewer-size').textContent());
   }
   await page.screenshot({path:`${output}/${kind}-${width}-${dark?'dark':'light'}.png`});
   if(mobile&&!process.env.BASELINE_VARIABLES){await backs.click();await page.waitForTimeout(300);assert.equal(await page.evaluate(()=>window.__mobileRefinements.state().show),false,kind+' Back did not close the expected modal');}
   else {await page.keyboard.press('Escape');await page.waitForTimeout(200);}
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,kind+' page overflow');results.push(metrics);
  }
  assert.deepEqual(errors,[]);await page.close();console.log('PASS '+width+' '+(dark?'dark':'light'));
 }
 await fs.writeFile(process.env.REFINEMENT_RESULT??output+'/results.json',JSON.stringify(results,null,2));console.log('PASS '+results.length+' modal/layout cases');
}catch(error){for(const page of browser?.contexts().flatMap(c=>c.pages())??[])await page.screenshot({path:output+'/failure.png'}).catch(()=>{});throw error;}finally{await browser?.close();await server?.close();await fs.unlink(file);await fs.rmdir(dir);}
