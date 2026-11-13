import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {chromium} from '../logs/ui-image-26/node_modules/playwright/index.mjs';

const browser=await chromium.launch();
const results=[];
try {
 for(const mobile of [false,true])for(const theme of ['light','dark']){
  const context=await browser.newContext({viewport:mobile?{width:390,height:844}:{width:1440,height:1000},isMobile:mobile,hasTouch:mobile});
  const page=await context.newPage();const errors=[];page.on('pageerror',error=>errors.push(error.message));
  await page.addInitScript(theme=>{localStorage.setItem('theme',theme);localStorage.setItem('neveai.language','pt-BR');},theme);
  let job={status:'completed',versions:{neve:'v1.0.0',llama:'b1'}};let selected=[];let preferences=null;let persisted=[];
  let availability={current_tag:'v3.1.83',latest_tag:'v999.0.0',neve_update_available:true,llama_cpp:{current_tag:'b1',latest_tag:'b999999',update_available:true}};
  await page.route('**/api/version/updates',route=>route.fulfill({json:availability}));
  await page.route('**/api/updater/**',async route=>{
   const action=new URL(route.request().url()).pathname.split('/').pop();
   if(action==='download'){
    selected=route.request().postDataJSON().targets;job={status:'downloading',id:'fixture',targets:selected,progress:25,phase:'Baixando pacote',versions:{neve:'v999.0.0',llama:'b999999'}};
   }else if(action==='restart')job={...job,status:'restarting'};
   await route.fulfill({json:job});
  });
  await page.route(/\/api\/v1\/users\/user\/settings(?:\/update)?$/,async route=>{
   if(route.request().method()==='POST'){
    const body=route.request().postDataJSON();preferences={...preferences,...body.ui};persisted.push(body);await route.fulfill({json:body});
   }else{const response=await route.fetch();const data=await response.json();preferences??={...data.ui,showModelRuntimeToasts:true,showModelDownloadToasts:true,showErrorToasts:true,showUpdateToast:true,receiveLlamaUpdates:true,enableInterfaceNotifications:true};await route.fulfill({response,json:{...data,ui:preferences}});}
  });
  await page.goto('http://localhost:8080',{waitUntil:'networkidle'});
  await page.evaluate(theme=>document.documentElement.classList.toggle('dark',theme==='dark'),theme);
  await page.locator('[data-neve-toast-kind="update"]').getByRole('button',{name:/Detalhes|Details/}).click();
  await page.locator('#tab-updates').waitFor();
  await page.keyboard.press('Escape');
  const menu=async()=>{
   const user=page.getByRole('button',{name:/Usuário|User menu/i});
   if(!await user.isVisible()){await page.locator('.chat-navbar-sidebar button').click();}
   await user.click();
  };
  await menu();
  const menuItems=await page.getByRole('menuitem').allTextContents();
  const position=text=>menuItems.findIndex(value=>value.includes(text));
  assert(position('Personalização')>position('Perfil'));
  assert.equal(position('Sobre'),-1);
  await page.getByRole('menuitem').filter({hasText:'Configurações'}).click();
  const tab=async name=>{
   if(mobile && await page.locator('#tab-updates,#tab-notifications,#tab-about').isVisible().catch(()=>false)){
    const back=page.getByRole('button',{name:/Voltar|Back/}).last();if(await back.isVisible())await back.click();
   }
   await page.getByRole('tab',{name,exact:true}).click();
  };
  await tab(/Notificações|Notifications/);
  const switches=page.locator('#tab-notifications [role="switch"]');assert.equal(await switches.count(),4);
  for(let i=0;i<4;i++)assert.equal(await switches.nth(i).getAttribute('aria-checked'),'true');
  await switches.nth(1).click();
  for(let i=0;i<100 && !persisted.length;i++)await page.waitForTimeout(100);
  assert.equal(await switches.nth(1).getAttribute('aria-checked'),'false');
  assert.equal(await switches.nth(2).getAttribute('aria-checked'),'true');
  await switches.nth(0).click();
  for(let i=1;i<4;i++){assert(await switches.nth(i).isDisabled());assert.equal(await switches.nth(i).getAttribute('aria-checked'),'false');}
  await page.waitForTimeout(300);
  const disabledVisual=await switches.evaluateAll(nodes=>nodes.map(node=>({checked:node.getAttribute('aria-checked'),color:getComputedStyle(node).backgroundColor})));
  assert(disabledVisual.every(value=>value.checked==='false'&&!['rgb(37, 99, 235)','rgb(59, 130, 246)'].includes(value.color)),JSON.stringify(disabledVisual));
  await page.screenshot({path:`logs/settings-master-off-${mobile?'mobile':'desktop'}-${theme}.png`});
  await tab('Atualizações');
  const updateNotifications=page.getByRole('switch',{name:'Notificar sobre novas atualizações',exact:true});
  assert(await updateNotifications.isDisabled());assert.equal(await updateNotifications.getAttribute('aria-checked'),'false');
  await page.reload({waitUntil:'networkidle'});await menu();await page.getByRole('menuitem').filter({hasText:'Configurações'}).click();
  await tab(/Notificações|Notifications/);
  assert.equal(await switches.nth(0).getAttribute('aria-checked'),'false');
  for(let i=1;i<4;i++)assert(await switches.nth(i).isDisabled());
  await switches.nth(0).click();
  assert.equal(await switches.nth(1).getAttribute('aria-checked'),'false');
  assert.equal(await switches.nth(2).getAttribute('aria-checked'),'true');
  assert.equal(await switches.nth(3).getAttribute('aria-checked'),'true');
  await page.screenshot({path:`logs/settings-notifications-${mobile?'mobile':'desktop'}-${theme}.png`});
  await tab('Atualizações');
  await page.locator('#tab-updates h3').getByText('Atualização disponível (v999.0.0)',{exact:true}).waitFor();
  assert.equal(await page.locator('#tab-updates').getByText('v1.0.0',{exact:true}).count(),0);
  assert.equal(await page.locator('#tab-updates input[type="checkbox"]:not([hidden])').count(),0);
  assert.equal(await page.locator('#tab-updates header svg').count(),0);
  assert.equal(await page.locator('[data-update-component]').count(),1);
  assert.equal(await page.locator('[data-update-component="neve"]').count(),0);
  assert.equal(await page.locator('#tab-updates h3').innerText(),'Atualização disponível (v999.0.0)');
  const cardVisual=await page.locator('#tab-updates > section').evaluate(node=>getComputedStyle(node).borderTopWidth);
  assert.equal(cardVisual,'0px');
  const labelVisual=await page.locator('[data-update-component="llama"] > span').first().evaluate(node=>({fontSize:getComputedStyle(node).fontSize,fontWeight:getComputedStyle(node).fontWeight}));
  assert.deepEqual(labelVisual,{fontSize:'13px',fontWeight:'400'});
  const rows=await page.locator('[data-update-component]').evaluateAll(nodes=>nodes.map(node=>{
   const style=getComputedStyle(node),box=node.getBoundingClientRect();
   return {top:box.top,bottom:box.bottom,left:box.left,right:box.right,borderTop:parseFloat(style.borderTopWidth),borderBottom:parseFloat(style.borderBottomWidth),borderLeft:parseFloat(style.borderLeftWidth),borderRight:parseFloat(style.borderRightWidth)};
  }));
  const headerBottom=await page.locator('#tab-updates header').evaluate(node=>({bottom:node.getBoundingClientRect().bottom,border:parseFloat(getComputedStyle(node).borderBottomWidth)}));
  assert(Math.abs(rows[0].top-headerBottom.bottom)<0.1);assert.equal(headerBottom.border,1);
  assert(rows.every(row=>row.borderLeft===0&&row.borderRight===0));
  assert((await page.locator('#llama-updates-label').boundingBox()).y>(await page.locator('#update-notifications-label').boundingBox()).y);
  const header=await page.locator('#tab-updates header').boundingBox();
  const button=await page.locator('#tab-updates .update-action').boundingBox();
  const padding=await page.locator('#tab-updates header').evaluate(node=>parseFloat(getComputedStyle(node).paddingRight));
  assert(Math.abs(button.x+button.width-header.x-header.width+padding)<1);
  assert.equal(button.height,30);
  await page.screenshot({path:`logs/settings-updates-available-${mobile?'mobile':'desktop'}-${theme}.png`});
  const llama=page.getByRole('switch',{name:'Receber atualizações do llama.cpp',exact:true});
  await llama.waitFor();
  if(theme==='light'){
   await llama.click();await page.locator('[data-update-component="llama"]').waitFor({state:'detached'});
   for(let i=0;i<100 && !persisted.some(body=>body.ui.receiveLlamaUpdates===false);i++)await page.waitForTimeout(50);
   assert(persisted.some(body=>body.ui.receiveLlamaUpdates===false));
   await page.reload({waitUntil:'networkidle'});await menu();await page.getByRole('menuitem').filter({hasText:'Configurações'}).click();await tab('Atualizações');
   assert.equal(await llama.getAttribute('aria-checked'),'false');
   assert.equal(await page.locator('[data-update-component="llama"]').count(),0);
  }
  await page.locator('#tab-updates').getByRole('button',{name:'Atualizar agora',exact:true}).click();
  assert.deepEqual(selected,theme==='light'?['neve']:['neve','llama']);
  assert(await llama.isDisabled());
  await page.getByRole('progressbar').waitFor();
  await page.locator('#tab-updates h3').getByText('Atualização em andamento (v999.0.0)',{exact:true}).waitFor();
  assert.equal(await page.locator('[data-update-phase]').innerText(),'Baixando pacote');
  const phaseBox=await page.locator('[data-update-phase]').boundingBox();
  const trackBox=await page.getByRole('progressbar').locator('.h-1').boundingBox();
  assert(phaseBox.y>trackBox.y+trackBox.height);
  assert.equal(await page.locator('[data-update-component]').count(),0);
  assert.equal(await page.locator('#tab-updates header').count(),1);
  assert.notEqual(await page.locator('#tab-updates > section').evaluate(node=>getComputedStyle(node).backgroundColor),'rgba(0, 0, 0, 0)');
  assert.equal(await page.locator('#tab-updates').getByRole('button',{name:'Atualizar agora'}).count(),0);
  await page.screenshot({path:`logs/settings-updates-downloading-${mobile?'mobile':'desktop'}-${theme}.png`});
  const originalTargets=job.targets;
  job={...job,targets:['llama']};
  await page.locator('#tab-updates h3').getByText('Atualização em andamento (b999999)',{exact:true}).waitFor({timeout:4000});
  job={...job,targets:originalTargets};
  await page.locator('#tab-updates h3').getByText('Atualização em andamento (v999.0.0)',{exact:true}).waitFor({timeout:4000});
  job={...job,status:'ready',progress:100};
  await page.locator('#tab-updates').getByRole('button',{name:'Reiniciar',exact:true}).waitFor({timeout:4000});
  assert.equal(await page.locator('#tab-updates h3').innerText(),'Reinicie para aplicar as alterações');
  await page.screenshot({path:`logs/settings-updates-ready-${mobile?'mobile':'desktop'}-${theme}.png`});
  await page.reload({waitUntil:'networkidle'});await menu();await page.getByRole('menuitem').filter({hasText:'Configurações'}).click();await tab('Atualizações');
  await page.locator('#tab-updates').getByRole('button',{name:'Reiniciar',exact:true}).waitFor();
  assert.equal(await page.locator('#tab-updates h3').innerText(),'Reinicie para aplicar as alterações');
  await page.locator('#tab-updates').getByRole('button',{name:'Reiniciar',exact:true}).click();
  await page.getByText('Reiniciando...', {exact:true}).waitFor();
  await tab('Sobre');assert.equal(await page.locator('#tab-about button').filter({hasText:/Atualizar/}).count(),0);
  await page.keyboard.press('Escape');await menu();
  await page.getByRole('menuitem').filter({hasText:'Personalização'}).click();await page.locator('#tab-personalization').waitFor();
  await page.keyboard.press('Escape');await menu();
  assert.equal(await page.getByRole('menuitem').filter({hasText:'Sobre'}).count(),0);
  await page.getByRole('menuitem').filter({hasText:'Configurações'}).click();await tab('Sobre');await page.locator('#tab-about').waitFor();
  job={status:'completed'};availability={current_tag:'v3.1.83',latest_tag:'v3.1.83',neve_update_available:false,llama_cpp:{current_tag:'b1',latest_tag:'b1',update_available:false}};
  await page.reload({waitUntil:'networkidle'});await menu();await page.getByRole('menuitem').filter({hasText:'Configurações'}).click();await tab('Atualizações');
  await page.locator('#tab-updates h3').getByText('Você está na versão mais recente',{exact:true}).waitFor();
  assert.equal(await page.locator('#tab-updates h3 svg').count(),1);
  assert.notEqual(await page.locator('#tab-updates > section').evaluate(node=>getComputedStyle(node).backgroundColor),'rgba(0, 0, 0, 0)');
  assert.equal(await page.locator('[data-update-component]').count(),0);
  assert.equal(await page.locator('#tab-updates .update-action').count(),0);
  await page.screenshot({path:`logs/settings-updates-current-${mobile?'mobile':'desktop'}-${theme}.png`});
  assert(persisted.some(body=>body.ui.showModelRuntimeToasts===false),JSON.stringify(persisted));
  assert.deepEqual(errors,[]);
  results.push({mobile,theme,selected,errors,notifications:4,masterRestores:true,restart:true});await context.close();
 }
 await fs.writeFile('logs/settings-updates-visual.json',JSON.stringify(results,null,2));console.log(JSON.stringify(results));
}finally{await browser.close();}
