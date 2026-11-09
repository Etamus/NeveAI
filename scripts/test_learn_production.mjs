import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {chromium} from '../logs/ui-image-26/node_modules/playwright/index.mjs';
const browser=await chromium.launch(); const results=[];
try {
 for(const width of [1440,390]) {
  const page=await browser.newPage({viewport:{width,height:1000}}),errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  await page.goto('http://127.0.0.1:8080/',{waitUntil:'networkidle',timeout:90000});
  await page.locator('#message-input-container').waitFor();
  await page.locator('#input-menu-button').click();
  const menu=page.locator('.composer-integrations-menu');await menu.waitFor();
  assert.equal(await menu.getByText(/^(Aprender|Learn)$/).count(),1);
  assert.equal(await menu.getByText(/^(Artefatos|Artifacts)$/).count(),0);
  const toolsButton=menu.getByRole('button').filter({has:page.getByText(/^(Ferramentas|Tools)$/,{exact:true})});
  if(width>768 && await toolsButton.getAttribute('aria-pressed')!=='true') await toolsButton.click();
  await menu.getByText(/^(Aprender|Learn)$/).click();
  await page.getByRole('button',{name:/Desativar aprendizado guiado|Disable guided learning/}).waitFor();
  if(width>768) {
   await page.locator('#input-menu-button').click();await menu.waitFor();
   assert.equal(await toolsButton.isDisabled(),true);
   assert.equal(await toolsButton.getAttribute('aria-pressed'),'false');
   await menu.getByText(/^(Aprender|Learn)$/).click();
   await page.locator('#input-menu-button').click();await menu.waitFor();
   assert.equal(await toolsButton.isDisabled(),false);
   assert.equal(await toolsButton.getAttribute('aria-pressed'),'true','Real Chat must retain the prior tools state');
   await page.keyboard.press('Escape');
  }
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  await page.screenshot({path:`logs/learn-production-${width}.png`});
  assert.deepEqual(errors,[]); results.push({width,errors,chip:true});await page.close();
 }
 await fs.writeFile('logs/learn-production.json',JSON.stringify(results,null,2));console.log(results);
} finally {await browser.close();}
