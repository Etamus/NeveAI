import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {chromium} from '../logs/ui-image-26/node_modules/playwright/index.mjs';
const browser=await chromium.launch(),results=[];
try{
 for(const width of [1440,390])for(const theme of ['dark','light']){
  const context=await browser.newContext({viewport:{width,height:1000}}),page=await context.newPage(),errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  await page.addInitScript(theme=>{localStorage.setItem('neveai.language','pt-BR');localStorage.setItem('theme',theme);},theme);
  await page.route('**/api/updater/state',route=>route.fulfill({json:{status:'idle'}}));
  await page.route('**/api/version/updates',route=>route.fulfill({json:{current_tag:'v3.2.11',latest_tag:'v3.2.11',neve_update_available:false,llama_cpp:{update_available:false}}}));
  await page.route('**/api/v1/users/user/settings/update',route=>route.fulfill({json:{}}));
  await page.goto('http://localhost:8080',{waitUntil:'networkidle'});await page.evaluate(()=>document.fonts.ready);
  const icon=await page.getByRole('button',{name:'Models',exact:true}).evaluate(button=>{
   const b=button.getBoundingClientRect(),svg=button.querySelector('svg'),s=svg.getBoundingClientRect(),wrapper=svg.parentElement.getBoundingClientRect();
   const paint=svg=>{const box=svg.getBBox(),rect=svg.getBoundingClientRect(),view=svg.viewBox.baseVal,stroke=parseFloat(getComputedStyle(svg).strokeWidth);return {width:(box.width+stroke)*rect.width/view.width,height:(box.height+stroke)*rect.height/view.height};};
   return {buttonWidth:b.width,buttonHeight:b.height,width:s.width,height:s.height,wrapper:wrapper.width,dx:s.x+s.width/2-b.x-b.width/2,dy:s.y+s.height/2-b.y-b.height/2,transform:getComputedStyle(svg).transform,paint:paint(svg),neighbors:['#temporary-chat-button svg','#chat-parameters-button svg'].map(selector=>document.querySelector(selector)).filter(Boolean).map(paint)};
  });
  assert(Math.abs(icon.width/icon.wrapper-1.1)<0.01);assert(Math.abs(icon.dx)<0.1&&Math.abs(icon.dy)<0.1);
  assert.equal(await page.locator('button[aria-label="Models"] svg path').count(),2);
  assert.equal(await page.locator('button[aria-label="Models"] svg path').last().getAttribute('d'),'M12 3V21M21 12H3');
  await page.screenshot({path:`logs/navbar-models-size-${width}-${theme}.png`});
  const user=page.getByRole('button',{name:/Usuário|User menu/i});if(!await user.isVisible())await page.locator('.chat-navbar-sidebar button').click();
  await user.click();await page.getByRole('menuitem').filter({hasText:'Configurações'}).click();
  const positions={};
  for(const [tab,text] of [['notifications','Ativar notificações na interface'],['about','Versão'],['data-controls','Conversas'],['personalization','Memória']]){
   const button=page.locator(`[role="tab"][aria-controls="tab-${tab}"]`);
   if(!await button.isVisible())await page.getByRole('button',{name:/Voltar|Back/}).last().click();
   await button.click();
   const heading=page.locator('.settings-shell').getByText(text,{exact:true});await heading.waitFor();
   const b=await heading.boundingBox();positions[tab]={x:b.x,y:b.y};
   await page.screenshot({path:`logs/settings-heading-${tab}-${width}-${theme}.png`});
  }
  for(const reference of ['about','data-controls','personalization']){
   assert(Math.abs(positions.notifications.x-positions[reference].x)<0.2,JSON.stringify({width,positions}));
   assert(Math.abs(positions.notifications.y-positions[reference].y)<0.5,JSON.stringify({width,positions}));
  }
  assert.deepEqual(errors,[]);results.push({width,theme,icon,positions,errors});await context.close();
 }
 await fs.writeFile('logs/settings-header-alignment-results.json',JSON.stringify(results,null,2));console.log(JSON.stringify(results));
}finally{await browser.close();}
