import fs from 'node:fs/promises';
import {constants} from 'node:fs';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {createServer} from 'vite';
import {chromium} from '../logs/ui-image-26/node_modules/playwright/index.mjs';
import {installMobileOfflineApi} from './fixtures/mobile-offline-api.mjs';
import JSZip from 'jszip';
import * as XLSX from 'xlsx';
import utils from '../logs/ui-image-26/node_modules/playwright-core/lib/utilsBundle.js';

const routeDir=new URL('../src/routes/__optimization_test/',import.meta.url);
const routeFile=new URL('+page.svelte',routeDir);
const output='logs/optimization-library';
const origin='http://localhost:5191';
// A valid, small image shared by every slide also exercises decoder reuse.
const png=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j5S8AAAAASUVORK5CYII=','base64');
const raster=new utils.PNG({width:1280,height:720});
for(let i=0;i<raster.data.length;i+=4){raster.data[i]=(i/4)%255;raster.data[i+1]=120;raster.data[i+2]=180;raster.data[i+3]=255;}
const zip=new JSZip();
zip.file('ppt/media/logo.png',utils.PNG.sync.write(raster));
zip.file('ppt/presentation.xml','<p:presentation xmlns:p="p"><p:sldSz cx="9144000" cy="5143500"/></p:presentation>');
for(let i=1;i<=30;i++){
 zip.file(`ppt/slides/slide${i}.xml`,`<p:sld xmlns:p="p" xmlns:a="a" xmlns:r="r"><p:spTree><p:pic><p:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="952500" cy="952500"/></a:xfrm></p:spPr><p:blipFill><a:blip r:embed="logo"/></p:blipFill></p:pic><p:sp><p:spPr><a:xfrm><a:off x="1000000" y="500000"/><a:ext cx="7000000" cy="3000000"/></a:xfrm></p:spPr><p:txBody><a:p><a:r><a:rPr sz="2400"/><a:t>Slide ${i}: preserved content</a:t></a:r></a:p></p:txBody></p:sp></p:spTree></p:sld>`);
 zip.file(`ppt/slides/_rels/slide${i}.xml.rels`,'<Relationships><Relationship Id="logo" Target="../media/logo.png"/></Relationships>');
}
const pptx=await zip.generateAsync({type:'nodebuffer'});
const sheet=XLSX.utils.aoa_to_sheet(Array.from({length:1200},(_,r)=>[r,`Row ${r}`,r*0.25,'<unsafe> & text']));
const workbook=XLSX.utils.book_new();XLSX.utils.book_append_sheet(workbook,sheet,'First');XLSX.utils.book_append_sheet(workbook,sheet,'Second');
const xlsx=XLSX.write(workbook,{type:'buffer',bookType:'xlsx'});
const baseline=execFileSync('git',['show','HEAD:src/lib/utils/pptxToHtml.ts'],{encoding:'utf8'});
const results=[];let server,browser;
await fs.mkdir(output,{recursive:true});
await fs.mkdir(routeDir,{recursive:true});
await fs.copyFile(new URL('./fixtures/optimization-review.svelte',import.meta.url),routeFile,constants.COPYFILE_EXCL);
try {
 server=await createServer({plugins:[{name:'optimization-fixture',enforce:'pre',
  configResolved(config){config.server.proxy=undefined;},
  resolveId(source){if(source.endsWith('pptx-before-audit.ts'))return process.cwd().replaceAll('\\','/')+'/src/lib/utils/pptx-before-audit.ts';},
  async load(id){
   if(id===routeFile.pathname.replace(/^\//,'')||id.endsWith('/__optimization_test/+page.svelte')) {
    return (await fs.readFile(routeFile,'utf8')).replaceAll('../../src/','../../');
   }
   if(id.endsWith('/src/lib/utils/pptx-before-audit.ts'))return baseline;
   if(id.endsWith('/src/lib/utils/excelToTable.ts'))return (await fs.readFile(id,'utf8')).replace(
    'export async function excelToTable(worksheet: WorkSheet): Promise<ExcelTableResult> {',
    'export async function excelToTable(worksheet: WorkSheet): Promise<ExcelTableResult> { window.__sheetRenders = (window.__sheetRenders || 0) + 1;'
   );
  }
 }],server:{port:5191,strictPort:true,watch:{ignored:['**/logs/**','**/scripts/**']}}});
 await server.listen();browser=await chromium.launch({ignoreDefaultArgs:['--hide-scrollbars']});
 for(const [name,viewport] of [['desktop',{width:1440,height:1000}],['mobile',{width:390,height:844}]]) {
  const page=await browser.newPage({viewport});page.setDefaultTimeout(20000);
  const errors=[],queries=[];let delay=0;
  const items=Array.from({length:550},(_,i)=>({id:`image-${i}`,filename:`Image ${i}.png`,meta:{content_type:'image/png'},created_at:1000-i,updated_at:1}));
  items.unshift({id:'xlsx',filename:'Spreadsheet.xlsx',meta:{content_type:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'},created_at:2000,updated_at:1},
   {id:'pptx',filename:'Slides.pptx',meta:{content_type:'application/vnd.openxmlformats-officedocument.presentationml.presentation'},created_at:1999,updated_at:1});
  page.on('pageerror',e=>errors.push(e.message));
  await installMobileOfflineApi(page);
  await page.route('**/api/v1/files/**',async route=>{
   const url=new URL(route.request().url()),parts=url.pathname.split('/'),id=parts[4];
   if(id==='generated'){
    const kind=url.searchParams.get('kind'),skip=Number(url.searchParams.get('skip')),limit=Number(url.searchParams.get('limit'));
    queries.push({kind,skip,limit});
    const filtered=items.filter(item=>kind==='all'||(kind==='image'?item.id.startsWith('image-'):kind==='document'?['xlsx','pptx'].includes(item.id):false));
    if(delay)await new Promise(r=>setTimeout(r,delay));
    return route.fulfill({json:filtered.slice(skip,skip+limit)});
   }
   if(parts.at(-1)==='thumbnail')return route.fulfill({body:png,contentType:'image/png'});
   if(parts.at(-1)==='content')return route.fulfill({body:id==='xlsx'?xlsx:id==='pptx'?pptx:png,contentType:'application/octet-stream'});
   const file=items.find(item=>item.id===id);
   return route.fulfill({json:file?{...file,data:{}}:{}});
  });
  await page.goto(origin+'/__optimization_test',{waitUntil:'networkidle',timeout:90000});
  await page.waitForFunction(()=>window.__auditConverters);
  await page.waitForFunction(()=>document.querySelectorAll('.library-grid article').length===50);
  for(let i=0;i<9;i++){
   await page.getByRole('button',{name:'Load more',exact:true}).click();
   await page.waitForFunction(count=>document.querySelectorAll('.library-grid article').length===count,(i+2)*50);
  }
  const before=await page.locator('main').evaluate(el=>{el.scrollTop=el.scrollHeight;window.__firstLibraryCard=document.querySelector('.library-grid article');return el.scrollTop;});
  queries.length=0;delay=400;
  await page.evaluate(()=>window.dispatchEvent(new Event('neve:files-changed')));
  await page.waitForTimeout(100);
  assert.equal(await page.locator('.library-grid article').count(),500);
  await page.waitForFunction(()=>document.querySelector('main').getAttribute('aria-busy')==='false');
  assert.deepEqual(queries,[{kind:'all',skip:0,limit:500}]);
  assert(await page.evaluate(()=>window.__firstLibraryCard===document.querySelector('.library-grid article')));
  assert.equal(await page.locator('main').evaluate(el=>el.scrollTop),before);
  delay=0;
  await page.getByRole('button',{name:'Load more',exact:true}).click();
  await page.waitForFunction(()=>document.querySelectorAll('.library-grid article').length===550);
  await page.getByRole('button',{name:'Load more',exact:true}).click();
  await page.waitForFunction(()=>document.querySelectorAll('.library-grid article').length===552);
  assert.equal(await page.getByRole('button',{name:'Load more',exact:true}).count(),0);
  await page.getByRole('button',{name:'Documents',exact:true}).click();
  await page.waitForFunction(()=>document.querySelectorAll('.library-grid article').length===2);
  await page.getByRole('button',{name:'Spreadsheet.xlsx',exact:true}).click();
  await page.locator('.file-viewer-content table').waitFor();
  assert.equal(await page.locator('.file-viewer-content tbody tr').count(),1200);
  assert((await page.locator('.file-viewer-content').innerText()).includes('Row 1199'));
  assert.equal(await page.locator('.file-viewer-content unsafe').count(),0);
  assert.equal(await page.evaluate(()=>window.__sheetRenders),1);
  await page.getByRole('button',{name:'Second',exact:true}).click();
  await page.waitForFunction(()=>window.__sheetRenders===2);
  await page.getByRole('button',{name:'First',exact:true}).click();
  await page.waitForTimeout(150);
  assert.equal(await page.evaluate(()=>window.__sheetRenders),2);
  assert.equal(await page.locator('.file-viewer-content tbody tr').count(),1200);
  await page.screenshot({path:`${output}/${name}-spreadsheet.png`});
  await page.keyboard.press('Escape');
  await page.getByRole('button',{name:'Slides.pptx',exact:true}).click();
  await page.locator('img[alt="Slide 1"]').waitFor();
  assert(await page.locator('img[alt="Slide 1"]').evaluate(el=>el.complete&&el.naturalWidth>0));
  await page.screenshot({path:`${output}/${name}-slides.png`});
  await page.keyboard.press('Escape');
  const conversion=await page.evaluate(async()=>{
   const data=await (await fetch('/api/v1/files/pptx/content')).arrayBuffer();
   const before=await import('/src/lib/utils/pptx-before-audit.ts');
   const OriginalImage=window.Image;let decodes=0;
   window.Image=class extends OriginalImage {constructor(...args){super(...args);decodes++;}};
   try {
    let start=performance.now();const old=await before.pptxToImages(data);const oldMs=performance.now()-start,oldDecodes=decodes;
    decodes=0;start=performance.now();const next=await window.__auditConverters.pptxToImages(data);
    return {identical:JSON.stringify(old)===JSON.stringify(next),oldMs,newMs:performance.now()-start,oldDecodes,newDecodes:decodes,slides:next.images.length};
   }finally{window.Image=OriginalImage;}
  });
  assert(conversion.identical);assert.equal(conversion.slides,30);assert.equal(conversion.newDecodes,1);assert.equal(conversion.oldDecodes,30);
  assert.deepEqual(errors,[]);results.push({name,refreshRequestCount:1,stableScroll:before,conversion,errors});
  await page.close();
 }
 await fs.writeFile(`${output}/results.json`,JSON.stringify(results,null,2));console.log(JSON.stringify(results));
}finally{await browser?.close();await server?.close();await fs.unlink(routeFile);await fs.rmdir(routeDir);}
