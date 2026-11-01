import fs from 'node:fs/promises';
import {constants} from 'node:fs';
import assert from 'node:assert/strict';
import {createServer} from 'vite';
import {chromium} from '../logs/ui-image-26/node_modules/playwright/index.mjs';
import {installMobileOfflineApi} from './fixtures/mobile-offline-api.mjs';

const routeDir=new URL('../src/routes/__unified_availability_test/',import.meta.url);
const routeFile=new URL('+page.svelte',routeDir);
const output='logs/unified-availability';
let server,browser;const results=[];
await fs.mkdir(output,{recursive:true});await fs.mkdir(routeDir,{recursive:true});
await fs.copyFile(new URL('./fixtures/unified-availability.svelte',import.meta.url),routeFile,constants.COPYFILE_EXCL);
try {
 server=await createServer({cacheDir:'node_modules/.vite-unified-availability',plugins:[{name:'unified-availability-fixture',enforce:'pre',
  configResolved(config){config.server.proxy=undefined;},
  async load(id){if(id.endsWith('/__unified_availability_test/+page.svelte'))return(await fs.readFile(routeFile,'utf8')).replaceAll('../../src/','../../');}
 }],server:{port:5195,strictPort:true,watch:{ignored:['**/logs/**','**/scripts/**','**/docs/**']}}});
 await server.listen();browser=await chromium.launch();
 for(const [name,viewport] of [['desktop',{width:1440,height:1000}],['mobile',{width:390,height:844}]]) {
  const page=await browser.newPage({viewport});const errors=[],mutations=[];
  page.on('pageerror',error=>{errors.push(error.message);console.error(error.stack);});
  page.setDefaultTimeout(20000);await installMobileOfflineApi(page);
  await page.route('**/llamacpp/status',route=>route.fulfill({json:{server_binary_exists:true,automatic_context:true}}));
  await page.route('**/llamacpp/vram',route=>route.fulfill({json:{available:true,source:'nvidia-smi',total:17179869184,used:4294967296,free:12884901888,total_human:'16 GB',used_human:'4 GB',free_human:'12 GB',gpus:[]}}));
  let pending=[];let catalog=['Alpha','Beta','Gamma'].map((name,i)=>({id:`local/${name}`,filename:`${name}.gguf`,file_size:1000000000,file_size_human:'1 GB',is_loaded:i===0,n_ctx:8192,n_gpu_layers:-1,cache_type:'q8_0',mmproj_filename:'',speculative_decoding:'off',token_prediction:'off',context_shift:'off'}));let state={epoch:'fixture',revision:0,busy:false,loaded_models:[]};let hold=false;
  await page.route('**/llamacpp/media-state',async route=>{
   const captured=structuredClone(state);
   if(hold) await new Promise(resolve=>pending.push(resolve));
   await route.fulfill({json:captured}).catch(()=>{});
  });
  await page.route('**/llamacpp/models',route=>route.fulfill({json:{models:catalog}}));
  await page.route('**/llamacpp/models/*',route=>{
   if(route.request().method()!=='GET'){
    mutations.push(route.request().url());
    if(route.request().url().endsWith('/unload')){
     catalog=catalog.map(model=>({...model,is_loaded:false}));state={...state,loaded_models:[]};
     return route.fulfill({json:{id:'local/Alpha',status:'unloaded'}});
    }
    if(route.request().url().endsWith('/load')){
     const body=route.request().postDataJSON();
     const loaded={...catalog[0],is_loaded:true,n_ctx:body.n_ctx||8192,context_auto:body.n_ctx===0,cache_type:body.cache_type};
     catalog=catalog.map(model=>model.id===loaded.id?loaded:{...model,is_loaded:false});state={...state,loaded_models:[loaded]};
     return route.fulfill({json:loaded});
    }
   }
   return route.fulfill({json:route.request().url().endsWith('/mmproj')?{mmproj_files:[]}:{models:[]}});
  });
  await page.goto('http://localhost:5195/__unified_availability_test',{waitUntil:'networkidle',timeout:120000});
  await page.waitForFunction(()=>window.__availabilityFixture);
  catalog=await page.evaluate(()=>window.__availabilityFixture.local);
  state={epoch:'fixture',revision:1,busy:true,loaded_models:[]};hold=true;
  await page.evaluate(async state=>{await window.__availabilityFixture.event(state);await window.__availabilityFixture.open();},state);
  const modal=page.locator('.unified-models-shell'),list=modal.locator('.unified-model-catalog');
  await list.waitFor();
  assert.equal(await list.getAttribute('inert'),'');
  assert.equal(await list.getAttribute('data-models-blocked'),'true');
  if(name==='desktop') {
   const appearance=await list.locator('[data-vram-meter]').evaluate(element=>{
    let opacity=1;const filters=[];
    for(let node=element;node&&!node.classList.contains('modal-content');node=node.parentElement){const style=getComputedStyle(node);opacity*=Number(style.opacity);if(style.filter!=='none')filters.push(style.filter);}
    return {opacity,filters};
   });
   assert.equal(appearance.opacity,1,'VRAM must remain at normal opacity');
   assert.deepEqual(appearance.filters,[],'VRAM must not inherit grayscale');
  }
  assert.equal(await list.locator('.unified-model-list-section').evaluate(element=>getComputedStyle(element).opacity),'0.5');
  assert.equal(await modal.getByRole('button',{name:'Descarregar',includeHidden:true}).count(),0);
  assert.equal(await modal.getByText('CTX: 8192',{exact:true}).count(),0);
  for(const button of await modal.getByRole('button',{name:'Carregar',includeHidden:true}).all())assert(await button.isDisabled());
  // Even programmatic clicks must not call the model-control API while locked.
  await list.locator('button[aria-label="Carregar"]').first().evaluate(button=>button.click());
  await page.screenshot({path:`${output}/${name}-busy.png`});
  await page.evaluate(()=>document.documentElement.classList.add('dark'));
  await page.screenshot({path:`${output}/${name}-busy-dark.png`});
  await page.evaluate(()=>document.documentElement.classList.remove('dark'));
  await page.evaluate(()=>window.__availabilityFixture.close());
  const restored={...catalog[0],is_loaded:true,n_ctx:32768};catalog=catalog.map(model=>({...model,is_loaded:false}));
  state={epoch:'fixture',revision:2,busy:false,loaded_models:[restored]};
  await page.evaluate(async state=>{await window.__availabilityFixture.event(state);await window.__availabilityFixture.open();},state);
  assert.equal(await list.getAttribute('data-models-blocked'),'false');
  await modal.getByText('CTX: 32768',{exact:true}).waitFor().catch(async error=>{
   await page.screenshot({path:`${output}/${name}-failure.png`});console.error(await modal.innerText());throw error;
  });
  assert.equal(await modal.locator('button[aria-label="Descarregar"]').count(),1);
  // Release stale HTTP responses issued while busy; they must not re-lock the list.
  hold=false;for(const resolve of pending.splice(0))resolve();
  catalog=catalog.map(model=>model.id===restored.id?restored:model);
  await page.waitForTimeout(250);
  assert.equal(await list.getAttribute('data-models-blocked'),'false');
  await modal.getByText('CTX: 32768',{exact:true}).waitFor();
  await page.screenshot({path:`${output}/${name}-restored.png`});
  await page.evaluate(()=>document.documentElement.classList.add('dark'));
  await page.screenshot({path:`${output}/${name}-restored-dark.png`});
  assert.deepEqual(mutations,[]);
  await modal.locator('button[aria-label="Descarregar"]').click();
  const alpha=modal.locator('.unified-model-card').filter({hasText:'Alpha'});
  await alpha.locator('button[aria-label="Carregar"]').waitFor();
  await alpha.locator('button[aria-label="Carregar"]').click();
  await alpha.locator('button[aria-label="Descarregar"]').waitFor();
  assert.equal(mutations.length,2,'Normal manual unload/load must remain available after media');
  assert.deepEqual(errors,[]);
  results.push({viewport:name,busyImmediately:true,noLoadedBadgeWhileBusy:true,restoredBeforePolling:true,lateResponsesIgnored:true,modelControlRequestsWhileBusy:0,manualActionsAfterMedia:mutations.length,errors});
  await page.close();
 }
 await fs.writeFile(`${output}/results.json`,JSON.stringify(results,null,2));console.log(JSON.stringify(results));
}finally{await browser?.close();await server?.close();await fs.unlink(routeFile);await fs.rmdir(routeDir);}
