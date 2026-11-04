import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
import { constants } from 'node:fs';
import { createServer } from 'vite';
import { chromium } from '../logs/ui-image-26/node_modules/playwright/index.mjs';
import { installMobileOfflineApi } from './fixtures/mobile-offline-api.mjs';
const directory = new URL('../src/routes/__ram_test/',import.meta.url), route = new URL('+page.svelte', directory);
await fs.mkdir(directory,{recursive:true});
await fs.copyFile(new URL('./fixtures/unified-availability.svelte',import.meta.url),route,constants.COPYFILE_EXCL);
let server,browser;
const results=[];
const gpu={available:true,total:16*1024**3,used:4*1024**3,free:12*1024**3,gpus:[]};
const cpu={...gpu,available:false,total:0,used:0,free:0,ram:{available:true,source:'system',total:32*1024**3,used:8*1024**3,free:24*1024**3}};
try {
  server=await createServer({plugins:[{name:'ram-meter-fixture',enforce:'pre',configResolved(config){config.server.proxy=undefined;},async load(id){if(id.endsWith('/__ram_test/+page.svelte'))return(await fs.readFile(route,'utf8')).replaceAll('../../src/','../../').replace(/vramInfo: \{[\s\S]*?gpus: \[\] \}/,'vramInfo:'+JSON.stringify(cpu)).replace('async open()', 'async setVram(value: any) { preload.vramInfo=value;await tick(); }, async open()');}}],server:{port:5195,strictPort:true,watch:{ignored:['**/logs/**','**/scripts/**','**/docs/**']}}});
  await server.listen(); browser=await chromium.launch();
  for(const [name,width] of [['desktop',1440],['mobile',390]])for(const theme of ['light','dark']) {
    const page=await browser.newPage({viewport:{width,height:1000}}),errors=[];
    page.on('pageerror',error=>{errors.push(error.message);console.error(error.stack);}); await installMobileOfflineApi(page);
    await page.route('**/llamacpp/vram',route=>route.fulfill({json:cpu}));
    await page.route('**/llamacpp/models',async route=>{
      const modelNames=['Alpha','Beta','Gamma'];
      await route.fulfill({json:{models:modelNames.map((name,i)=>({id:`local/${name}`,filename:`${name}.gguf`,file_size:1000000000,file_size_human:'1 GB',is_loaded:i===0,loaded_at:100,n_ctx:8192,n_gpu_layers:-1,cache_type:'q8_0',mmproj_filename:'',speculative_decoding:'off',token_prediction:'off',context_shift:'off'}))}});
    });
    await page.goto('http://localhost:5195/__ram_test',{waitUntil:'networkidle',timeout:120000});
    await page.waitForFunction(()=>window.__availabilityFixture);
    await page.evaluate(async theme=>{document.documentElement.classList.toggle('dark',theme==='dark');await window.__availabilityFixture.open();},theme);
    if(name==='desktop') {
      const expand=page.getByRole('button',{name:'Mostrar modelos',exact:true});
      await expand.waitFor();
      const collapsedHeight=await page.locator('.unified-models-shell').evaluate(element=>element.getBoundingClientRect().height);
      await expand.click();
      await page.waitForTimeout(250);
      assert.ok(await page.locator('.unified-model-list .unified-model-card').count()>=2,'Manual expansion shows other models');
      assert.ok(await page.locator('.unified-models-shell').evaluate(element=>element.getBoundingClientRect().height)>collapsedHeight,'Original expandable size restored');
      await page.getByRole('button',{name:'Ocultar modelos',exact:true}).click();
      await page.waitForTimeout(250);
      await page.evaluate(async()=>{await window.__availabilityFixture.close();await window.__availabilityFixture.open();});
      await expand.waitFor();
      assert.equal(await page.locator('.unified-models-shell').evaluate(element=>element.getBoundingClientRect().height),collapsedHeight,'Original collapsed reopening restored');
      const meter=page.locator('[data-ram-meter]');await meter.waitFor();
      assert.match(await meter.innerText(),/8.*GB.*32.*GB/);
      assert.match(await meter.innerText(),/24.*GB/);
      assert.equal(await page.getByText('Use CPU models or install compatible drivers.').count(),0);
      await page.evaluate(async value=>window.__availabilityFixture.setVram(value),{...cpu,ram:{available:false,total:0,used:0,free:0,source:'system'}});
      assert.doesNotMatch(await meter.innerText(),/NaN|Infinity/);
      await page.evaluate(async value=>window.__availabilityFixture.setVram(value),gpu);
      assert.equal(await page.locator('[data-ram-meter]').count(),0);
      assert.match(await page.locator('[data-vram-meter]').innerText(),/VRAM/);
      await page.evaluate(async value=>window.__availabilityFixture.setVram(value),cpu);
    } else assert.equal(await page.locator('[data-vram-meter]').count(),0);
    await page.screenshot({path:`logs/ram-meter-${name}-${theme}.png`});assert.deepEqual(errors,[]);results.push({name,theme,errors});await page.close();
  }
  await fs.writeFile('logs/ram-meter-results.json',JSON.stringify(results,null,2));
} finally { await browser?.close();await server?.close();await fs.rm(route,{force:true});await fs.rmdir(directory).catch(()=>{}); }
