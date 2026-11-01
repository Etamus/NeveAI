import fs from 'node:fs/promises';
import {constants} from 'node:fs';
import assert from 'node:assert/strict';
import {createServer} from 'vite';
import {chromium} from '../logs/ui-image-26/node_modules/playwright/index.mjs';
import {installMobileOfflineApi} from './fixtures/mobile-offline-api.mjs';
import JSZip from 'jszip';
import * as XLSX from 'xlsx';

const routeDir=new URL('../src/routes/__office_navigation_test/',import.meta.url);
const routeFile=new URL('+page.svelte',routeDir);
const output='logs/office-navigation';
const workbook=XLSX.utils.book_new();
for(let i=1;i<=24;i++) XLSX.utils.book_append_sheet(workbook,
 XLSX.utils.aoa_to_sheet(Array.from({length:120},(_,r)=>[`Sheet ${i}`,r,'Preserved cell'])),`Sheet ${i}`);
const xlsx=XLSX.write(workbook,{type:'buffer',bookType:'xlsx'});
const zip=new JSZip();
zip.file('ppt/presentation.xml','<p:presentation xmlns:p="p"><p:sldSz cx="9144000" cy="5143500"/></p:presentation>');
for(let i=1;i<=3;i++)zip.file(`ppt/slides/slide${i}.xml`,`<p:sld xmlns:p="p" xmlns:a="a"><p:spTree><p:sp><p:spPr><a:xfrm><a:off x="1000000" y="500000"/><a:ext cx="7000000" cy="3000000"/></a:xfrm></p:spPr><p:txBody><a:p><a:r><a:rPr sz="2400"/><a:t>Slide ${i}</a:t></a:r></a:p></p:txBody></p:sp></p:spTree></p:sld>`);
const pptx=await zip.generateAsync({type:'nodebuffer'});
const slide='data:image/svg+xml,'+encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720"><rect width="1280" height="720" fill="#426c72"/><text x="80" y="120" fill="white" font-size="60">Preview</text></svg>');
let server,browser;const results=[];
await fs.mkdir(output,{recursive:true});await fs.mkdir(routeDir,{recursive:true});
await fs.copyFile(new URL('./fixtures/office-navigation.svelte',import.meta.url),routeFile,constants.COPYFILE_EXCL);
try {
 server=await createServer({cacheDir:'node_modules/.vite-office-navigation',plugins:[{name:'office-navigation',enforce:'pre',
  configResolved(config){config.server.proxy=undefined;},
  async load(id){if(id.endsWith('/__office_navigation_test/+page.svelte'))return(await fs.readFile(routeFile,'utf8')).replaceAll('../../src/','../../');}
 }],server:{port:5194,strictPort:true,watch:{ignored:['**/logs/**','**/scripts/**','**/docs/**']}}});
 await server.listen();browser=await chromium.launch();
 for(const [name,viewport] of [['desktop',{width:1440,height:1000}],['short',{width:1024,height:600}],['mobile',{width:390,height:844}],['mobile-landscape',{width:844,height:390}]]) {
  const page=await browser.newPage({viewport});const errors=[];
  page.on('pageerror',e=>{errors.push(e.message);console.error('PAGEERROR',e.stack);});page.setDefaultTimeout(30000);
  page.on('console',message=>{if(message.type()==='error') console.error('BROWSER',message.text());});
  await installMobileOfflineApi(page);
  await page.route('**/api/v1/files/**',route=>{
   const url=new URL(route.request().url()),id=url.pathname.split('/')[4];
   return url.pathname.endsWith('/content')?route.fulfill({body:id==='xlsx'?xlsx:pptx,contentType:'application/octet-stream'}):route.fulfill({json:{id,data:{}}});
  });
  console.log(name,'opening fixture');
  await page.goto('http://localhost:5194/__office_navigation_test',{waitUntil:'networkidle',timeout:120000});
  console.log(name,'opening spreadsheet');
  await page.locator('#open-xlsx').click();
  const modal=page.locator('.file-viewer-content');const nav=modal.locator('.sheet-navigation');
  await nav.getByRole('tab',{name:'Sheet 1',exact:true}).waitFor();
  console.log(name,'spreadsheet loaded');
  assert.equal(await nav.getByRole('tab').count(),24);
  await nav.getByRole('button',{name:'Next',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('.sheet-tab-track')?.scrollLeft>40);
  // Keyboard reaches every tab without dragging the horizontal scrollbar.
  await nav.getByRole('tab',{selected:true}).focus();await page.keyboard.press('End');
  await modal.locator('.office-preview').getByText('Sheet 24',{exact:true}).first().waitFor();
  assert.equal(await nav.getByRole('tab',{name:'Sheet 24',exact:true}).getAttribute('aria-selected'),'true');
  await page.screenshot({path:`${output}/${name}-sheets.png`});
  await page.evaluate(()=>document.documentElement.classList.add('dark'));
  await page.screenshot({path:`${output}/${name}-sheets-dark.png`});
  await page.evaluate(()=>document.documentElement.classList.remove('dark'));
  await page.keyboard.press('Home');
  await modal.locator('.office-preview').getByText('Sheet 1',{exact:true}).first().waitFor();
  await page.keyboard.press('Escape');await modal.waitFor({state:'hidden'});
  await page.reload({waitUntil:'networkidle'});
  console.log(name,'opening presentation');
  await page.locator('#open-pptx').click();
  const slides=modal.locator('.slide-navigation');await slides.getByText('1 / 3').waitFor().catch(async error=>{
   await page.screenshot({path:`${output}/${name}-failure.png`});console.error(await page.locator('body').innerText());throw error;
  });
  const box=await slides.boundingBox();assert(box.y>=0&&box.y+box.height<=viewport.height,'Slide controls must stay visible');
  assert(await slides.locator('button').last().isVisible());await slides.locator('button').last().click();
  await slides.getByText('2 / 3').waitFor();
  console.log(name,'presentation navigation passed');
  const scroll=await modal.locator('.presentation-preview').evaluate(el=>({client:el.clientHeight,scroll:el.scrollHeight}));
  assert(scroll.scroll<=scroll.client+1,'Presentation must not scroll to reach controls');
  await page.screenshot({path:`${output}/${name}-slides.png`});
  await page.evaluate(()=>document.documentElement.classList.add('dark'));
  await page.screenshot({path:`${output}/${name}-slides-dark.png`});
  await page.evaluate(()=>document.documentElement.classList.remove('dark'));
  await page.keyboard.press('Escape');await modal.waitFor({state:'hidden'});
  await page.evaluate(slide=>window.__officeFixture.side('pptx',[slide,slide,slide]),slide);
  const side=page.locator('#side-preview');await side.getByText('1 / 3').waitFor();
  await side.locator('.slide-navigation button').last().click();await side.getByText('2 / 3').waitFor();
  await page.evaluate(()=>window.__officeFixture.side('xlsx',[]));
  const sideNav=side.locator('.sheet-navigation');await sideNav.getByRole('tab',{selected:true}).focus();
  await page.keyboard.press('End');await side.getByRole('cell',{name:'Sheet 24',exact:true}).waitFor();
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  assert.deepEqual(errors,[]);results.push({viewport:name,sheets:24,controls:box,scroll,errors});await page.close();
 }
 await fs.writeFile(`${output}/results.json`,JSON.stringify(results,null,2));console.log(JSON.stringify(results));
}finally{await browser?.close();await server?.close();await fs.unlink(routeFile);await fs.rmdir(routeDir);}
