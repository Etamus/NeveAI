import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {chromium} from '../logs/ui-image-26/node_modules/playwright/index.mjs';
const browser=await chromium.launch(),results=[];
try{
 for(const [locale,saved,width] of [['pt-PT',null,1440],['pt-BR',null,390],['en-GB',null,1440],['fr-FR',null,390],['ja-JP','auto',1440],['en-US','pt-BR',1440],['pt-PT','en-US',1440]]){
  console.log('Language scenario',locale,saved,width);
  const context=await browser.newContext({locale,viewport:{width,height:900}}),page=await context.newPage(),errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  await page.addInitScript(saved=>{
   if(!sessionStorage.getItem('language-test-initialized')){
    localStorage.removeItem('neveai.language');if(saved)localStorage.setItem('neveai.language',saved);
    sessionStorage.setItem('language-test-initialized','true');
   }
  },saved);
  await page.route('**/api/updater/state',route=>route.fulfill({json:{status:'idle'}}));
  await page.route('**/api/version/updates',route=>route.fulfill({json:{current_tag:'v3.2.11',latest_tag:'v3.2.11',neve_update_available:false,llama_cpp:{update_available:false}}}));
  await page.route('**/api/v1/users/user/settings/update',route=>route.fulfill({json:{}}));
  const automatic=locale.toLowerCase().startsWith('pt')?'pt-BR':'en-US';
  const expected=saved&&saved!=='auto'?saved:automatic;
  await page.goto('http://localhost:8080',{waitUntil:'networkidle'});
  assert.equal(await page.evaluate(()=>document.documentElement.lang),expected);
  async function open(){
   const user=page.getByRole('button',{name:/Usuário|User menu/i});
   if(!await user.isVisible())await page.locator('.chat-navbar-sidebar button').click();
   await user.click();assert.equal(await page.getByRole('menuitem',{name:/^(Sobre|About)$/}).count(),0);
   await page.getByRole('menuitem',{name:/^(Configurações|Settings)$/}).click();
   if(width<768)await page.locator('[role="tab"][aria-controls="tab-general"]').click();
   await page.locator('#tab-general').waitFor();
  }
  await open();
  const trigger=page.locator('#interface-language-control > button');
  assert.equal(await trigger.innerText(),saved==='en-US'?(expected==='pt-BR'?'Inglês':'English'):saved==='pt-BR'?'Português (Brasil)':expected==='pt-BR'?'Detecção automática':'Auto-detect');
  async function select(index){await trigger.click();await page.locator('#interface-language-control > div button').nth(index).click();}
  await trigger.click();
  const choices=await page.locator('#interface-language-control > div button').allTextContents();
  assert.match(choices[0],/Detecção automática|Auto-detect/);assert.match(choices[1],/Português \(Brasil\)/);
  await trigger.click();
  await select(2);assert.equal(await page.evaluate(()=>document.documentElement.lang),'en-US');
  await select(1);assert.equal(await page.evaluate(()=>document.documentElement.lang),'pt-BR');
  await select(0);assert.equal(await page.evaluate(()=>document.documentElement.lang),automatic);
  assert.equal(await page.evaluate(()=>localStorage.getItem('neveai.language')),'auto');
  await page.screenshot({path:`logs/automatic-language-${locale}-${saved??'default'}-${width}.png`});
  await page.reload({waitUntil:'networkidle'});assert.equal(await page.evaluate(()=>document.documentElement.lang),automatic);
  await open();assert.match(await trigger.innerText(),/Detecção automática|Auto-detect/);
  assert.deepEqual(errors,[]);results.push({locale,saved,width,expected,automatic,errors});await context.close();
 }
 await fs.writeFile('logs/automatic-language-results.json',JSON.stringify(results,null,2));
 console.log('PASS automatic language: pt-PT/pt-BR, English, other languages, manual overrides, reload and removed About shortcut');
}finally{await browser.close();}
