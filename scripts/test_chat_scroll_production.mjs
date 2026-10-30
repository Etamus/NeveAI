import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {chromium} from '../logs/ui-image-26/node_modules/playwright/index.mjs';

const browser=await chromium.launch({ignoreDefaultArgs:['--hide-scrollbars']});
const results=[];
const chatId=process.env.PRODUCTION_CHAT??'c7e7801e-c017-4961-8d2b-c13848330d2b';
try{
 for(const viewport of [{width:1440,height:1000},{width:390,height:844}]){
  const page=await browser.newPage({viewport});const errors=[];page.on('pageerror',e=>errors.push(e.message));
  for(const path of ['/','/c/'+chatId]){
   await page.goto('http://localhost:8080'+path,{waitUntil:'networkidle',timeout:90000});
   await page.locator('#message-input-container').waitFor();await page.evaluate(()=>document.fonts.ready);await page.waitForTimeout(600);
   const viewportElement=page.locator('#messages-container');
   if(path!=='/'){
    const leaked=await page.locator('#response-content-container').evaluateAll(roots=>roots.some(root=>{const copy=root.cloneNode(true);copy.querySelectorAll('.reasoning-text').forEach(n=>n.remove());return /<details\b|<summary>|&gt;|Thinking Process:/.test(copy.textContent);}));
    assert(!leaked,'Saved reasoning leaked in the production build');
    await viewportElement.hover();await page.mouse.wheel(0,-300);await page.waitForTimeout(150);await page.mouse.wheel(0,50000);await page.waitForTimeout(500);
    const before=await viewportElement.evaluate(e=>e.scrollTop);await page.mouse.wheel(0,300);await page.waitForTimeout(150);const after=await viewportElement.evaluate(e=>e.scrollTop);
    assert(Math.abs(after-before)<=1,'Saved chat moved beyond its bottom');
   }
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
   results.push({viewport:viewport.width,path,errors:[...errors]});
  }
  await page.screenshot({path:'logs/chat-scroll-production-'+viewport.width+'.png'});assert.deepEqual(errors,[]);await page.close();
 }
 await fs.writeFile('logs/chat-scroll-production.json',JSON.stringify(results,null,2));console.log('PASS '+results.length+' production views');
}finally{await browser.close();}
