import fs from 'node:fs/promises';
import {constants} from 'node:fs';
import assert from 'node:assert/strict';
import {createServer} from 'vite';
import {chromium} from '../logs/ui-image-26/node_modules/playwright/index.mjs';
import {installMobileOfflineApi} from './fixtures/mobile-offline-api.mjs';
const dir=new URL('../src/routes/__media_tokens/',import.meta.url),file=new URL('+page.svelte',dir);
let server,browser;const results=[];
const usage={total_tokens:420,context_window:8192,tokens_per_second:60};
const assistant=extra=>({role:'assistant',done:true,usage,...extra});
const cases=[
 ['image-only',{currentId:'a',messages:{a:assistant({statusHistory:[{action:'stable_diffusion',done:true}]})}},false],
 ['video-only',{currentId:'a',messages:{a:assistant({statusHistory:[{action:'video_generation',done:true}]})}},false],
 ['pending-image',{currentId:'a',messages:{a:{role:'assistant',done:false,token_usage_eligible:false,context_window:8192}}},false],
 ['older-video',{currentId:'a',messages:{u:{role:'user',video_generation_features:{video_generation:true}},a:assistant({parentId:'u'})}},false],
 ['normal',{currentId:'a',messages:{a:assistant({})}},true],
 ['music',{currentId:'a',messages:{a:assistant({statusHistory:[{action:'music_generation'}]})}},true],
 ['web',{currentId:'a',messages:{a:assistant({statusHistory:[{action:'web_search'}]})}},true],
 ['documents',{currentId:'a',messages:{a:assistant({statusHistory:[{action:'file_generation'}]})}},true],
 ['normal-image-attachment',{currentId:'a',messages:{u:{role:'user',files:[{type:'image'}]},a:assistant({parentId:'u'})}},true],
 ['mixed',{currentId:'a',messages:{normal:assistant({}),a:assistant({parentId:'normal',statusHistory:[{action:'stable_diffusion'}]})}},true],
 ['normal-after-media',{currentId:'a',messages:{media:assistant({statusHistory:[{action:'video_generation'}]}),a:assistant({parentId:'media'})}},true],
];
try {
 await fs.mkdir(dir,{recursive:true});await fs.copyFile(new URL('./fixtures/chat-metrics-layout.svelte',import.meta.url),file,constants.COPYFILE_EXCL);
 server=await createServer({plugins:[{name:'fixture',configResolved(c){c.server.proxy=undefined;}}],server:{port:5196,strictPort:true,watch:{ignored:['**/logs/**']}}});
 await server.listen();browser=await chromium.launch();
 for(const width of [1440,390])for(const theme of ['dark','light']) {
  const page=await browser.newPage({viewport:{width,height:1000}}),errors=[];page.on('pageerror',e=>errors.push(e.message));await installMobileOfflineApi(page);
  await page.goto('http://localhost:5196/__media_tokens',{waitUntil:'networkidle',timeout:120000});await page.waitForFunction(()=>window.__metrics);
  await page.evaluate(t=>document.documentElement.classList.toggle('dark',t==='dark'),theme);
  for(const expanded of [false,true]) {
   await page.locator('#chat-input').fill(expanded?'A long composer message with multiple lines.\n'.repeat(12):'Short draft');
   for(const [label,history,visible] of cases) {
    await page.evaluate(async h=>{await window.__metrics.integration('');await window.__metrics.setHistory(h);},history);
    assert.equal(await page.locator('[data-token-usage-trigger]').count(),Number(visible),`${width}/${theme}/${expanded}/${label}`);
    results.push({width,theme,expanded,label,visible});
   }
   const normal={currentId:'a',messages:{a:assistant({})}};
   await page.evaluate(h=>window.__metrics.setHistory(h),normal);
   for(const kind of ['image','video','music','']) {
    await page.evaluate(k=>window.__metrics.integration(k),kind);
    assert.equal(await page.locator('[data-token-usage-trigger]').count(),Number(kind!=='image'&&kind!=='video'),kind);
   }
  }
  assert.deepEqual(errors,[]);await page.screenshot({path:`logs/media-tokens-${width}-${theme}.png`});await page.close();
 }
 await fs.writeFile('logs/media-token-visual.json',JSON.stringify(results,null,2));console.log({cases:results.length,errors:0});
}finally{await browser?.close();await server?.close();await fs.rm(file,{force:true});await fs.rmdir(dir).catch(()=>{});}
