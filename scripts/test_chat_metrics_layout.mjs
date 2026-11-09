import fs from 'node:fs/promises';
import { constants } from 'node:fs';
import assert from 'node:assert/strict';
import { createServer } from 'vite';
import { chromium } from '../logs/ui-image-26/node_modules/playwright/index.mjs';
import { installMobileOfflineApi } from './fixtures/mobile-offline-api.mjs';
const dir=new URL('../src/routes/__metrics_layout_test/',import.meta.url),file=new URL('+page.svelte',dir);
let server,browser;
const results=[];
try {
    await fs.mkdir(dir,{recursive:true});
    await fs.copyFile(new URL('./fixtures/chat-metrics-layout.svelte',import.meta.url),file,constants.COPYFILE_EXCL);
    server=await createServer({plugins:[{name:'metrics-fixture',configResolved(c){c.server.proxy=undefined;}}],server:{port:5196,strictPort:true,watch:{ignored:['**/logs/**']}}});
    await server.listen();browser=await chromium.launch();
    for(const width of [1440,900,390]) for(const theme of ['dark','light']) {
        const page=await browser.newPage({viewport:{width,height:1000}}),errors=[];
        page.on('pageerror',e=>errors.push(e.message));await installMobileOfflineApi(page);
        await page.goto('http://localhost:5196/__metrics_layout_test',{waitUntil:'networkidle',timeout:120000});
        await page.waitForFunction(()=>window.__metrics);
        await page.evaluate(t=>document.documentElement.classList.toggle('dark',t==='dark'),theme);
        await page.evaluate(()=>document.fonts.ready);
        await page.evaluate(()=>document.querySelector('#sidebar').addEventListener('click',e=>{if(e.target.closest('a'))e.preventDefault();},true));
        const measure=()=>page.locator('#sidebar-chat-item').first().evaluate(e=>{
            const r=e.getBoundingClientRect(),title=e.querySelector('[dir=auto]')??e.querySelector('input'),t=title.getBoundingClientRect();
            return {row:{top:r.top,height:r.height},title:{top:t.top,height:t.height},font:getComputedStyle(title).fontFamily};
        });
        const before=await measure();
        await page.screenshot({path:`logs/chat-metrics-${width}-${theme}${process.env.BASELINE?'-baseline':''}.png`});
        if(process.env.BASELINE){console.log({width,theme,before});await page.close();continue;}
        const typography=await page.locator('#fixture-markdown').evaluate(e=>Object.fromEntries(['h1','h2','h3','p'].map(tag=>[tag,getComputedStyle(e.querySelector(tag)).fontSize])));
        assert.ok(parseFloat(typography.h1)<=parseFloat(typography.p)*1.51);assert.ok(parseFloat(typography.h1)>=parseFloat(typography.h2));
        assert.equal(await page.locator('[data-token-usage-percentage]').count(),0);
        const trigger=page.locator('[data-token-usage-trigger]');
        if(width<768)await trigger.click();else await trigger.hover();
        const popup=page.locator('[data-token-usage-popup]');await popup.waitFor();
        await page.evaluate(()=>window.__metrics.update({prompt_n:600,predicted_n:20,predicted_per_second:42.3,context_window:8192}));
        await page.waitForTimeout(100);assert.match(await popup.innerText(),/120/);assert.match(await popup.innerText(),/42/);
        await page.evaluate(()=>window.__metrics.update({prompt_n:600,predicted_n:40,predicted_per_second:52.8,context_window:8192}));
        await page.waitForTimeout(100);assert.match(await popup.innerText(),/120/);assert.match(await popup.innerText(),/53/);
        await page.waitForTimeout(3000);assert.match(await popup.innerText(),/120/);
        await page.waitForTimeout(1100);assert.match(await popup.innerText(),/640/);
        await page.evaluate(()=>window.__metrics.update({total_tokens:650,tokens_per_second:51,context_window:8192},true));
        await page.waitForTimeout(100);assert.match(await popup.innerText(),/650/);assert.match(await popup.innerText(),/51/);
        await page.mouse.move(width-1,1);
        for(const id of ['regular','pinned']) {
            const row=page.locator('#sidebar-chat-group').nth(id==='regular'?0:1);
            await row.locator('a').dblclick();
            const input=row.locator('input');await input.waitFor();
            const geom=await input.evaluate(e=>{const r=e.getBoundingClientRect(),p=e.parentElement.getBoundingClientRect();return {center:r.top+r.height/2-(p.top+p.height/2),opticalOffset:parseFloat(getComputedStyle(e).fontSize)*-.0625};});
            assert.ok(Math.abs(geom.center-geom.opticalOffset)<0.6);await input.press('Escape');
        }
        const after=await measure();assert.deepEqual(after,before,'Rename must not move the row/title');
        await page.screenshot({path:`logs/chat-metrics-${width}-${theme}.png`});
        assert.deepEqual(errors,[]);results.push({width,theme,before,typography,liveUsage:true,renameStable:true,errors});
        await page.close();
    }
    await fs.writeFile('logs/chat-metrics-layout-results.json',JSON.stringify(results,null,2));console.log(JSON.stringify(results));
} finally {await browser?.close();await server?.close();await fs.rm(file,{force:true});await fs.rmdir(dir).catch(()=>{});}
