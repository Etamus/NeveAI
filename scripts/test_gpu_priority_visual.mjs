import fs from 'node:fs/promises';
import {constants} from 'node:fs';
import assert from 'node:assert/strict';
import {createServer} from 'vite';
import {chromium} from '../logs/ui-image-26/node_modules/playwright/index.mjs';
import {installMobileOfflineApi} from './fixtures/mobile-offline-api.mjs';
const dir=new URL('../src/routes/__gpu_priority_test/',import.meta.url),file=new URL('+page.svelte',dir);
let server,browser;const results=[];
try{
    await fs.mkdir(dir,{recursive:true});await fs.copyFile(new URL('./fixtures/gpu-priority.svelte',import.meta.url),file,constants.COPYFILE_EXCL);
    server=await createServer({plugins:[{name:'gpu-fixture',configResolved(c){c.server.proxy=undefined;}}],server:{port:5196,strictPort:true,watch:{ignored:['**/logs/**']}}});
    await server.listen();browser=await chromium.launch();
    for(const width of [1440,390]){
        const page=await browser.newPage({viewport:{width,height:1000}}),errors=[],requests=[];
        page.on('pageerror',e=>errors.push(e.message));await installMobileOfflineApi(page);
        let local={id:'local/Alpha',filename:'Alpha.gguf',file_size:1000000000,file_size_human:'1 GB',is_loaded:false,n_ctx:8192,n_gpu_layers:-1};
        await page.route('**/llamacpp/status',r=>r.fulfill({json:{server_binary_exists:true,automatic_context:true,gpu_priority_supported:true}}));
        await page.route('**/llamacpp/models',r=>r.fulfill({json:{models:[local]}}));
        await page.route('**/llamacpp/models/*',r=>{
            if(r.request().url().endsWith('/load')){
                const body=r.request().postDataJSON();requests.push(body);
                local={...local,...body,is_loaded:true,n_ctx:body.n_ctx||8192,context_auto:body.n_ctx===0};return r.fulfill({json:local});
            }
            if(r.request().url().endsWith('/unload')){local={...local,is_loaded:false};return r.fulfill({json:{id:local.id,status:'unloaded'}});}
            return r.fulfill({json:{mmproj_files:[]}});
        });
        await page.goto('http://localhost:5196/__gpu_priority_test',{waitUntil:'networkidle',timeout:120000});
        const toggle=page.locator('#load-setting-gpu-priority');await toggle.waitFor();
        assert.equal(await toggle.getAttribute('aria-checked'),'false');
        const before=await page.evaluate(()=>({context:localStorage.getItem('llamacpp_load_context'),cache:localStorage.getItem('llamacpp_cache_type')}));
        await toggle.click();assert.equal(await toggle.getAttribute('aria-checked'),'true');
        assert.deepEqual(await page.evaluate(()=>({context:localStorage.getItem('llamacpp_load_context'),cache:localStorage.getItem('llamacpp_cache_type')})),before);
        await page.reload({waitUntil:'networkidle'});assert.equal(await toggle.getAttribute('aria-checked'),'true');
        for(const theme of ['light','dark']){
            await page.evaluate(t=>document.documentElement.classList.toggle('dark',t==='dark'),theme);
            await page.screenshot({path:`logs/gpu-priority-${width}-${theme}.png`});
        }
        await page.locator('#open-models').click();const modal=page.locator('.unified-models-shell');
        await modal.locator('button[aria-label="Carregar"]').first().click();await modal.locator('button[aria-label="Descarregar"]').waitFor();
        assert.equal(requests.at(-1).prioritize_gpu,true);
        await modal.locator('button[aria-label="Descarregar"]').click();
        await modal.locator('button[aria-label="Carregar"]').first().waitFor();
        await page.evaluate(()=>window.__gpuFixture.close());await page.waitForFunction(()=>window.__gpuFixture.closed());
        await toggle.click();assert.equal(await toggle.getAttribute('aria-checked'),'false');
        await page.locator('#open-models').click();await modal.locator('button[aria-label="Carregar"]').first().click();
        await modal.locator('button[aria-label="Descarregar"]').waitFor();assert.equal(requests.at(-1).prioritize_gpu,false);
        assert.deepEqual(errors,[]);results.push({width,persisted:true,otherSettingsUnchanged:true,loadFlags:requests.map(r=>r.prioritize_gpu),errors});await page.close();
    }
    await fs.writeFile('logs/gpu-priority-visual-results.json',JSON.stringify(results,null,2));console.log(JSON.stringify(results));
}finally{await browser?.close();await server?.close();await fs.rm(file,{force:true});await fs.rmdir(dir).catch(()=>{});}
