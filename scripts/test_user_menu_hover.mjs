import assert from 'node:assert/strict';
import {chromium} from '../logs/ui-image-26/node_modules/playwright/index.mjs';
import {installMobileOfflineApi} from './fixtures/mobile-offline-api.mjs';
const browser=await chromium.launch();
try{
 for(const dark of [false,true]){
  const page=await browser.newPage({viewport:{width:1440,height:1000}});
  await installMobileOfflineApi(page);
  await page.goto('http://127.0.0.1:8080',{waitUntil:'networkidle'});
  await page.evaluate(dark=>document.documentElement.classList.toggle('dark',dark),dark);
  const image=page.locator('#sidebar img[aria-label]').last();
  const trigger=image.locator('xpath=ancestor::button[1]');
  const surface=trigger.locator(':scope > div').first();
  await trigger.hover();await page.waitForTimeout(250);
  const hover=await surface.evaluate(node=>getComputedStyle(node).backgroundColor);
  await trigger.click();await page.mouse.move(900,400);await page.waitForTimeout(250);
  assert.equal(await trigger.getAttribute('data-state'),'open');
  assert.equal(await surface.evaluate(node=>getComputedStyle(node).backgroundColor),hover);
  await page.keyboard.press('Escape');await page.mouse.move(900,400);await page.waitForTimeout(250);
  assert.equal(await trigger.getAttribute('data-state'),'closed');
  assert.equal(await surface.evaluate(node=>getComputedStyle(node).backgroundColor),'rgba(0, 0, 0, 0)');
  await page.screenshot({path:`logs/user-menu-hover-${dark?'dark':'light'}.png`});
  console.log('PASS',dark?'dark':'light');await page.close();
 }
}finally{await browser.close()}
