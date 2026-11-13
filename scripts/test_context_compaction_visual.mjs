import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {chromium} from '../logs/ui-image-26/node_modules/playwright/index.mjs';
import {installMobileOfflineApi} from './fixtures/mobile-offline-api.mjs';

const browser=await chromium.launch(),results=[];
try{
 for(const width of [1440,390])for(const theme of ['dark','light']){
  const page=await browser.newPage({viewport:{width,height:900}}),errors=[];
  await installMobileOfflineApi(page);
  await page.addInitScript(theme=>{localStorage.setItem('neveai.language','pt-BR');localStorage.setItem('theme',theme);},theme);
  page.on('pageerror',e=>errors.push(e.message));
  await page.goto('http://127.0.0.1:8080',{waitUntil:'networkidle',timeout:90000});
  async function open(){await page.locator('#model-selector-0-button').click();await page.getByRole('button',{name:'Predefinições',exact:true}).click();}
  await open();
  const toggle=page.locator('#load-setting-compaction');
  await toggle.scrollIntoViewIfNeeded();assert.equal(await toggle.getAttribute('aria-checked'),'false');
  assert.equal(await page.locator('#load-setting-compaction-label').innerText(),'Compactação de contexto');
  const before=await page.evaluate(()=>Object.fromEntries(Object.entries(localStorage).filter(([k])=>k.startsWith('llamacpp_'))));
  await toggle.click();assert.equal(await toggle.getAttribute('aria-checked'),'true');
  let values=await page.evaluate(()=>Object.fromEntries(Object.entries(localStorage).filter(([k])=>k.startsWith('llamacpp_'))));
  assert.deepEqual(values,{...before,llamacpp_context_compaction:'true'});
  await page.keyboard.press('Escape');await open();await toggle.scrollIntoViewIfNeeded();
  assert.equal(await toggle.getAttribute('aria-checked'),'true');
  const shift=page.locator('#load-setting-contextShift');await shift.click();
  assert.equal(await toggle.getAttribute('aria-checked'),'true');
  await shift.click();await toggle.click();assert.equal(await toggle.getAttribute('aria-checked'),'false');
  values=await page.evaluate(()=>localStorage.getItem('llamacpp_context_compaction'));assert.equal(values,null);
  await page.waitForTimeout(250);
  await toggle.scrollIntoViewIfNeeded();
  const rect=await toggle.boundingBox();assert(rect.x>=0&&rect.x+rect.width<=width&&rect.y+rect.height<=900);
  assert.deepEqual(errors,[]);
  await page.screenshot({path:`logs/context-compaction-settings-${width}-${theme}.png`});
  results.push({width,theme,default_off:true,persisted_on_reopen:true,shift_independent:true,unrelated_preferences_preserved:true});
  console.log('PASS',width,theme);await page.close();
 }
 await fs.writeFile('logs/context-compaction-settings.json',JSON.stringify(results,null,2));
}finally{await browser.close()}
