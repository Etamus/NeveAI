import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {chromium} from '../logs/ui-image-26/node_modules/playwright/index.mjs';
const browser=await chromium.launch();
try{
 const page=await browser.newPage({viewport:{width:1440,height:1000}});
 const errors=[],mutations=[];page.on('pageerror',error=>errors.push(error.message));
 await page.addInitScript(()=>{localStorage.setItem('neveai.imageQuality','neve_image_2');localStorage.setItem('neveai.imageStyle','manga');});
 page.on('request',request=>{if(/llamacpp.*(?:load|unload|standby)/.test(request.url())&&request.method()==='POST')mutations.push(request.url())});
 await page.goto('http://localhost:8080',{waitUntil:'networkidle'});
 await page.locator('#input-menu-button').click();
 await page.getByRole('button').filter({hasText:'Criar imagem'}).click();
 const selector=page.locator('.image-quality-control > button');await selector.click();
 const menu=page.locator('[data-composer-dropdown-anchor="image-quality-dropdown-container"]');
 await menu.waitFor();const text=await menu.innerText();
 assert(!text.includes('Neve Image 1.5'));
 for(const name of ['Neve Image 2','Neve Image 2.6','Neve Image 3'])assert(text.includes(name));
 await page.screenshot({path:'logs/image-retirement-selector.png'});
 await page.keyboard.press('Escape');
 const preferences=await page.evaluate(()=>({quality:localStorage.getItem('neveai.imageQuality'),style:localStorage.getItem('neveai.imageStyle')}));
 assert.deepEqual(preferences,{quality:'qwen_image_2s',style:null});assert.deepEqual(errors,[]);assert.deepEqual(mutations,[]);
 await fs.writeFile('logs/image-retirement-visual.json',JSON.stringify({preferences,errors,mutations,menu:text},null,2));
 console.log('Image model selection and retired preference migration passed without model lifecycle mutations');
}finally{await browser.close();}
