import fs from 'node:fs/promises';
import { constants } from 'node:fs';
import assert from 'node:assert/strict';
import { createServer } from 'vite';
import { chromium } from '../logs/ui-image-26/node_modules/playwright/index.mjs';
import { installMobileOfflineApi } from './fixtures/mobile-offline-api.mjs';

const dir=new URL('../src/routes/__sidebar_actions_test/',import.meta.url);
const file=new URL('+page.svelte',dir);
let server,browser;
const results=[];
try {
 await fs.mkdir(dir,{recursive:true});
 await fs.copyFile(new URL('./fixtures/sidebar-actions.svelte',import.meta.url),file,constants.COPYFILE_EXCL);
 server=await createServer({plugins:[{name:'fixture',configResolved(c){c.server.proxy=undefined;}}],server:{port:5195,strictPort:true,watch:{ignored:['**/logs/**']}}});
 await server.listen();browser=await chromium.launch();
 for(const width of [1440,390]) for(const theme of ['dark','light']) {
  const page=await browser.newPage({viewport:{width,height:900}}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));await installMobileOfflineApi(page);
  await page.goto('http://localhost:5195/__sidebar_actions_test',{waitUntil:'networkidle',timeout:120000});
  await page.waitForFunction(()=>window.__sidebarActions);
  await page.evaluate(()=>document.querySelector('#sidebar').addEventListener('click',e=>{if(e.target.closest('a'))e.preventDefault();},true));
  await page.evaluate(t=>document.documentElement.classList.toggle('dark',t==='dark'),theme);
  await page.evaluate(()=>document.fonts.ready);
  const geometry=[];
  for(const row of await page.locator('#sidebar-chat-group').all()) {
   await row.hover();
   const pin=row.getByRole('button',{name:/^(Fixar|Desfixar)$/});
   const more=row.locator('button[aria-label="Chat Menu"]');
   const p=await pin.boundingBox(),m=await more.boundingBox(),r=await row.boundingBox();
   const centers=await row.locator('.sidebar-chat-actions button[aria-label]:not(.hidden)').evaluateAll(buttons=>buttons.map(button=>{
    const b=button.getBoundingClientRect(),row=button.closest('#sidebar-chat-group').getBoundingClientRect(),svg=button.querySelector('svg'),s=svg.getBoundingClientRect(),ink=svg.getBBox(),vb=svg.viewBox.baseVal;
    return {label:button.getAttribute('aria-label'),buttonCenter:b.y+b.height/2-row.y-row.height/2,svgCenter:s.y+s.height/2-b.y-b.height/2,inkCenter:s.y+(ink.y+ink.height/2-vb.y)*s.height/vb.height-row.y-row.height/2};
   }));
   for(const center of centers){assert(Math.abs(center.buttonCenter)<0.05);assert(Math.abs(center.svgCenter-0.5)<0.05);}
   await row.screenshot({path:`logs/sidebar-row-${width}-${theme}-${await row.locator('a').getAttribute('href').then(value=>value.split('/').pop())}.png`});
   assert(p.x+p.width<=m.x,'Pin must precede More visually and in tab order');
   assert(m.x+m.width<=r.x+r.width+1,'Actions must remain inside the row');
   const order=await row.locator('.sidebar-chat-actions button[aria-label]:not(.hidden)').evaluateAll(es=>es.map(e=>e.getAttribute('aria-label')));
   assert.match(order[0],/^(Fixar|Desfixar)$/);assert.equal(order[1],'Chat Menu');
   await more.evaluate(button=>button.click());
   await page.getByText('Renomear',{exact:true}).waitFor();
   await page.keyboard.press('Escape');
   geometry.push({pin:p.x,more:m.x,right:r.x+r.width-(m.x+m.width),centers});
  }
  const toast=page.locator('#update-fixture');
  assert.match(await toast.innerText(),/NeveAI v3\.1\.83 e mais/);
  assert.doesNotMatch(await toast.innerText(),/llama\.cpp/);
  await toast.getByRole('button',{name:'Detalhes',exact:true}).click();
  assert.equal(await page.evaluate(()=>window.__sidebarActions.opened()),1);
  await page.screenshot({path:`logs/sidebar-actions-${width}-${theme}.png`});
  for(const value of ['NeveAI v3.1.83','llama.cpp b12167']) {
   await page.evaluate(value=>window.__sidebarActions.version(value),value);
   assert((await toast.innerText()).includes(value));assert.doesNotMatch(await toast.innerText(),/e mais/);
  }
  assert.deepEqual(errors,[]);results.push({width,theme,geometry,errors});await page.close();
 }
 console.log(JSON.stringify(results,null,2));
 await fs.writeFile(`logs/sidebar-actions-results${process.env.BASELINE?'-before':''}.json`,JSON.stringify(results,null,2));
} finally {await browser?.close();await server?.close();await fs.rm(file,{force:true});await fs.rmdir(dir).catch(()=>{});}
