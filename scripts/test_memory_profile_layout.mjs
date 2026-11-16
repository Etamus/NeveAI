import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import { constants } from 'node:fs';
import { createServer } from 'vite';
import { chromium } from '../logs/ui-image-26/node_modules/playwright/index.mjs';
import { installMobileOfflineApi } from './fixtures/mobile-offline-api.mjs';

const directory=new URL('../src/routes/__memory_profile_layout/',import.meta.url),file=new URL('+page.svelte',directory),output='logs/memory-profile-layout';
let server,browser,page;
await fs.mkdir(directory,{recursive:true});
await fs.copyFile(new URL('./fixtures/memory-profile-layout.svelte',import.meta.url),file,constants.COPYFILE_EXCL);
try{
 await fs.mkdir(output,{recursive:true});
 server=await createServer({cacheDir:'node_modules/.vite-memory-profile-layout',plugins:[{name:'memory-profile-offline',configResolved(config){config.server.proxy=undefined;}}],server:{port:5196,strictPort:true,watch:{ignored:['**/logs/**','**/scripts/**']}}});
 await server.listen();browser=await chromium.launch();
 for(const width of [1440,390])for(const theme of ['dark','light']){
  page=await browser.newPage({viewport:{width,height:900}});page.setDefaultTimeout(15000);const errors=[];
  page.on('pageerror',error=>errors.push(error.message));await installMobileOfflineApi(page);
  let memories=Array.from({length:35},(_,i)=>({id:'memory-'+i,content:`Memory ${String(i).padStart(2,'0')} with a long user preference to check clipping`,updated_at:1700000000+i})),deletes=0,clears=0,adds=0,updates=0;
  await page.route('**/api/v1/memories/**',async route=>{
   const path=new URL(route.request().url()).pathname,method=route.request().method();
   if(method==='GET')return route.fulfill({json:memories});
   if(method==='DELETE'){
    if(path.endsWith('/delete/user')){clears++;memories=[];}else{deletes++;memories=memories.filter(row=>!path.endsWith('/'+row.id));}
    return route.fulfill({json:true});
   }
   const content=route.request().postDataJSON().content;
   if(path.endsWith('/add')){const row={id:'new',content,updated_at:1700000050};adds++;memories.push(row);return route.fulfill({json:row});}
   const id=path.split('/').at(-2);updates++;const row=memories.find(row=>row.id===id);row.content=content;return route.fulfill({json:row});
  });
  await page.goto('http://localhost:5196/__memory_profile_layout',{waitUntil:'networkidle'});
  await page.waitForFunction(()=>window.__smallUI);
  await page.evaluate(theme=>{document.documentElement.classList.toggle('dark',theme==='dark');document.documentElement.classList.toggle('light',theme==='light');},theme);
  await page.evaluate(()=>window.__smallUI.memories());
  const manager=page.locator('[data-memory-manager]'),body=manager.locator('[data-memory-list-body]'),header=manager.locator('[data-memory-list-header]');await body.waitFor();
  const clear=manager.getByRole('button',{name:'Limpar',exact:true}),add=manager.getByRole('button',{name:'Adicionar',exact:true});
  await page.waitForTimeout(350);
  assert(await manager.evaluate(el=>document.activeElement===el),'opening focuses modal content, not Clear');
  assert.equal(await page.locator('[data-tippy-root]:visible').filter({hasText:'Limpar'}).count(),0,'Clear tooltip does not appear on open');
  await page.keyboard.press('Tab');
  if(width>=768)assert(await clear.evaluate(el=>document.activeElement===el),'Clear remains keyboard reachable');
  await manager.focus();
  assert((await clear.boundingBox()).x<(await add.boundingBox()).x,'add is right of clear');
  for(const button of [clear,add])assert.equal(await button.innerText(),'','icon-only memory actions');
  assert(await body.evaluate(el=>el.scrollHeight>el.clientHeight));
  const before=await header.boundingBox(),scroll=await body.boundingBox();assert(scroll.y>=before.y+before.height,'scroll starts below header');
  const columns=await manager.evaluate(el=>{const head=[...el.querySelectorAll('thead th')].filter(el=>getComputedStyle(el).display!=='none'),cells=[...el.querySelectorAll('tbody tr:first-child td')].filter(el=>getComputedStyle(el).display!=='none');return head.map((cell,i)=>Math.abs(cell.getBoundingClientRect().x-cells[i].getBoundingClientRect().x));});
  assert(columns.every(offset=>offset<1),'header aligns with rows');
  await body.hover();await page.mouse.wheel(0,1500);await page.waitForTimeout(120);
  assert.equal((await header.boundingBox()).y,before.y,'header fixed during wheel scroll');
  await body.evaluate(el=>el.scrollTop=el.scrollHeight);
  const last=await body.locator('tr').last().boundingBox();assert(last.y+last.height<=scroll.y+scroll.height+1,'last row fully visible');
  await page.screenshot({path:`${output}/${width}-${theme}-memory.png`});
  await body.evaluate(el=>el.scrollTop=0);
  await body.locator('tr').first().getByRole('button',{name:'Delete',exact:true}).click();
  await page.getByRole('button',{name:'Cancel',exact:true}).last().click();assert.equal(deletes,0);
  await body.locator('tr').first().getByRole('button',{name:'Delete',exact:true}).click();
  await page.getByRole('button',{name:'Delete',exact:true}).last().click();await page.waitForFunction(()=>!document.querySelector('[data-memory-list-body]')?.textContent.includes('Memory 00'));assert.equal(deletes,1);
  await body.locator('tr').first().getByRole('button',{name:'Edit',exact:true}).click();
  const edit=page.locator('.modal[aria-hidden="false"]').last();await edit.locator('textarea').fill('Updated preference');await edit.getByRole('button',{name:'Update',exact:true}).click();await body.getByRole('cell',{name:'Updated preference',exact:true}).waitFor();assert.equal(updates,1);
  await add.click();const adding=page.locator('.modal[aria-hidden="false"]').last();await adding.locator('textarea').fill('New preference');await adding.getByRole('button',{name:'Add',exact:true}).click();await body.getByRole('cell',{name:'New preference',exact:true}).waitFor();assert.equal(adds,1);
  await clear.click();await page.getByRole('button',{name:'Cancel',exact:true}).last().click();assert.equal(clears,0);
  await clear.click();await page.getByRole('button',{name:'Confirm',exact:true}).last().click();await manager.getByText('Memories accessible by LLMs will be shown here.',{exact:true}).waitFor();assert.equal(clears,1);
  await page.evaluate(()=>window.__smallUI.close());
  await page.evaluate(()=>window.__smallUI.profile());const profile=page.locator('.modal[aria-hidden="false"]').last();const name=profile.getByRole('textbox',{name:'Nome de usuário',exact:true});await name.waitFor();assert.equal(await name.inputValue(),'Test person');assert.equal(await profile.getByText('Nome de usuário',{exact:true}).count(),0);await name.fill('Edited name');assert.equal(await name.inputValue(),'Edited name');await page.screenshot({path:`${output}/${width}-${theme}-profile.png`});
  await page.evaluate(()=>window.__smallUI.close());await page.evaluate(()=>window.__smallUI.project());const project=page.locator('.modal[aria-hidden="false"]').last();const projectName=project.getByRole('textbox',{name:'Nome do projeto',exact:true});await projectName.waitFor();assert.equal(await project.getByText('Nome do projeto',{exact:true}).count(),0);await projectName.fill('Fixture project');await page.screenshot({path:`${output}/${width}-${theme}-project.png`});await project.getByRole('button',{name:'Criar',exact:true}).click();await page.waitForFunction(()=>window.__projectSubmit?.name==='Fixture project');
  assert.deepEqual(errors,[]);await page.close();console.log(`PASS ${width} ${theme}: memory header, actions and CRUD; profile/project fields`);
 }
}catch(error){await page?.screenshot({path:`${output}/failed.png`});throw error;}finally{await browser?.close();await server?.close();await fs.rm(file,{force:true});await fs.rmdir(directory).catch(()=>{});}
