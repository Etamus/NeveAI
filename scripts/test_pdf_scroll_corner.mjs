import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
import { createServer } from 'vite';
import { chromium } from '../logs/ui-image-26/node_modules/playwright/index.mjs';
import { installMobileOfflineApi } from './fixtures/mobile-offline-api.mjs';
const directory=new URL('../src/routes/__pdf_corner_test/',import.meta.url),route=new URL('+page.svelte',directory);
let server,browser;
const results=[];
try {
  await fs.mkdir(directory,{recursive:true});
  const source=(await fs.readFile(new URL('fixtures/pdf-scroll-corner.svelte',import.meta.url),'utf8')).replace('../../src/','../../');
  await fs.writeFile(route,source,{flag:'wx'});
  server=await createServer({plugins:[{name:'pdf-corner-test',configResolved(config){config.server.proxy=undefined;}}],server:{port:5195,strictPort:true}});await server.listen();
  browser=await chromium.launch();
  for(const theme of ['dark','light']) {
    const page=await browser.newPage({viewport:{width:900,height:800}}),errors=[];
    // The pinned test browser predates the Map API used by the installed PDF.js.
    await page.addInitScript(()=>{
      for(const type of [Map,WeakMap]) if(!type.prototype.getOrInsertComputed) {
        Object.defineProperty(type.prototype,'getOrInsertComputed',{value:function(key,create){if(!this.has(key))this.set(key,create(key));return this.get(key);},configurable:true,writable:true});
      }
    });
    page.on('pageerror',error=>errors.push(error.message));
    page.on('console',message=>{if(message.type()==='error')console.error(message.text());});
    await installMobileOfflineApi(page);
    await page.goto('http://localhost:5195/__pdf_corner_test',{waitUntil:'networkidle',timeout:120000});
    await page.evaluate(theme=>document.documentElement.classList.toggle('dark',theme==='dark'),theme);
    await page.locator('canvas[data-rendered=true]').waitFor().catch(async error=>{
      await page.screenshot({path:'logs/pdf-scroll-corner-failure.png'});
      throw new Error(error.message+'\n'+JSON.stringify(errors)+'\n'+await page.locator('body').innerText());
    });
    await page.getByRole('button',{name:'Zoom in',exact:true}).click({clickCount:3});
    await page.waitForTimeout(500);
    const measure=await page.locator('#pdf-frame .overflow-y-auto').evaluate(element=>({x:element.scrollWidth>element.clientWidth,y:element.scrollHeight>element.clientHeight,corner:getComputedStyle(element,'::-webkit-scrollbar-corner').backgroundColor}));
    assert.ok(measure.x&&measure.y,'Zoom must exercise both scrollbars');
    assert.equal(measure.corner,'rgba(0, 0, 0, 0)');
    assert.equal(await page.locator('#document-scroll').evaluate(element=>getComputedStyle(element,'::-webkit-scrollbar-corner').backgroundColor),'rgba(0, 0, 0, 0)');
    await page.screenshot({path:`logs/pdf-scroll-corner-${theme}.png`});
    await page.getByRole('button',{name:'Reset zoom',exact:true}).click();
    assert.equal(await page.getByRole('button',{name:'Reset zoom',exact:true}).innerText(),'100%');
    assert.deepEqual(errors,[]);results.push({theme,...measure,errors});await page.close();
  }
  await fs.writeFile('logs/pdf-scroll-corner-results.json',JSON.stringify(results,null,2));
  console.log('PDF zoom, reset and scrollbar corners passed in both themes');
} finally {await browser?.close();await server?.close();await fs.rm(route,{force:true});await fs.rmdir(directory).catch(()=>{});}
