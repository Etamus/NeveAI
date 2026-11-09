import fs from 'node:fs/promises';
import {constants} from 'node:fs';
import assert from 'node:assert/strict';
import {createServer} from 'vite';
import {chromium} from '../logs/ui-image-26/node_modules/playwright/index.mjs';
import {installMobileOfflineApi} from './fixtures/mobile-offline-api.mjs';
const dir=new URL('../src/routes/__learn_artifacts/',import.meta.url),file=new URL('+page.svelte',dir);
let server,browser; const results=[];
try {
 await fs.mkdir(dir,{recursive:true}); await fs.copyFile(new URL('./fixtures/learn-artifacts.svelte',import.meta.url),file,constants.COPYFILE_EXCL);
 server=await createServer({plugins:[{name:'fixture',configResolved(c){c.server.proxy=undefined;}}],server:{port:5197,strictPort:true,watch:{ignored:['**/logs/**']}}});
 await server.listen(); browser=await chromium.launch();
 for(const width of [1440,390]) for(const theme of ['dark','light']) for(const language of ['en-US','pt-BR']) {
  const preview = language === 'pt-BR' ? 'Pré-visualização' : 'Preview';
  const learn = language === 'pt-BR' ? 'Aprender' : 'Learn';
  const tools = language === 'pt-BR' ? 'Ferramentas' : 'Tools';
  const page=await browser.newPage({viewport:{width,height:1000},acceptDownloads:true}); const errors=[];
  page.on('pageerror',e=>errors.push(e.message)); await installMobileOfflineApi(page);
  await page.goto(`http://localhost:5197/__learn_artifacts?lang=${language}`,{waitUntil:'networkidle',timeout:120000});
  if (await page.locator('#finish').count() === 0) {console.log({errors,body:(await page.locator('body').innerText()).slice(0,1000)});await page.reload({waitUntil:'networkidle'});}
  await page.evaluate(t=>document.documentElement.classList.toggle('dark',t==='dark'),theme);
  assert.equal(await page.locator('#first-card [data-artifact-results]').count(),0);
  assert.equal(await page.locator('#artifacts-container').count(),0);
  await page.locator('#finish').click();
  await page.locator('#first-card [data-artifact-results]').waitFor();
  assert.equal(await page.locator('#artifacts-container').count(),0,'Completion must not open the sidebar');
  const downloadPromise=page.waitForEvent('download');
  await page.locator('#first-card button[aria-label]').last().click();
  const download=await downloadPromise;
  assert.equal(download.suggestedFilename(),'artifact.html');
  const html=await fs.readFile(await download.path(),'utf8');
  assert.ok(html.includes('First artifact')&&html.includes('color: red'));
  await page.locator('#first-card').getByText(preview,{exact:true}).click();
  await page.locator('#artifacts-container iframe').waitFor();
  const sidebarDownload = page.locator('#artifacts-container button').filter({has:page.locator('svg path[d^="M4 17v2"]')});
  assert.equal(await page.locator('#first-card button[aria-label] svg').last().evaluate(el=>el.outerHTML),await sidebarDownload.locator('svg').evaluate(el=>el.outerHTML),'Card download SVG must exactly match the sidebar');
  assert.ok((await page.locator('#artifacts-container iframe').getAttribute('srcdoc')).includes('First artifact'),'Older card must open the clicked artifact');
  await page.locator('#second-card').getByText(preview,{exact:true}).click();
  await page.waitForTimeout(60);
  assert.ok((await page.locator('#artifacts-container iframe').getAttribute('srcdoc')).includes('Second artifact'));
  await page.getByRole('button',{name:preview,exact:true}).first().hover();
  await page.getByRole('tooltip').getByText(preview,{exact:true}).waitFor();
  await page.getByRole('button',{name:preview,exact:true}).first().click();
  await page.waitForTimeout(60);
  assert.ok((await page.locator('#artifacts-container iframe').getAttribute('srcdoc')).includes('First artifact'),'Codeblock preview must remain available without a toggle');
  await page.locator('#open-menu').click(); const menu=page.locator('.composer-integrations-menu');await menu.waitFor();
  assert.equal(await menu.getByText('Artifacts',{exact:true}).count(),0);
  await menu.getByText(learn,{exact:true}).click();
  assert.equal(await page.locator('#learning').textContent(),'true');
  await page.locator('#open-menu').click();
  const toolsButton = menu.getByRole('button').filter({has:page.getByText(tools,{exact:true})});
  if(width>768) {
   assert.equal(await toolsButton.isDisabled(),true);
   assert.equal(await toolsButton.getAttribute('aria-pressed'),'false');
   assert.ok((await toolsButton.getAttribute('class')).includes('cursor-not-allowed'));
  }
  if(language==='pt-BR') assert.equal(await menu.getByText('Estude com orientações e exercícios guiados',{exact:true}).count(),1);
  await menu.getByText(learn,{exact:true}).click();
  assert.equal(await page.locator('#learning').textContent(),'false');
  if(width>768) {
   await page.locator('#open-menu').click();
   await toolsButton.click();
   assert.equal(await page.locator('#file-generation').textContent(),'true');
   await menu.getByText(learn,{exact:true}).click();
   assert.equal(await page.locator('#learning').textContent(),'true');
   assert.equal(await page.locator('#file-generation').textContent(),'true','Learn must preserve the prior document-tools preference');
   await page.locator('#open-menu').click();
   assert.equal(await toolsButton.isDisabled(),true);
   assert.equal(await toolsButton.getAttribute('aria-pressed'),'false');
   await menu.getByText(learn,{exact:true}).click();
   await page.locator('#open-menu').click();
   assert.equal(await toolsButton.isDisabled(),false);
   assert.equal(await toolsButton.getAttribute('aria-pressed'),'true','Disabling Learn must restore active tools');
   await menu.getByText(learn,{exact:true}).click();
   await page.locator('#open-menu').click();
   await menu.getByText(language==='pt-BR'?'Busca na web':'Web search',{exact:true}).click();
   await page.locator('#open-menu').click();
   assert.equal(await toolsButton.isDisabled(),false);
   assert.equal(await toolsButton.getAttribute('aria-pressed'),'true','Switching from Learn to Web Search must restore active tools');
   await toolsButton.click();
   assert.equal(await page.locator('#file-generation').textContent(),'false');
   await menu.getByText(learn,{exact:true}).click();
   await page.locator('#open-menu').click();
   await menu.getByText(learn,{exact:true}).click();
   await page.locator('#open-menu').click();
   assert.equal(await toolsButton.getAttribute('aria-pressed'),'false','An originally disabled preference must stay disabled');
   await page.keyboard.press('Escape');
  }
  await page.locator('#restore-conflict').click();
  assert.equal(await page.locator('#file-generation').textContent(),'true','Restored drafts must retain the document-tools preference while blocked');
  assert.equal(await page.locator('#defaults button[role="switch"][aria-checked="true"]').count(),1);
  assert.equal(await page.locator('#default-feature-ids').textContent(),'guided_learning','Conflicting defaults must retain only the last exclusive feature');
  assert.equal(await page.locator('#defaults button[role="switch"]:disabled').count(),5);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  await page.screenshot({path:`logs/learn-artifacts-${width}-${theme}-${language}.png`});
  assert.deepEqual(errors,[]);results.push({width,theme,language,download:true,olderSelection:true,menu:true,errors});await page.close();
 }
 await fs.writeFile('logs/learn-artifacts-visual.json',JSON.stringify(results,null,2));console.log(results);
}finally{await browser?.close();await server?.close();await fs.rm(file,{force:true});await fs.rmdir(dir).catch(()=>{});}
