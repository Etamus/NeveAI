import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
import { createServer } from 'vite';
import { chromium } from '../logs/ui-image-26/node_modules/playwright/index.mjs';
import { installMobileOfflineApi } from './fixtures/mobile-offline-api.mjs';
const directory=new URL('../src/routes/__unified_catalog_test/',import.meta.url),file=new URL('+page.svelte',directory);
let server,browser;
const results=[];
try {
    await fs.mkdir(directory,{recursive:true});
    await fs.copyFile(new URL('./fixtures/unified-catalog.svelte',import.meta.url),file,fs.constants?.COPYFILE_EXCL ?? 1);
    server=await createServer({plugins:[{name:'catalog-fixture',configResolved(config){config.server.proxy=undefined;}}],server:{port:5195,strictPort:true,watch:{ignored:['**/logs/**']}}});
    await server.listen();browser=await chromium.launch();
    for(const width of [1440,390]) {
        const page=await browser.newPage({viewport:{width,height:1000}}),errors=[],saves=[],runtimeRequests=[];
        page.on('pageerror',error=>{errors.push(error.message);console.error(error);});
        await installMobileOfflineApi(page);
        const local=['Alpha','Beta','Gamma'].map(name=>({id:`local/${name}`,filename:`${name}.gguf`,file_size:1000000000,file_size_human:'1 GB',is_loaded:false,n_ctx:8192,n_gpu_layers:-1}));
        let workspace=local.map(model=>({id:model.id,name:model.filename.replace('.gguf',''),base_model_id:null,is_active:true,meta:{}}));
        let holdCatalog=false,holdSave=false,failSave=false,failCatalog=false,pendingCatalog=[],pendingSave=[];
        await page.route('**/llamacpp/models',route=>route.fulfill({json:{models:local}}));
        await page.route('**/llamacpp/models/*',route=>{if(route.request().method()!=='GET')runtimeRequests.push(route.request().url());return route.fulfill({json:{mmproj_files:[]}});});
        await page.route('**/api/models',route=>route.fulfill({json:{data:workspace.filter(model=>model.is_active).map(model=>({...model,owned_by:'llamacpp'}))}}));
        await page.route('**/api/v1/models/base',async route=>{
            const snapshot=structuredClone(workspace),failed=failCatalog;
            if(holdCatalog)await new Promise(resolve=>pendingCatalog.push(resolve));
            await route.fulfill(failed?{status:503,json:{detail:'Catalog unavailable'}}:{json:snapshot}).catch(()=>{});
        });
        await page.route('**/api/v1/models/model/toggle?*',async route=>{
            const id=new URL(route.request().url()).searchParams.get('id');saves.push(id);
            if(holdSave)await new Promise(resolve=>pendingSave.push(resolve));
            if(failSave)return route.fulfill({status:500,json:{detail:'Could not save'}});
            workspace=workspace.map(model=>model.id===id?{...model,is_active:!model.is_active}:model);
            await route.fulfill({json:workspace.find(model=>model.id===id)});
        });
        await page.route('**/models/model/profile/image?**',async route=>route.fulfill({body:await fs.readFile('static/favicon.png'),contentType:'image/png'}));
        await page.goto('http://localhost:5195/__unified_catalog_test',{waitUntil:'networkidle',timeout:120000});
        await page.waitForFunction(()=>window.__catalogFixture);
        await page.evaluate(()=>window.__catalogFixture.open());
        const beta=page.getByRole('switch',{name:'Beta',exact:true}),alpha=page.getByRole('switch',{name:'Alpha',exact:true});
        await beta.waitFor();
        const checked=async(toggle,value)=>assert.equal(await toggle.getAttribute('aria-checked'),String(value));
        const waitFor=async condition=>{const until=Date.now()+10000;while(!condition()){assert.ok(Date.now()<until,'Pending request not observed');await page.waitForTimeout(20);}};
        const reopen=async()=>{
            await page.evaluate(()=>window.__catalogFixture.close());
            await page.waitForFunction(()=>!window.__catalogFixture.dialogOpen());
            await page.evaluate(()=>window.__catalogFixture.open());
            await beta.waitFor();
        };
        holdCatalog=true;await reopen();await waitFor(()=>pendingCatalog.length>0);
        holdSave=true;await beta.click({timeout:7000}).catch(async error=>{await page.screenshot({path:'logs/unified-catalog-failure.png'});console.error(await page.locator('body').innerText());throw error;});await waitFor(()=>pendingSave.length===1);await checked(beta,false);
        assert.ok(await beta.isDisabled(),'Only pending toggle is disabled');assert.ok(await alpha.isEnabled());
        await beta.evaluate(button=>button.click());assert.equal(saves.length,1,'Duplicate save is not sent');
        await reopen();await checked(beta,false);
        holdSave=false;for(const resolve of pendingSave.splice(0))resolve();
        await waitFor(()=>workspace.find(model=>model.name==='Beta').is_active===false);
        await reopen();await checked(beta,false);
        holdCatalog=false;for(const resolve of pendingCatalog.splice(0))resolve();
        await page.waitForTimeout(250);await checked(beta,false);
        for(let i=0;i<3;i++){await reopen();await checked(beta,false);}
        await beta.click();await waitFor(()=>workspace.find(model=>model.name==='Beta').is_active===true);await page.waitForTimeout(150);await checked(beta,true);
        failSave=true;await beta.click();await page.waitForTimeout(250);await checked(beta,true);failSave=false;
        await reopen();await checked(beta,true);
        holdSave=true;await alpha.click();await beta.click();await waitFor(()=>pendingSave.length===2);
        const reverse=pendingSave.splice(0).reverse();holdSave=false;for(const resolve of reverse)resolve();
        await waitFor(()=>workspace.filter(model=>!model.is_active).length===2);await page.waitForTimeout(250);
        await reopen();await checked(alpha,false);await checked(beta,false);
        failCatalog=true;await reopen();await page.waitForTimeout(300);await checked(alpha,false);await checked(beta,false);failCatalog=false;
        assert.deepEqual(runtimeRequests,[],'Catalog toggles must not load or unload models');
        assert.deepEqual(errors,[]);
        await page.screenshot({path:`logs/unified-catalog-${width}.png`});
        results.push({width,optimisticReopen:true,staleResponsesIgnored:true,duplicateSaveBlocked:true,failedSaveRollback:true,parallelToggles:true,catalogFailurePreserved:true,runtimeRequests:0,errors});
        await page.close();
    }
    await fs.writeFile('logs/unified-catalog-results.json',JSON.stringify(results,null,2));
    console.log(JSON.stringify(results));
} finally {await browser?.close();await server?.close();await fs.rm(file,{force:true});await fs.rmdir(directory).catch(()=>{});}
