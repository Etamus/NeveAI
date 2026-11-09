import fs from 'node:fs/promises';
import { constants } from 'node:fs';
import assert from 'node:assert/strict';
import { createServer } from 'vite';
import { chromium } from '../logs/ui-image-26/node_modules/playwright/index.mjs';
import { installMobileOfflineApi } from './fixtures/mobile-offline-api.mjs';

const dir=new URL('../src/routes/__message_typography/',import.meta.url),file=new URL('+page.svelte',dir);
let server,browser;
const results=[];
try {
 await fs.mkdir(dir,{recursive:true});
 await fs.copyFile(new URL('./fixtures/message-typography.svelte',import.meta.url),file,constants.COPYFILE_EXCL);
 server=await createServer({plugins:[{name:'fixture',configResolved(c){c.server.proxy=undefined;}}],server:{port:5194,strictPort:true,watch:{ignored:['**/logs/**']}}});
 await server.listen();browser=await chromium.launch();
 for(const width of [1440,390]) for(const scale of [1,1.15]) for(const theme of ['dark','light']){
  const page=await browser.newPage({viewport:{width,height:1100}}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));await installMobileOfflineApi(page);
  await page.goto('http://localhost:5194/__message_typography',{waitUntil:'networkidle',timeout:120000});
  await page.waitForFunction(()=>window.__typography);
  await page.evaluate(({theme,scale})=>{document.documentElement.classList.toggle('dark',theme==='dark');document.documentElement.style.setProperty('--app-text-scale',scale);},{theme,scale});
  await page.locator('#chat-input').fill('Texto de exemplo');await page.evaluate(()=>document.fonts.ready);await page.waitForTimeout(250);
  const typography=async locator=>locator.evaluate(e=>{const s=getComputedStyle(e);return {font:s.fontFamily,size:s.fontSize};});
  const input=await typography(page.locator('#chat-input'));
  assert.deepEqual(await typography(page.locator('.chat-user-content')),input);
  const paragraph=page.locator('.chat-assistant p').first();
  assert.deepEqual(await typography(paragraph),input);
  assert.deepEqual(await typography(page.locator('.chat-assistant li').first()),input);
  assert.notEqual((await typography(page.locator('.chat-assistant pre code').first())).font,input.font);
  const before=await paragraph.boundingBox();
  await page.evaluate(()=>window.__typography.done(false));await page.waitForTimeout(100);
  await page.evaluate(()=>window.__typography.done(true));await page.waitForTimeout(100);
  assert.deepEqual(await paragraph.boundingBox(),before,'Completion must not change text geometry');
  await page.locator('.edit-user-message-button').click();
  const editor=page.locator('#message-edit-question');await editor.waitFor();
  assert.deepEqual(await typography(editor),input);
  const cancel=page.locator('#close-edit-message-button');
  assert.equal(await cancel.evaluate(e=>getComputedStyle(e).color),theme==='dark'?'rgb(255, 255, 255)':'rgb(0, 0, 0)');
  const box=editor.locator('..').locator('..');
  const radius=await box.evaluate(e=>parseFloat(getComputedStyle(e).borderTopLeftRadius));
  const root=await page.evaluate(()=>parseFloat(getComputedStyle(document.documentElement).fontSize));
  assert(Math.abs(radius-root*1.25)<0.1);
  await page.mouse.move(width-1,1);await page.waitForTimeout(200);
  const normal=await cancel.evaluate(e=>getComputedStyle(e).backgroundColor);
  await cancel.hover();await page.waitForTimeout(220);
  const hover=await cancel.evaluate(e=>getComputedStyle(e).backgroundColor);
  assert.notEqual(normal,hover);
  if(theme==='dark'){assert(normal.endsWith('0.1)'));assert(hover.endsWith('0.05)'));}
  else assert(parseFloat(hover.match(/[\d.]+/)[0])<parseFloat(normal.match(/[\d.]+/)[0]));
  await box.screenshot({path:`logs/message-editor-${width}-${scale}-${theme}.png`});
  await editor.fill('Rascunho descartado');await cancel.click();
  assert.equal(await page.locator('.chat-user-content').innerText(),'Texto de exemplo para comparar a fonte e o tamanho das mensagens.');
  assert.equal((await page.evaluate(()=>window.__typography.submitted())).length,0);
  await page.locator('.edit-user-message-button').click();await editor.fill('Edicao confirmada');
  await page.locator('#confirm-edit-message-button').click();
  assert.equal((await page.evaluate(()=>window.__typography.submitted()))[0][1].content,'Edicao confirmada');
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  assert.deepEqual(errors,[]);results.push({width,scale,theme,input,radius,normal,hover,errors});await page.close();
 }
 console.log(JSON.stringify(results,null,2));
 await fs.writeFile('logs/message-typography-results.json',JSON.stringify(results,null,2));
}finally{await browser?.close();await server?.close();await fs.rm(file,{force:true});await fs.rmdir(dir).catch(()=>{});}
