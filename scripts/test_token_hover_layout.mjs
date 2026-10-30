import assert from 'node:assert/strict';
import {createServer} from 'vite';
import {chromium} from '../logs/ui-image-26/node_modules/playwright/index.mjs';
let server,browser;
try{
 server=await createServer({server:{port:5188,strictPort:true,watch:{ignored:['**/logs/**','**/scripts/**','**/docs/**']}}});await server.listen();browser=await chromium.launch();
 for(const viewport of [{width:1440,height:1000},{width:900,height:800},{width:390,height:844}]){
  const page=await browser.newPage({viewport});await page.route('**/api/**',r=>r.request().method()==='GET'||r.request().url().includes('/auths/')?r.continue():r.fulfill({json:{}}));
  await page.goto('http://localhost:5188/c/a0bf5564-5162-457b-af95-65c6d789ebaf',{waitUntil:'domcontentloaded',timeout:90000});
  const input=page.locator('#chat-input'),trigger=page.locator('[data-token-usage-trigger]:visible');await trigger.waitFor({timeout:60000});await page.evaluate(()=>document.fonts.ready);await page.waitForTimeout(500);
  const count=await input.evaluate(e=>{const p=e.querySelector('p'),s=getComputedStyle(p),c=document.createElement('canvas').getContext('2d');c.font=`${s.fontWeight} ${s.fontSize} ${s.fontFamily}`;return Math.floor(p.clientWidth/c.measureText('w').width);});
  for(let n=Math.max(1,count-3);n<=count;n++){
   await input.fill('');await input.fill('w'.repeat(n));await page.waitForTimeout(150);
   if(!await page.locator('.composer-compact-controls').count())continue;
   const measure=()=>page.locator('#message-input-container').evaluate(e=>({h:e.getBoundingClientRect().height,scroll:document.querySelector('#messages-container').scrollTop}));
   const before=await measure();if(viewport.width<600)await trigger.click();else await trigger.hover();await page.waitForTimeout(200);const after=await measure();
   console.log(JSON.stringify({viewport,n,before,after}));assert.equal(after.h,before.h,'Token hover resized the composer');assert.equal(after.scroll,before.scroll,'Token hover scrolled the chat');
   if(viewport.width<600)await trigger.click();else await page.mouse.move(2,2);await page.waitForTimeout(200);
  }
  await page.close();
 }
}finally{await browser?.close();await server?.close();}
