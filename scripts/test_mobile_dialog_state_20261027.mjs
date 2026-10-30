import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
import {createServer} from 'vite';
import {chromium} from '../logs/ui-image-26/node_modules/playwright/index.mjs';

const list=await(await fetch('http://localhost:8080/api/v1/chats/list')).json();
const chatId=list[0]?.id;assert(chatId,'A saved chat is required for the state regression test');
const original=await(await fetch('http://localhost:8080/api/v1/chats/'+chatId)).json();
let server,browser;const results=[];
try{
 server=await createServer({plugins:[{name:'mobile-state-audit',enforce:'pre',async load(id){
  if(id.endsWith('/src/routes/(app)/+layout.svelte'))return(await fs.readFile(id,'utf8')).replace('</script>',`onMount(()=>{window.__dialogState={settings:()=>showSettings.set(true),search:()=>showSearch.set(true)};return()=>delete window.__dialogState;});\n</script>`);
 }}],server:{port:5188,strictPort:true,watch:{ignored:['**/logs/**','**/scripts/**','**/docs/**']}}});await server.listen();
 browser=await chromium.launch();const page=await browser.newPage({viewport:{width:390,height:844},hasTouch:true});page.setDefaultTimeout(20000);
 let chatReads=0;const errors=[];page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(new URL(r.url()).pathname==='/api/v1/chats/'+chatId)chatReads++;});
 await page.route('**/api/**',r=>r.request().method()==='GET'||r.request().url().includes('/auths/')?r.continue():r.fulfill({json:{}}));
 await page.goto('http://localhost:5188/c/'+chatId,{waitUntil:'networkidle',timeout:90000});await page.waitForFunction(()=>window.__dialogState);await page.locator('#chat-input').waitFor({state:'visible'});await page.waitForTimeout(500);
 await page.locator('#chat-input').fill('Rascunho preservado durante a navegacao dos modais');
 await page.locator('#messages-container').evaluate(e=>e.scrollTop=Math.floor((e.scrollHeight-e.clientHeight)/2));await page.waitForTimeout(300);
 const snapshot=()=>page.evaluate(()=>({url:location.href,top:document.querySelector('#messages-container').scrollTop,draft:document.querySelector('#chat-input').textContent,
  rows:[...document.querySelectorAll('#messages-container [role="listitem"]')].map(e=>({text:e.textContent.slice(0,150),top:e.getBoundingClientRect().top}))}));
 const baseline=await snapshot(),initialReads=chatReads;
 const back=async()=>{if(process.env.DIALOG_BACK_BUTTON)await page.locator('.modal[aria-hidden="false"] .mobile-modal-back').last().click();else await page.evaluate(()=>history.back());await page.waitForTimeout(350);};
 for(const dialog of ['models','search','settings']){
  if(dialog==='models')await page.locator('button[aria-label="Models"]').tap();else await page.evaluate(kind=>window.__dialogState[kind](),dialog);
  await page.waitForTimeout(300);assert(await page.locator('.modal[aria-hidden="false"]').count());
  if(dialog==='settings'){await page.locator('#settings-tabs-container > button').first().tap();await page.waitForTimeout(100);await back();assert(await page.locator('#settings-tabs-container').isVisible());}
  await back();const after=await snapshot();assert.deepEqual(after,baseline,'Dialog navigation changed the chat or draft');assert.equal(chatReads,initialReads,'Shallow dialog history reloaded the chat');results.push({dialog,preserved:true});
 }
 await page.locator('button[aria-label="Models"]').tap();await page.waitForTimeout(250);await page.setViewportSize({width:1000,height:844});await page.waitForTimeout(350);
 const box=await page.locator('.modal[aria-hidden="false"] > div').boundingBox();assert(box.width<999&&box.height<844,'Fullscreen mobile styling leaked into desktop after resize');
 await page.keyboard.press('Escape');await page.waitForTimeout(250);assert.equal(await page.locator('.modal[aria-hidden="false"]').count(),0);
 await page.setViewportSize({width:390,height:844});await page.waitForTimeout(150);await page.locator('button[aria-label="Models"]').tap();await page.waitForTimeout(250);await back();assert.equal(await page.locator('.modal[aria-hidden="false"]').count(),0,'Resize left a trapped dialog history entry');
 assert.equal(JSON.stringify(await(await fetch('http://localhost:8080/api/v1/chats/'+chatId)).json()),JSON.stringify(original),'The original saved chat was modified');
 assert.deepEqual(errors,[]);await fs.writeFile(process.env.DIALOG_STATE_RESULT??'logs/mobile-20261027/state.json',JSON.stringify({chatId,results,chatReads,errors,resize:true,backButton:!!process.env.DIALOG_BACK_BUTTON},null,2));console.log('PASS saved chat/draft, no chat reloads, Back and desktop/mobile resizing');
}finally{await browser?.close();await server?.close();}
