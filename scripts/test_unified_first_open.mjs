import fs from 'node:fs/promises';
import {constants} from 'node:fs';
import assert from 'node:assert/strict';
import {createServer} from 'vite';
import {chromium} from '../logs/ui-image-26/node_modules/playwright/index.mjs';
import {installMobileOfflineApi} from './fixtures/mobile-offline-api.mjs';

const directory=new URL('../src/routes/__unified_first_open/',import.meta.url);
const file=new URL('+page.svelte',directory);
await fs.mkdir(directory,{recursive:true});
await fs.copyFile(new URL('./fixtures/unified-first-open.svelte',import.meta.url),file,constants.COPYFILE_EXCL);
let server,browser;
const results=[];
try {
    server=await createServer({server:{port:5195,strictPort:true,watch:{ignored:['**/logs/**']}}});
    await server.listen();
    browser=await chromium.launch();
    for(const width of [1440,390]) {
        const page=await browser.newPage({viewport:{width,height:950}});
        const errors=[];
        page.on('pageerror',error=>errors.push(error.message));
        await installMobileOfflineApi(page);
        await page.route('**/models/model/profile/image?**',async route=>route.fulfill({
            body:await fs.readFile('static/favicon.png'),contentType:'image/png'
        }));
        let pending=[],hold=true,empty=false,failed=false;
        await page.route('**/llamacpp/models',async route=>{
            if(hold)await new Promise(resolve=>pending.push(resolve));
            if(failed)return route.fulfill({status:503,json:{detail:'Backend unavailable'}}).catch(()=>{});
            const local=await page.evaluate(()=>window.__firstOpen.local).catch(()=>[]);
            return route.fulfill({json:{models:empty?[]:local}}).catch(()=>{});
        });
        await page.route('**/llamacpp/status',route=>route.fulfill({json:{server_binary_exists:true}}));
        await page.route('**/llamacpp/models/mmproj',route=>route.fulfill({json:{mmproj_files:[]}}));
        await page.route('**/api/v1/models/base',async route=>{
            const admin=await page.evaluate(()=>window.__firstOpen.admin).catch(()=>[]);
            return route.fulfill({json:empty?[]:admin});
        });
        await page.goto('http://localhost:5195/__unified_first_open',{waitUntil:'networkidle',timeout:90000});
        await page.waitForFunction(()=>window.__firstOpen);
        const close = async () => {
            await page.evaluate(()=>window.__firstOpen.close());
            await page.waitForFunction(()=>!window.__firstOpen.dialogOpen());
        };
        await page.evaluate(()=>{
            window.__emptyFlashes=[];
            const observer=new MutationObserver(records=>{
                for(const record of records)for(const node of record.addedNodes){
                    const text=node.textContent||'';
                    if(/No models (found|installed)|Adjust your search/.test(text))window.__emptyFlashes.push(text);
                }
            });
            observer.observe(document.body,{childList:true,subtree:true});
        });
        await page.evaluate(()=>window.__firstOpen.open(true));
        assert.equal(await page.locator('.unified-model-card').count(),1,'Ready catalog must render without an HTTP refresh');
        await page.getByText('Alpha custom name',{exact:true}).waitFor();
        await page.screenshot({path:`logs/unified-first-open-${width}-ready.png`});
        assert.deepEqual(await page.evaluate(()=>window.__emptyFlashes),[]);
        hold=false;for(const resolve of pending.splice(0))resolve();
        await page.waitForTimeout(200);
        await close();
        hold=true;
        await page.evaluate(()=>{window.__emptyFlashes=[];return window.__firstOpen.open(false);});
        await page.waitForTimeout(350);
        assert.deepEqual(await page.evaluate(()=>window.__emptyFlashes),[],'Pending query is not an empty catalog');
        assert.equal(await page.locator('.unified-model-card').count(),0);
        hold=false;for(const resolve of pending.splice(0))resolve();
        await page.getByText('Alpha custom name',{exact:true}).waitFor({timeout:10000}).catch(async error=>{
            await page.screenshot({path:`logs/unified-first-open-${width}-failure.png`});
            console.error(await page.locator('body').innerText(), {pending:pending.length,errors});
            throw error;
        });
        assert.deepEqual(await page.evaluate(()=>window.__emptyFlashes),[]);
        const search=page.getByPlaceholder('Search Models');
        await search.fill('not-a-model');
        await page.getByText('No models found',{exact:true}).waitFor();
        await search.fill('');
        await page.getByText('Alpha custom name',{exact:true}).waitFor();
        await close();
        empty=true;
        await page.evaluate(()=>window.__firstOpen.open(false,true));
        await page.getByText('No models installed',{exact:true}).waitFor();
        await page.screenshot({path:`logs/unified-first-open-${width}-empty.png`});
        await close();
        empty=false;failed=true;
        await page.evaluate(()=>window.__firstOpen.open(false));
        await page.getByText('Could not access local models',{exact:true}).waitFor();
        assert.deepEqual(errors,[]);
        results.push({width,readyWithoutWaiting:true,noEmptyFlash:true,realEmptyAndSearchStates:true,errorState:true});
        await page.close();
    }
    await fs.writeFile('logs/unified-first-open-results.json',JSON.stringify(results,null,2));
    console.log(JSON.stringify(results));
} finally {
    await browser?.close();await server?.close();
    await fs.unlink(file);await fs.rmdir(directory);
}
