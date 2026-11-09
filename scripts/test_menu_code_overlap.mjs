import fs from 'node:fs/promises';
import {constants} from 'node:fs';
import {createRequire} from 'node:module';
import assert from 'node:assert/strict';
import {createServer} from 'vite';
import {chromium} from '../logs/ui-image-26/node_modules/playwright/index.mjs';
import {installMobileOfflineApi} from './fixtures/mobile-offline-api.mjs';
const require=createRequire(import.meta.url);
const {PNG}=require('../logs/ui-image-26/node_modules/playwright-core/lib/utilsBundle.js');
const dir=new URL('../src/routes/__menu_code_overlap/',import.meta.url),file=new URL('+page.svelte',dir);
let server,browser;const results=[];
try{
    await fs.mkdir(dir,{recursive:true});await fs.copyFile(new URL('./fixtures/menu-code-overlap.svelte',import.meta.url),file,constants.COPYFILE_EXCL);
    server=await createServer({plugins:[{name:'overlap-fixture',configResolved(c){c.server.proxy=undefined;}}],server:{port:5196,strictPort:true,watch:{ignored:['**/logs/**']}}});
    await server.listen();browser=await chromium.launch({ignoreDefaultArgs:['--hide-scrollbars']});
    for(const width of [1440,900,390])for(const theme of ['dark','light']){
        const page=await browser.newPage({viewport:{width,height:900}}),errors=[];page.on('pageerror',e=>errors.push(e.message));await installMobileOfflineApi(page);
        await page.goto('http://localhost:5196/__menu_code_overlap',{waitUntil:'networkidle',timeout:120000});
        await page.evaluate(t=>document.documentElement.classList.toggle('dark',t==='dark'),theme);
        await page.locator('#open-menu').click();const menu=page.locator('.composer-integrations-menu');await menu.waitFor();await page.waitForTimeout(180);
        const measure=await menu.evaluate(e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return {x:r.x,y:r.y,width:r.width,height:r.height,clip:s.backgroundClip,background:s.backgroundColor,border:s.borderTopColor};});
        const screenshot=`logs/menu-code-${width}-${theme}${process.env.BASELINE?'-before':''}.png`;await page.screenshot({path:screenshot});
        const png=PNG.sync.read(await fs.readFile(screenshot));
        const sample=(x,y)=>{const offset=(Math.floor(y)*png.width+Math.floor(x))*4;return [...png.data.subarray(offset,offset+3)];};
        const y=Math.ceil(measure.y),left=Math.ceil(measure.x+100),right=Math.floor(measure.x+measure.width-45);
        const before=sample(left,y),outside=sample(right,y);
        results.push({width,theme,measure,overCode:before,overPage:outside,errors});
        if(!process.env.BASELINE){assert.equal(measure.clip,'border-box');assert.deepEqual(before,outside,'Menu top border must not depend on the codeblock underneath');assert.deepEqual(errors,[]);}
        await menu.getByText('Web Search',{exact:true}).click();await menu.waitFor({state:'hidden'});
        await page.locator('#open-menu').click();await menu.waitFor();await page.keyboard.press('Escape');await menu.waitFor({state:'hidden'});
        const code=page.locator('.code-scroll').first();await code.hover();await page.mouse.wheel(0,120);await page.waitForTimeout(100);
        assert.ok(await code.evaluate(e=>e.scrollTop)>0,'Code scrolling must remain functional');
        assert.equal(await page.evaluate(()=>window.scrollY),0,'Inner code scroll must not move the page');
        await page.close();
    }
    await fs.writeFile(`logs/menu-code-results${process.env.BASELINE?'-before':''}.json`,JSON.stringify(results,null,2));console.log(JSON.stringify(results));
}finally{await browser?.close();await server?.close();await fs.rm(file,{force:true});await fs.rmdir(dir).catch(()=>{});}
