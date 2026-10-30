import fs from 'node:fs/promises';
import {constants} from 'node:fs';
import assert from 'node:assert/strict';
import {createServer} from 'vite';
import {chromium} from '../logs/ui-image-26/node_modules/playwright/index.mjs';
const dir=new URL('../src/routes/__paint_test/',import.meta.url),file=new URL('+page.svelte',dir);
await fs.mkdir(dir,{recursive:true});await fs.copyFile(new URL('./fixtures/paint-overlays.svelte',import.meta.url),file,constants.COPYFILE_EXCL);
let server,browser;
try{
 server=await createServer({server:{port:5188,strictPort:true,watch:{ignored:['**/logs/**']}}});await server.listen();
 browser=await chromium.launch();
 for(const viewport of [{width:1440,height:1000},{width:390,height:844}]){
  const page=await browser.newPage({viewport});const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/api/chat/completions',r=>r.abort());
  await page.goto('http://localhost:5188/__paint_test',{waitUntil:'domcontentloaded',timeout:90000});
  const open=page.locator('#open-preview');await open.click();
  const modal=page.locator('.modal');await modal.waitFor();
  assert.equal(await modal.evaluate(el=>el.parentElement===document.body),true);
  const box=await modal.boundingBox();assert(Math.abs(box.width-viewport.width)<2);
  await page.getByText('Close preview',{exact:true}).click();await modal.waitFor({state:'detached'});
  await page.locator('#test-tooltip').hover();const tip=page.locator('[data-tippy-root]');await tip.waitFor({state:'visible'});
  assert.equal(await tip.evaluate(el=>el.closest('#messages-container')===null),true);
  await page.mouse.move(2,2);
  await page.locator('#messages-container').evaluate(el=>el.scrollTop=0);
  await page.locator('#messages-container p').evaluate(el=>{const range=document.createRange();range.selectNodeContents(el);const s=getSelection();s.removeAllRanges();s.addRange(range);el.dispatchEvent(new MouseEvent('mouseup',{bubbles:true}));});
  const selection=page.locator('#floating-buttons-paint-selection');await selection.waitFor({state:'visible'});
  assert.equal(await selection.evaluate(el=>el.closest('#messages-container')===null),true);
  await page.evaluate(()=>getSelection().removeAllRanges());await page.mouse.click(2,2);
  const source=page.locator('[data-link-preview-trigger]');await source.scrollIntoViewIfNeeded();await source.hover();
  const popover=page.locator('[data-link-preview-content]');await popover.waitFor({state:'visible'});
  assert.equal(await popover.evaluate(el=>el.closest('#messages-container')===null),true);
  const rect=await popover.boundingBox();assert(rect.x>=0&&rect.y>=0&&rect.x+rect.width<=viewport.width+1&&rect.y+rect.height<=viewport.height+1);
  assert.deepEqual(errors,[]);await page.screenshot({path:`logs/paint-overlays-${viewport.width}.png`});console.log(JSON.stringify({viewport,modal:true,tooltip:true,selection:true,sources:true,errors}));await page.close();
 }
}finally{await browser?.close();await server?.close();await fs.unlink(file);await fs.rmdir(dir);}
