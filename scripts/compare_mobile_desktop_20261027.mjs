import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
import {chromium} from '../logs/ui-image-26/node_modules/playwright/index.mjs';
const browser=await chromium.launch();
try{
 const page=await browser.newPage({viewport:{width:1440,height:1000}});
 await page.route('**/api/**',r=>r.request().method()==='GET'||r.request().url().includes('/auths/')?r.continue():r.fulfill({json:{}}));
 await page.goto('http://localhost:8080',{waitUntil:'networkidle',timeout:90000});await page.evaluate(()=>document.fonts.ready);
 const box=async()=>{await page.waitForTimeout(300);return page.locator('.modal[aria-hidden="false"]').last().locator(':scope > div').boundingBox();};
 const before={};await page.locator('button[aria-label="Models"]').click();before.models=await box();
 await page.locator('.modal[aria-hidden="false"]').last().getByText('Baixar modelos',{exact:true}).click();before.download=await box();
 await page.keyboard.press('Escape');await page.waitForTimeout(200);await page.keyboard.press('Escape');await page.waitForTimeout(200);
 await page.locator('#sidebar').getByRole('button').filter({has:page.locator('img[aria-label]')}).last().click();
 await page.getByRole('menuitem').filter({hasText:'Configurações'}).click();before.settings=await box();await page.keyboard.press('Escape');await page.waitForTimeout(200);
 await page.locator('#sidebar-search-button').click();before.search=await box();
 const after=JSON.parse(await fs.readFile('logs/mobile-20261027/results.json','utf8')).find(r=>r.width===1440&&!r.dark);
 for(const key of Object.keys(before))for(const prop of ['x','y','width','height'])assert(Math.abs(before[key][prop]-after[key][prop])<=0.5,key+' desktop '+prop+' changed: '+JSON.stringify({before:before[key],after:after[key]}));
 await fs.writeFile('logs/mobile-20261027/desktop-comparison.json',JSON.stringify({before,after:Object.fromEntries(Object.keys(before).map(k=>[k,after[k]]))},null,2));console.log('PASS: all four desktop dialog rectangles match the previous production build');
}finally{await browser.close();}
