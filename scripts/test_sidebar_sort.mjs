import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
import {createServer} from 'vite';
import {chromium} from '../logs/ui-image-26/node_modules/playwright/index.mjs';
import {installMobileOfflineApi} from './fixtures/mobile-offline-api.mjs';

const output='logs/sidebar-sort', origin='http://localhost:5192';
const rows=Array.from({length:135},(_,i)=>({id:`sort-${String(i).padStart(3,'0')}`,title:`${['Zebra','Beta','Agata'][i%3]} ${String(i).padStart(3,'0')}`,created_at:1700000000+i,updated_at:1700000000+i}));
const recent=[...rows].reverse(), named=[...rows].sort((a,b)=>a.title<b.title?-1:1);
let server,browser;
const results=[];
try {
 await fs.mkdir(output,{recursive:true});
 server=await createServer({cacheDir:'node_modules/.vite-sidebar-sort',plugins:[{
  name:'sidebar-sort-fixture',enforce:'pre',
  configResolved(config){config.server.proxy=undefined;},
  async load(id){if(id.endsWith('/src/lib/components/layout/Sidebar.svelte'))return(await fs.readFile(id,'utf8')).replace('</script>',`onMount(()=>{window.__sidebarSort={async open(){config.update(c=>({...c,features:{...c.features,enable_folders:true}}));showSidebar.set(true);showFolders=true;await tick();await initChatList();},more:loadMoreChats,state(){return {sort:chatSort,ids:$chats.map(c=>c.id),page:$currentChatPage};}};return()=>delete window.__sidebarSort;});\n</script>`);}
 }],server:{port:5192,strictPort:true,watch:{ignored:['**/logs/**','**/docs/**','**/scripts/**']}}});
 await server.listen();browser=await chromium.launch();
 for(const [name,viewport] of [['desktop',{width:1440,height:1000}],['mobile',{width:390,height:844}]]) {
  const context=await browser.newContext({viewport,serviceWorkers:'block'}),page=await context.newPage(),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.routeWebSocket('**/*',ws=>ws.close());
  await page.route('**/*',route=>new URL(route.request().url()).origin===origin?route.continue():route.fulfill({status:503,body:'Offline fixture'}));
  await installMobileOfflineApi(page);
  await page.route('**/api/v1/folders/',route=>route.fulfill({json:[{id:'project-fixture',name:'Project fixture',parent_id:null,updated_at:1,data:{},meta:{}}]}));
  let slowPage=false;
  await page.route('**/api/v1/chats/**',async route=>{
   const url=new URL(route.request().url());
   if(url.pathname.endsWith('/pinned'))return route.fulfill({json:[{...rows[0],id:'pinned-test',title:'Pinned fixture'}]});
   if(url.pathname==='/api/v1/chats/'){
    const number=Number(url.searchParams.get('page')??1),items=url.searchParams.get('sort')==='name'?named:recent;
    if(slowPage&&number===2&&url.searchParams.get('sort')!=='name')await new Promise(r=>setTimeout(r,600));
    return route.fulfill({json:items.slice((number-1)*60,number*60)});
   }
   return route.fulfill({json:[]});
  });
  await page.addInitScript(()=>{localStorage.token='fixture';localStorage.locale='pt-BR';localStorage.setItem('sidebar-pinned-chats-folder-state','true');localStorage.setItem('sidebar-folders-folder-state','true');});
  await page.goto(origin,{waitUntil:'networkidle',timeout:90000});
  await page.waitForFunction(()=>window.__sidebarSort);
  await page.evaluate(()=>window.__sidebarSort.open());
  const section=page.locator('[data-sidebar-section="sidebar-chats"]');
  const trigger=page.getByRole('button',{name:/Ordenar conversas|Sort conversations/});
  await trigger.waitFor({state:'visible'});
  await page.waitForTimeout(350);
  await page.waitForFunction(()=>window.__sidebarSort.state().ids.length>=60);
  assert.deepEqual((await page.evaluate(()=>window.__sidebarSort.state().ids)).slice(0,60),recent.slice(0,60).map(r=>r.id));
  const header=section.locator('#sidebar-folder-button').first();
  const geometry=await header.evaluate(el=>{const title=el.querySelector('button>div'),svg=title.querySelector('svg'),range=document.createRange();range.selectNodeContents(title.childNodes[0]);return {text:range.getBoundingClientRect().toJSON(),icon:svg.getBoundingClientRect().toJSON()};});
  assert(geometry.icon.x>=geometry.text.right&&geometry.icon.x-geometry.text.right<12,'chevron beside title');
  assert.equal(await page.locator('[data-sidebar-section="sidebar-pinned-chats"]').getByRole('button',{name:/Ordenar conversas|Sort conversations/}).count(),0);
  for(const id of ['sidebar-pinned-chats','sidebar-folders','sidebar-chats']){
   const group=page.locator(`[data-sidebar-section="${id}"]`);
   const heading=group.locator('#sidebar-folder-button').first();
   assert(await heading.isVisible());
   const inline=await heading.evaluate(el=>{const title=el.querySelector('button>div'),svg=title.querySelector('svg'),range=document.createRange();range.selectNodeContents(title.childNodes[0]);const text=range.getBoundingClientRect(),icon=svg.getBoundingClientRect();return icon.x>=text.right&&icon.x-text.right<12;});
   assert(inline,'inline chevron for '+id);
   const button=heading.locator(':scope > button').first();
   const path=button.locator('svg path').first();
   assert.equal(await path.getAttribute('d'),'m19.5 8.25-7.5 7.5-7.5-7.5','open chevron down');
   const background=await heading.evaluate(el=>getComputedStyle(el).backgroundColor);
   await button.hover();
   assert.equal(await heading.evaluate(el=>getComputedStyle(el).backgroundColor),background,'no header hover');
   await button.click();
   assert.equal(await path.getAttribute('d'),'m8.25 4.5 7.5 7.5-7.5 7.5','closed chevron right');
   await button.click();
   assert.equal(await path.getAttribute('d'),'m19.5 8.25-7.5 7.5-7.5-7.5');
  }
  slowPage=true;
  await page.evaluate(()=>{void window.__sidebarSort.more();});
  await trigger.click();
  assert(await section.getByText(recent[0].title,{exact:true}).isVisible(),'sort trigger must not collapse conversations');
  await page.getByRole('menuitemradio',{name:/^Nome$|^Name$/}).click();
  await page.waitForFunction(()=>window.__sidebarSort.state().sort==='name');
  await page.waitForTimeout(800);
  await page.evaluate(async()=>{await window.__sidebarSort.more();await window.__sidebarSort.more();});
  assert.deepEqual(await page.evaluate(()=>window.__sidebarSort.state().ids),named.map(r=>r.id));
  assert.equal(await page.evaluate(()=>localStorage.getItem('neveai.sidebarChatSort')),'name');
  for(const theme of ['dark','light']){
   await page.evaluate(theme=>{document.documentElement.classList.toggle('dark',theme==='dark');document.documentElement.classList.toggle('light',theme==='light');},theme);
   await trigger.click();
   const item=page.getByRole('menuitemradio',{name:/^Nome$|^Name$/});
   assert.equal(await item.getAttribute('aria-checked'),'true');
   assert((await item.locator('svg path').getAttribute('d')).includes('a9 9'),'selected option uses circled check');
   const visual=await trigger.evaluate(el=>{
    const icon=el.querySelector('svg').getBoundingClientRect(),button=el.getBoundingClientRect();
    const color=element=>{const canvas=document.createElement('canvas');canvas.width=canvas.height=1;const ctx=canvas.getContext('2d');ctx.fillStyle=getComputedStyle(element).backgroundColor;ctx.fillRect(0,0,1,1);return [...ctx.getImageData(0,0,1,1).data].slice(0,3).reduce((sum,value)=>sum+value,0);};
    return {ratio:icon.width/button.width,button:color(el),header:color(el.closest('#sidebar-folder-button'))};
   });
   assert(Math.abs(visual.ratio-3.5/6)<0.01,'smaller icon, unchanged button');
   if(theme==='dark')assert(visual.button>visual.header,'button highlight brighter than conversation header');
   if(theme==='dark')assert(await trigger.evaluate(el=>{const rgb=getComputedStyle(el).backgroundColor.match(/\d+/g).slice(0,3).map(Number);return rgb.every(value=>value<100);}), 'dark trigger background');
   await page.screenshot({path:`${output}/${name}-${theme}.png`});
   await page.keyboard.press('Escape');
   await item.waitFor({state:'hidden'});
  }
  await page.reload({waitUntil:'networkidle'});
  await page.waitForFunction(()=>window.__sidebarSort);
  await page.evaluate(()=>window.__sidebarSort.open());
  await page.waitForFunction(()=>window.__sidebarSort.state().ids[0]==='sort-002');
  await trigger.click();
  await page.getByRole('menuitemradio',{name:/Mais recentes|Most recent/}).click();
  await page.waitForFunction(()=>window.__sidebarSort.state().ids[0]==='sort-134');
  await trigger.focus();await page.keyboard.press('Enter');
  await page.getByRole('menuitemradio',{name:/Mais recentes|Most recent/}).waitFor({state:'visible'});
  await page.keyboard.press('Escape');
  assert.deepEqual(errors,[]);
  results.push({name,geometry,tests:'ordering, pagination, stale response, persistence, menu, themes passed'});
  await context.close();
 }
 await fs.writeFile(`${output}/results.json`,JSON.stringify(results,null,2));
 console.log(JSON.stringify(results,null,2));
}finally{await browser?.close();await server?.close();}
