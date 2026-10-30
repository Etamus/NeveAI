import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import { chromium } from '../logs/ui-image-26/node_modules/playwright/index.mjs';

const browser = await chromium.launch();
const results = [];
try {
  for(const [name,viewport] of [['desktop',{width:1440,height:1000}],['mobile',{width:390,height:844}]]){
    const page = await browser.newPage({viewport});
    const errors = [];
    page.on('pageerror',error=>errors.push(error.message));
    await page.goto('http://localhost:8080',{waitUntil:'networkidle'});
    await page.locator('#input-menu-button:visible').click();
    await page.getByText('Criar vídeo',{exact:true}).click();
    const controls = ['video-resolution-dropdown-container','video-duration-dropdown-container','video-aspect-ratio-dropdown-container'];
    for(const id of controls) assert.equal(await page.locator('#'+id).count(),1);
    assert.equal(await page.locator('[data-composer-root] input[type=file]').first().getAttribute('accept'),'image/*');
    for(const [id,value] of [[controls[0],'672p'],[controls[1],'8s'],[controls[2],'9:16']]){
      await page.locator('#'+id+' > button').click();
      await page.getByRole('button',{name:value,exact:true}).click();
      assert((await page.locator('#'+id+' > button').innerText()).includes(value));
    }
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
    await page.screenshot({path:`logs/video-controls-${name}.png`});
    assert.deepEqual(errors,[]);
    results.push({name,controls:3,imageOnly:true,errors});
    await page.close();
  }
  console.log(JSON.stringify(results));
} finally {await browser.close();}
