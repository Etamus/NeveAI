import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {chromium} from '../logs/ui-image-26/node_modules/playwright/index.mjs';
const browser=await chromium.launch(), results=[];
try{
 for(const width of [1440,390,320]){
  const context=await browser.newContext({viewport:{width,height:width===1440?1000:844},colorScheme:'dark'});
  const page=await context.newPage(), errors=[];page.on('pageerror',error=>errors.push(error.message));
  await page.addInitScript(()=>{localStorage.setItem('theme','dark');localStorage.setItem('neveai.language','pt-BR');});
  await page.route('**/api/updater/state',route=>route.fulfill({json:{status:'idle'}}));
  await page.route('**/api/version/updates',route=>route.fulfill({json:{current_tag:'v3.2.11',latest_tag:'v3.2.11',neve_update_available:false,llama_cpp:{update_available:false}}}));
  await page.route('**/api/v1/users/user/settings/update',route=>route.fulfill({json:{}}));
  await page.goto('http://localhost:8080',{waitUntil:'networkidle'});
  const user=page.getByRole('button',{name:/Usuário|User menu/i});
  if(!await user.isVisible())await page.locator('.chat-navbar-sidebar button').click();
  await user.click();await page.getByRole('menuitem').filter({hasText:'Configurações'}).click();
  if(width<768)await page.getByRole('tab',{name:'Geral',exact:true}).click();
  for(const mode of ['system','light','dark']){
   await page.locator(`[data-theme-option="${mode}"]`).click();await page.waitForTimeout(100);
   assert.equal(await page.evaluate(()=>localStorage.getItem('theme')),mode);
   assert.equal(await page.locator('[data-theme-option][aria-pressed="true"]').count(),1);
   assert.equal(await page.locator(`[data-theme-option="${mode}"]`).getAttribute('aria-pressed'),'true');
   assert.equal(await page.evaluate(()=>document.documentElement.classList.contains('dark')),mode!=='light');
   const geometry=await page.locator('[data-theme-option]').evaluateAll(nodes=>nodes.map(node=>{const r=node.getBoundingClientRect();return{x:r.x,y:r.y,width:r.width,height:r.height,right:r.right};}));
   assert(geometry.every(value=>value.x>=0&&value.right<=width));
   const group=await page.locator('[data-theme-option]').first().locator('..').boundingBox();
   assert(geometry.every(value=>value.x>=group.x+4&&value.right<=group.x+group.width-4));
   assert.equal(new Set(geometry.map(value=>value.y)).size,1);
   const corners=await page.locator('[data-theme-option]').evaluateAll(nodes=>nodes.map(node=>{
    const button=getComputedStyle(node),image=getComputedStyle(node.querySelector('.theme-preview')),border=getComputedStyle(node,'::after');
    return {buttonRadius:button.borderRadius,imageRadius:image.borderRadius,borderRadius:border.borderRadius,imageBackground:image.backgroundColor,borderColor:border.borderColor,panes:[...node.querySelectorAll('.preview-pane')].map(pane=>getComputedStyle(pane).backgroundColor)};
   }));
   for(const corner of corners){assert.equal(corner.buttonRadius,corner.imageRadius);assert.equal(corner.buttonRadius,corner.borderRadius);assert(corner.panes.every(color=>color==='rgba(0, 0, 0, 0)'));}
   assert.equal(corners[['system','light','dark'].indexOf(mode)].borderColor,'rgb(59, 130, 246)');
   const other=page.locator(`[data-theme-option="${mode==='light'?'dark':'light'}"]`);
   await other.hover();await page.waitForTimeout(200);
   assert.notEqual(await other.evaluate(node=>getComputedStyle(node,'::after').borderColor),'rgba(0, 0, 0, 0)');
   await page.mouse.move(0,0);await page.waitForTimeout(200);
   const label=page.locator('#tab-general').getByText('Tema',{exact:true});
   const labelBox=await label.boundingBox();
   const lineHeight=await label.evaluate(node=>parseFloat(getComputedStyle(node).lineHeight));
   assert(labelBox.height<=lineHeight+0.5);
   assert(labelBox.x+labelBox.width<=group.x);
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
   await page.screenshot({path:`logs/theme-previews-${width}-${mode}.png`});
   results.push({width,mode,geometry,errors});
  }
  assert.deepEqual(errors,[]);await context.close();
 }
 await fs.writeFile('logs/theme-previews-results.json',JSON.stringify(results,null,2));
 console.log('PASS theme preview selection, persistence, colors, layout at 1440/390/320px');
}finally{await browser.close();}
