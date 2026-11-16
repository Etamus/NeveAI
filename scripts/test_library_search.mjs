import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
import {createServer} from 'vite';
import {chromium} from '../logs/ui-image-26/node_modules/playwright/index.mjs';
import {installMobileOfflineApi} from './fixtures/mobile-offline-api.mjs';
const origin='http://localhost:5194',output='logs/library-search';
const png=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j5S8AAAAASUVORK5CYII=','base64');
const items=Array.from({length:180},(_,i)=>({id:`item-${i}`,filename:`${i>=140?'Match':'Creation'} ${i}.${i%3===0?'png':i%3===1?'mp4':'pdf'}`,meta:{content_type:i%3===0?'image/png':i%3===1?'video/mp4':'application/pdf'},created_at:2000-i,updated_at:1}));
let server,browser,page;
const results=[];
try{
 await fs.mkdir(output,{recursive:true});
 server=await createServer({cacheDir:'node_modules/.vite-library-search',plugins:[{name:'library-search-fixture',configResolved(config){config.server.proxy=undefined;}}],server:{port:5194,strictPort:true,watch:{ignored:['**/logs/**','**/scripts/**','**/docs/**']}}});
 await server.listen();browser=await chromium.launch();
 for(const width of [1440,1024,768,390]){
  page=await browser.newPage({viewport:{width,height:900}});page.setDefaultTimeout(15000);
  const errors=[],requests=[];page.on('pageerror',error=>errors.push(error.message));await installMobileOfflineApi(page);
  await page.route('**/api/v1/files/**',async route=>{
   const url=new URL(route.request().url());
   if(url.pathname.endsWith('/generated')){
    const query=url.searchParams.get('query')??'',kind=url.searchParams.get('kind'),skip=Number(url.searchParams.get('skip')),limit=Number(url.searchParams.get('limit'));requests.push({query,kind,skip,limit});
    const filtered=items.filter(item=>(kind==='all'||(kind==='document'?item.meta.content_type.startsWith('application/'):item.meta.content_type.startsWith(kind+'/')))&&item.filename.toLowerCase().includes(query.toLowerCase()));
    if(query==='Creation')await new Promise(resolve=>setTimeout(resolve,650));
    return route.fulfill({json:filtered.slice(skip,skip+limit)}).catch(()=>{});
   }
   if(url.pathname.endsWith('/thumbnail')||url.pathname.endsWith('/content'))return route.fulfill({body:png,contentType:'image/png'});
   return route.fulfill({json:{}});
  });
  await page.goto(origin+'/library',{waitUntil:'networkidle',timeout:90000});
  const search=page.getByRole('textbox',{name:/Search library|Pesquisar na biblioteca/}),cards=page.locator('.library-grid article');
  await search.waitFor();await page.waitForFunction(()=>document.querySelectorAll('.library-grid article').length===50);
  const metrics=await search.evaluate(el=>{const field=el.closest('.search-field').getBoundingClientRect(),toolbar=el.closest('.library-toolbar'),rect=toolbar.getBoundingClientRect(),nav=toolbar.querySelector('nav').getBoundingClientRect();return {width:field.width,right:field.right,expectedRight:rect.right-parseFloat(getComputedStyle(toolbar).paddingRight),height:field.height,expectedHeight:2*parseFloat(getComputedStyle(document.documentElement).fontSize),centerY:field.y+field.height/2,filtersCenterY:nav.y+nav.height/2};});
  assert(Math.abs(metrics.right-metrics.expectedRight)<1,'library search right aligned');
  assert(Math.abs(metrics.height-metrics.expectedHeight)<1,'standard search height');
  if(width===1440)assert(Math.abs(metrics.centerY-metrics.filtersCenterY)<1,'search beside filters');
  await search.fill('Match');await page.waitForFunction(()=>document.querySelectorAll('.library-grid article').length===40);
  assert((await cards.first().innerText()).includes('Match 140'),'server finds items beyond first page');
  await Promise.all([page.waitForResponse(response=>{const url=new URL(response.url());return url.pathname.endsWith('/generated')&&url.searchParams.get('kind')==='image'&&url.searchParams.get('query')==='Match';}),page.getByRole('button',{name:/^Images$|^Imagens$/}).click()]);await page.waitForFunction(()=>document.querySelectorAll('.library-grid article').length===13);
  assert(requests.some(request=>request.kind==='image'&&request.query==='Match'));
  await page.getByRole('button',{name:/^All$|^Tudo$/}).click();await page.waitForFunction(()=>document.querySelectorAll('.library-grid article').length===40);
  await search.fill('Creation');await page.waitForRequest(request=>new URL(request.url()).searchParams.get('query')==='Creation');
  await search.fill('Match 170');await page.waitForFunction(()=>document.querySelectorAll('.library-grid article').length===1);
  await page.waitForTimeout(800);assert((await cards.first().innerText()).includes('Match 170'),'late query cannot replace latest');
  await search.fill('No matching entry');await page.getByText(/No matching creations|Nenhum resultado encontrado/).waitFor();assert.equal(await cards.count(),0);
  await search.fill('');await page.waitForFunction(()=>document.querySelectorAll('.library-grid article').length===50);
  await page.getByRole('button',{name:/Load more|Carregar mais/}).click();await page.waitForFunction(()=>document.querySelectorAll('.library-grid article').length===100);
  assert(requests.some(request=>request.query===''&&request.skip===50));
  for(const theme of ['dark','light']){
   await page.evaluate(theme=>{document.documentElement.classList.toggle('dark',theme==='dark');document.documentElement.classList.toggle('light',theme==='light');},theme);
   await page.screenshot({path:`${output}/${width}-${theme}.png`});
  }
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  assert.deepEqual(errors,[]);results.push({width,metrics,queries:requests.length,offPageMatch:true,filter:true,lateResponse:true,clearAndPagination:true});await page.close();
 }
 await fs.writeFile(`${output}/results.json`,JSON.stringify(results,null,2));console.log(JSON.stringify(results,null,2));
}catch(error){await page?.screenshot({path:`${output}/failed.png`});throw error;}finally{await browser?.close();await server?.close();}
