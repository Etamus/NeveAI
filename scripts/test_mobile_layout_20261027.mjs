import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
import {createServer} from 'vite';
import {chromium} from '../logs/ui-image-26/node_modules/playwright/index.mjs';

const appHook=`onMount(()=>{window.__mobileUI={settings:()=>showSettings.set(true),search:()=>showSearch.set(true),sidebar:()=>showSidebar.set(true),toasts:(show)=>{updateToastDismissed=!show;updateToastShownVersion=show?'b-test':'';neveDownloadToast.set(show?{name:'Modelo de exemplo',progress:0.4,label:'Baixando',cancelling:false,onCancel:()=>{}}:null);modelRuntimeToast=show?{operationId:'test',modelId:'test',modelName:'Modelo de exemplo',action:'load',phase:'start',timestamp:Date.now()}:null;}};return()=>delete window.__mobileUI;});`;
const composerHook=`onMount(()=>{window.__mobileImage=(quality)=>{stableDiffusionEnabled=true;stableDiffusionQuality=quality;};return()=>delete window.__mobileImage;});`;
let server,browser;const results=[];
const visibleDialog=page=>page.locator('.modal[aria-hidden="false"]').last();
const dialogBox=page=>visibleDialog(page).locator(':scope > div').boundingBox();
try{
 await fs.mkdir('logs/mobile-20261027',{recursive:true});
 server=await createServer({plugins:[{name:'mobile-layout-test',enforce:'pre',async load(id){
  if(id.endsWith('/src/routes/(app)/+layout.svelte'))return(await fs.readFile(id,'utf8')).replace('</script>',appHook+'\n</script>');
  if(id.endsWith('/src/lib/components/chat/Chat.svelte'))return(await fs.readFile(id,'utf8')).replace('</script>',composerHook+'\n</script>');
  if(id.endsWith('/src/routes/+layout.svelte'))return(await fs.readFile(id,'utf8')).replace('</script>',`onMount(()=>{window.__mobileTheme=value=>{theme.set(value);document.documentElement.classList.toggle('dark',value==='dark');};window.__mobileError=()=>toast.error('Teste de erro');window.__mobileDismiss=()=>toast.dismiss();});\n</script>`);
 }}],server:{port:5188,strictPort:true,watch:{ignored:['**/logs/**','**/scripts/**','**/docs/**']}}});await server.listen();
 browser=await chromium.launch({ignoreDefaultArgs:['--hide-scrollbars']});
 for(const width of (process.env.MOBILE_WIDTHS??'320,390,430,767,768,1440').split(',').map(Number))for(const dark of process.env.MOBILE_LIGHT_ONLY?[false]:[false,true]){
  const height=width>=768?1000:844,mobile=width<768;
  const page=await browser.newPage({viewport:{width,height},hasTouch:mobile});page.setDefaultTimeout(15000);
  const errors=[];page.on('pageerror',e=>{errors.push(e.message);console.log('PAGEERROR',e.message);});
  await page.route('**/api/**',r=>r.request().method()==='GET'||r.request().url().includes('/auths/')?r.continue():r.fulfill({json:{}}));
  await page.goto('http://localhost:5188',{waitUntil:'networkidle',timeout:90000});await page.waitForFunction(()=>window.__mobileUI&&window.__mobileImage);await page.evaluate(()=>document.fonts.ready);
  await page.evaluate(theme=>window.__mobileTheme(theme),dark?'dark':'light');
  const shot=name=>page.screenshot({path:`logs/mobile-20261027/${name}-${width}-${dark?'dark':'light'}.png`});
  const url=page.url();const initialHistory=await page.evaluate(()=>history.length);
  const full=async(label)=>{const box=await dialogBox(page);assert(box,label+' missing');if(mobile)assert(Math.abs(box.x)<1&&Math.abs(box.y)<1&&Math.abs(box.width-width)<1&&Math.abs(box.height-height)<1,label+' not fullscreen '+JSON.stringify(box));else assert(box.width<width-30&&box.height<height,label+' changed desktop sizing '+JSON.stringify(box));return box;};
  const back=async()=>{await page.evaluate(()=>history.back());await page.waitForTimeout(300);assert.equal(page.url(),url,'Back navigated away from the chat');};
  if(mobile)await page.locator('button[aria-label="Models"]').tap();else await page.locator('button[aria-label="Models"]').click();await page.locator('.unified-models-shell').waitFor();await page.waitForTimeout(250);
  const models=await full('models');assert.equal(await visibleDialog(page).locator('.unified-global-settings').count(),0);
  if(mobile)assert.equal(await visibleDialog(page).locator('button[aria-label="Close"]').count(),0);
  const modelSpacing=await page.locator('.unified-model-name').first().evaluate(e=>{const name=e.getBoundingClientRect(),meta=e.parentElement.nextElementSibling.getBoundingClientRect();return{gap:meta.top-name.bottom,max:getComputedStyle(e).maxWidth};});
  if(mobile)assert(modelSpacing.gap>=6,'Model metadata is too close');
  await shot('models');
  await visibleDialog(page).getByText('Baixar modelos',{exact:true}).click();await page.locator('.download-models-shell').waitFor();await page.waitForTimeout(300);
  const download=await full('download');assert.equal(await page.locator('.download-models-close').isVisible(),!mobile);
  const catalog=page.locator('.catalog-model-row').first();await catalog.waitFor();
  const gaps=await catalog.evaluate(e=>{const r=[...e.children].map(c=>c.getBoundingClientRect());return{check:r[1].left-r[0].right,text:r[2].left-r[1].right};});
  if(mobile)assert(gaps.check>=11&&gaps.text>=11,'Catalog spacing is compressed '+JSON.stringify(gaps));
  await shot('download');
  if(mobile){await back();await page.locator('.download-models-shell').waitFor({state:'hidden'});assert(await page.locator('.unified-models-shell').isVisible());
   await page.locator('.unified-model-name').first().click();await page.locator('.unified-model-editor').waitFor({state:'visible'});await back();assert(await page.locator('.unified-models-shell').isVisible());
   await back();await page.locator('.unified-models-shell').waitFor({state:'hidden'});}
  else {await page.locator('.download-models-close').click();await page.keyboard.press('Escape');await page.waitForTimeout(250);assert.equal(await page.evaluate(()=>history.length),initialHistory,'Desktop dialogs created mobile history entries');}
  await page.evaluate(()=>window.__mobileUI.settings());await page.locator('.settings-shell').waitFor({state:'visible'});
  const settings=await full('settings');assert.equal(await page.locator('.settings-close').isVisible(),!mobile);
  if(mobile){assert(!(await page.locator('.settings-content').isVisible()));const tabs=await page.locator('#settings-tabs-container > button').evaluateAll(es=>es.map(e=>({x:e.getBoundingClientRect().x,y:e.getBoundingClientRect().y,w:e.getBoundingClientRect().width})));assert(tabs.every((t,i)=>!i||(t.y>tabs[i-1].y&&t.x===tabs[i-1].x)));}
  await shot('settings-index');
  await page.locator('#settings-tabs-container > button').first().click();await page.locator('.settings-content').waitFor({state:'visible'});await page.waitForTimeout(200);
  await shot('settings-detail');
  if(mobile){assert(!(await page.locator('#settings-tabs-container').isVisible()));await back();assert(await page.locator('#settings-tabs-container').isVisible());assert(!(await page.locator('.settings-content').isVisible()));
   for(const index of [1,2,3]){await page.locator('#settings-tabs-container > button').nth(index).click();await page.locator('.settings-content').waitFor({state:'visible'});await back();assert(await page.locator('#settings-tabs-container').isVisible());}
   await back();await page.locator('.settings-shell').waitFor({state:'hidden'});}
  else await page.locator('.settings-close').click();
  await page.evaluate(()=>window.__mobileUI.search());await page.locator('.search-modal-shell').waitFor({state:'visible'});
  const search=await full('search');assert.equal(await page.locator('.search-modal-close').isVisible(),!mobile);
  await shot('search');
  if(mobile){await page.setViewportSize({width,height:520});await page.waitForTimeout(150);assert(Math.abs((await dialogBox(page)).height-520)<=1);await page.setViewportSize({width,height});await page.waitForTimeout(150);}
  if(mobile){await back();await page.locator('.search-modal-shell').waitFor({state:'hidden'});}else await page.locator('.search-modal-close').click();
  await page.evaluate(()=>window.__mobileUI.toasts(true));await page.waitForTimeout(250);
  const toasts=await page.locator('[data-neve-toast] > div').evaluateAll(es=>es.map(e=>{const r=e.getBoundingClientRect();return{x:r.x,y:r.y,w:r.width,right:r.right,bottom:r.bottom};}));
  assert(toasts.length>=2,'Toast fixtures missing');if(mobile){assert(toasts.every(t=>Math.abs(t.right-(width-12))<=1&&t.w<=288.5&&t.y>=56),JSON.stringify(toasts));for(let i=1;i<toasts.length;i++)assert(toasts[i].y>=toasts[i-1].bottom,'Toast stack overlaps');}
  await page.evaluate(()=>window.__mobileError());await page.waitForTimeout(450);
  const errorToast=await page.locator('[data-sonner-toast]').last().boundingBox();if(mobile)assert(errorToast.width<=289&&Math.abs(errorToast.x+errorToast.width-(width-12))<=1,'Error toast position differs '+JSON.stringify(errorToast));
  await shot('toasts');await page.evaluate(()=>{window.__mobileUI.toasts(false);window.__mobileDismiss();});
  await page.evaluate(()=>window.__mobileUI.sidebar());await page.locator('#sidebar').waitFor({state:'visible'});await page.waitForTimeout(350);
  await page.locator('#sidebar').getByRole('button').filter({has:page.locator('img[aria-label]')}).last().click();
  const menu=page.locator('[role="menu"]').last();await menu.waitFor();await page.waitForTimeout(150);const userMenu=await menu.boundingBox(),sidebar=await page.locator('#sidebar').boundingBox();
  if(mobile)assert(Math.abs(userMenu.x-sidebar.x-8)<=1&&Math.abs(sidebar.x+sidebar.width-userMenu.x-userMenu.width-8)<=1,'User menu does not fill the sidebar '+JSON.stringify({userMenu,sidebar}));await shot('user');await page.keyboard.press('Escape');
  for(const quality of ['neve_image_2','qwen_image_2s']){
   await page.evaluate(q=>window.__mobileImage(q),quality);await page.waitForTimeout(150);
   const selector=quality==='neve_image_2'?'#image-style-dropdown-container':'#image-mode-dropdown-container';
   assert.equal(await page.locator(selector).isVisible(),!mobile,'Image selector mobile visibility is wrong: '+quality);
  }
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'Horizontal page overflow');
  assert.deepEqual(errors,[]);results.push({width,dark,models,modelSpacing,download,gaps,settings,search,toasts,errorToast,userMenu});console.log('PASS '+width+' '+(dark?'dark':'light'));await page.close();
 }
 await fs.writeFile('logs/mobile-20261027/results.json',JSON.stringify(results,null,2));console.log('PASS '+results.length+' viewport configurations');
}catch(error){for(const page of browser?.contexts().flatMap(c=>c.pages())??[]){await page.screenshot({path:'logs/mobile-20261027/failure.png'}).catch(()=>{});console.log(await page.evaluate(()=>({url:location.href,state:history.state,dialogs:[...document.querySelectorAll('.modal')].map(e=>({hidden:e.getAttribute('aria-hidden'),text:e.textContent.slice(0,180)}))})).catch(()=>null));}throw error;}finally{await browser?.close();await server?.close();}
