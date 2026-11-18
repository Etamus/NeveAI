import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {chromium} from '../logs/ui-image-26/node_modules/playwright/index.mjs';

const browser=await chromium.launch();
try{
 const page=await browser.newPage();let requests=0;const errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/api/chat/completions',route=>{requests++;return route.fulfill({json:{task_id:'must-not-start'}});});
 await page.addInitScript(()=>{
  const NativeWorker=window.Worker;
  window.Worker=class extends NativeWorker{
   constructor(...args){super(...args);this.delayed=String(args[0]).includes('chat-request');}
   postMessage(...args){if(this.delayed)setTimeout(()=>{if(!this.ended)super.postMessage(...args);},500);else super.postMessage(...args);}
   terminate(){this.ended=true;return super.terminate();}
  };
 });
 await page.goto('http://127.0.0.1:8080/?temporary-chat=true',{waitUntil:'networkidle'});
 await page.locator('#input-menu-button').click();await page.getByText('Criar imagem',{exact:true}).click();
 await page.locator('#image-quality-dropdown-container > button').click();await page.getByText('Neve Image 2.8',{exact:true}).click();
 await page.locator('input[type=file]').nth(1).setInputFiles('backend/data/uploads/0e335168-40a8-473e-a233-1dd5f1cfb0c6_image.png');
 await page.waitForFunction(()=>[...document.querySelectorAll('#message-input-container img')].some(i=>i.complete && i.naturalWidth>0));
 await page.locator('#chat-input').fill('Edit');await page.waitForTimeout(500);
 await page.locator('#send-message-button').click();await page.waitForTimeout(50);
 await page.locator('#send-message-button').click();await page.waitForTimeout(1500);
 const stopped=await page.locator('[data-composer-root]').getAttribute('data-generating');
 assert.equal(requests,0);assert.equal(stopped,'false');assert.deepEqual(errors,[]);
 await fs.writeFile('logs/base64-early-stop.json',JSON.stringify({requests,stopped,errors}));
 console.log('Early Stop: no request dispatched, no generation, no JavaScript errors');
}finally{await browser.close();}
