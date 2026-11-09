import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {createServer} from 'vite';
import {chromium} from '../logs/ui-image-26/node_modules/playwright/index.mjs';

let server,browser;
const results=[];
try{
 server=await createServer({server:{port:5190,strictPort:true,watch:{ignored:['**/logs/**','**/scripts/**','**/docs/**']}}});
 await server.listen();browser=await chromium.launch();
 for(const width of [1440,390]){
  const page=await browser.newPage({viewport:{width,height:1000}}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/api/v1/chats/**',route=>route.request().method()==='GET'?route.continue():route.fulfill({json:{}}));
  await page.goto('http://localhost:5190/c/f65f45de-0c88-4e85-a18d-961ce5190f32',{waitUntil:'domcontentloaded',timeout:90000});
  const table=page.locator('#message-8b08c3fb-09f0-4572-91e7-e1ed9fe79fa6 table');
  await table.waitFor({timeout:90000});await table.scrollIntoViewIfNeeded();await page.evaluate(()=>document.fonts.ready);
  assert.equal(await table.locator('thead th').count(),5);
  assert.equal(await table.locator('tbody tr').count(),8);
  if(width<768)assert(await table.locator('thead th').first().evaluate(e=>e.getBoundingClientRect().width>=119),'Mobile columns must remain readable inside the horizontal scroller');
  for(const row of await table.locator('tbody tr').all())assert.equal(await row.locator('td').count(),5);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  await page.screenshot({path:`logs/table-recovery-${width}.png`});
  if(width===1440){
   const diagram=page.locator('#message-ffdf2e23-040b-4c4a-98d4-b58159d25bb1 .code-shell');
   const buttons=diagram.locator('button');
   await buttons.nth(1).hover();
   await page.locator('[data-tippy-root] .tippy-content').filter({hasText:/^Redefinir$/}).waitFor();
   await buttons.nth(2).hover();
   await page.locator('[data-tippy-root] .tippy-content').filter({hasText:/^Copiar$/}).waitFor();
  }
  assert.deepEqual(errors,[]);
  results.push({width,headers:5,rows:8,errors});await page.close();
 }
 await fs.writeFile('logs/table-recovery-visual.json',JSON.stringify(results,null,2));
 console.log(JSON.stringify(results));
}finally{await browser?.close();await server?.close();}
