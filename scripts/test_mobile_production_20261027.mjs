import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
import {chromium} from '../logs/ui-image-26/node_modules/playwright/index.mjs';
const browser=await chromium.launch();const results=[];const output=process.env.PRODUCTION_MOBILE_DIR??'logs/mobile-20261027';
try{
 for(const width of [390,767,1440]){
  const mobile=width<768,page=await browser.newPage({viewport:{width,height:1000},hasTouch:mobile}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));page.setDefaultTimeout(20000);
  await page.route('**/api/**',r=>r.request().method()==='GET'||r.request().url().includes('/auths/')?r.continue():r.fulfill({json:{}}));
  await page.goto('http://localhost:8080',{waitUntil:'networkidle',timeout:90000});await page.evaluate(()=>document.fonts.ready);const url=page.url();
  const dialog=()=>page.locator('.modal[aria-hidden="false"]').last();
  const check=async()=>{await page.waitForTimeout(200);const b=await dialog().locator(':scope > div').boundingBox();if(mobile)assert(Math.abs(b.x)<1&&Math.abs(b.y)<1&&Math.abs(b.width-width)<1&&Math.abs(b.height-1000)<1);else assert(b.width<width&&b.height<1000);return b;};
  const back=async()=>{if(process.env.DIALOG_BACK_BUTTON)await dialog().locator('.mobile-modal-back').last().click();else await page.evaluate(()=>history.back());await page.waitForTimeout(300);assert.equal(page.url(),url);};
  const press=async locator=>mobile?locator.tap():locator.click();
  await press(page.locator('button[aria-label="Models"]'));await page.locator('.unified-models-shell').waitFor({state:'visible'});const models=await check();
  await press(dialog().getByText('Baixar modelos',{exact:true}));await page.locator('.download-models-shell').waitFor({state:'visible'});const download=await check();
  if(mobile){await back();assert(await page.locator('.unified-models-shell').isVisible());
   if(process.env.DIALOG_BACK_BUTTON){await page.locator('.unified-model-name').first().click();await page.locator('.model-editor-features').waitFor({state:'attached'});assert(!(await page.locator('.model-editor-features').isVisible()));await back();assert(await page.locator('.unified-models-shell').isVisible());}
   await back();}else{await page.keyboard.press('Escape');await page.waitForTimeout(200);await page.keyboard.press('Escape');}
  await page.waitForTimeout(250);
  if(mobile){await page.locator('.chat-navbar-sidebar button').tap();await page.waitForTimeout(350);}
  await press(page.locator('#sidebar').getByRole('button').filter({has:page.locator('img[aria-label]')}).last());
  await press(page.getByRole('menuitem').filter({hasText:'Configurações'}));await page.locator('.settings-shell').waitFor({state:'visible'});const settings=await check();
  await press(page.locator('#settings-tabs-container > button').first());await page.locator('.settings-content').waitFor({state:'visible'});
  if(mobile){await back();assert(await page.locator('#settings-tabs-container').isVisible());await back();}else await page.locator('.settings-close').click();
  await page.waitForTimeout(250);if(mobile){await page.locator('.chat-navbar-sidebar button').tap();await page.waitForTimeout(350);}
  await press(page.locator('#sidebar-search-button'));await page.locator('.search-modal-shell').waitFor({state:'visible'});const search=await check();
  await page.screenshot({path:`${output}/production-search-${width}.png`});if(mobile)await back();else await page.locator('.search-modal-close').click();
  assert.deepEqual(errors,[]);assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);results.push({width,models,download,settings,search,errors});await page.close();
 }
 await fs.writeFile(output+'/production.json',JSON.stringify(results,null,2));console.log('PASS 3 production viewport configurations using actual UI controls');
}finally{await browser.close();}
