import fs from 'node:fs/promises';
import {constants} from 'node:fs';
import assert from 'node:assert/strict';
import {createServer} from 'vite';
import {chromium} from '../logs/ui-image-26/node_modules/playwright/index.mjs';
const dir=new URL('../src/routes/__selection_reasoning/',import.meta.url),file=new URL('+page.svelte',dir);
let browser,server;const results=[];
await fs.mkdir(dir,{recursive:true});await fs.copyFile(new URL('./fixtures/selection-reasoning.svelte',import.meta.url),file,constants.COPYFILE_EXCL);
try{
 server=await createServer({plugins:[{name:'selection-sse-fixture',configureServer(server){server.middlewares.use((req,res,next)=>{
  if(!req.url?.startsWith('/__selection_sse'))return next();
  const kind=new URL(req.url,'http://localhost').searchParams.get('kind');
  res.setHeader('Content-Type','text/event-stream');res.setHeader('Access-Control-Allow-Origin','*');res.flushHeaders();
  const delta=kind==='structured'?{reasoning_content:'Private thought.\n'.repeat(30)}:{content:'<think>Private thought.\n'.repeat(1)};
  res.write('data: '+JSON.stringify({choices:[{delta}]})+'\n\n');
  const timer=setTimeout(()=>{res.end('data: '+JSON.stringify({choices:[{delta:{content:(kind==='structured'?'':'</think>')+'Answer.'}}]})+'\n\ndata: [DONE]\n\n');},1500);
  res.on('close',()=>clearTimeout(timer));
 });}}],server:{port:5188,strictPort:true,watch:{ignored:['**/logs/**','**/scripts/**','**/docs/**']}}});await server.listen();browser=await chromium.launch();
 const cases=[['plain',[{content:'Answer.'}]],['structured',[{reasoning_content:'Private thought.\n'.repeat(30)},{content:'Answer.'}]],['inline',[{content:'<thi'},{content:'nk>Private thought.'},{content:'</think>Answer.'}]],['harmony',[{content:'<|channel|>analysis<|message|>Private thought.'},{content:'<|channel|>final<|message|>Answer.'}]],['normalized',[{content:'<details type="reasoning" done="true">\n<summary>Thought</summary>\n\n> Private thought.\n</details>\n\nAnswer.'}]]];
 for(const viewport of [{width:1440,height:1000},{width:390,height:844}])for(const effort of [false,true])for(const action of ['ask','explain'])for(const [kind,deltas] of cases){
  const page=await browser.newPage({viewport});const errors=[],requests=[];page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/api/chat/completions',async route=>{requests.push(route.request().postDataJSON());await route.fulfill({contentType:'text/event-stream',body:deltas.map(delta=>'data: '+JSON.stringify({choices:[{delta}]})+'\n\n').join('')+'data: [DONE]\n\n'});});
  await page.goto('http://localhost:5188/__selection_reasoning',{waitUntil:'domcontentloaded',timeout:90000});await page.waitForFunction(()=>window.__selectionSetModel);await page.waitForTimeout(150);
  const id=effort?'local/gpt-oss-20b':'local/selection-test';await page.evaluate(id=>window.__selectionSetModel({id,name:id}),id);
  await page.locator('main p').first().evaluate(e=>{const r=document.createRange();r.selectNodeContents(e);getSelection().removeAllRanges();getSelection().addRange(r);e.dispatchEvent(new MouseEvent('mouseup',{bubbles:true}));});
  const menu=page.locator('#floating-buttons-selection-reasoning');await menu.waitFor({state:'visible'});
  await menu.locator('button').nth(action==='ask'?0:1).click();
  if(action==='ask'){await menu.locator('input').fill('Explain this');await menu.locator('input').press('Enter');}
  const response=menu.locator('[data-selection-response]');await response.waitFor();await page.waitForFunction(()=>document.querySelector('[data-selection-response]')?.textContent.includes('Answer.'));
  assert.equal(requests.length,1);assert.equal(requests[0].model,id);assert.equal(requests[0].params.reasoning_mode,'quick');assert.equal(requests[0].params.no_think,!effort);assert.equal(requests[0].params.reasoning_unlimited,false);
  assert.deepEqual(await page.evaluate(()=>window.__selectionPrepared),[id]);
  if(kind!=='plain'){
   const reasoning=response.locator('.reasoning-text');assert.equal(await reasoning.count(),1);
   const outside=await response.evaluate(e=>{const clone=e.cloneNode(true);clone.querySelectorAll('.reasoning-text').forEach(n=>n.remove());return clone.textContent;});assert(!outside.includes('Private thought'),'Reasoning leaked into answer');
   await response.locator('.reasoning-header').click();await page.waitForTimeout(180);
   assert((await reasoning.innerText()).includes('Private thought'));
  }
  assert.equal(await response.evaluate(e=>e.scrollWidth<=e.clientWidth+1),true,'Response overflowed horizontally');
  if(action==='explain'&&effort&&kind==='structured')await page.screenshot({path:`logs/selection-reasoning-${viewport.width}.png`});
  const addedButton=menu.getByRole('button',{name:/^(Adicionar|Add)$/});await addedButton.click();
  const added=JSON.parse(await page.locator('#selection-added').innerText());assert.equal(added.modelId,id);assert(added.messages[1].content.includes('Answer.'));
  if(kind!=='plain')assert(added.messages[1].content.includes('<details type="reasoning"'));
  assert.deepEqual(errors,[]);results.push({viewport,effort,action,kind});
  await page.close();
 }
 for(const viewport of [{width:1440,height:1000},{width:390,height:844}])for(const effort of [false,true])for(const kind of ['structured','inline']){
  const page=await browser.newPage({viewport});const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/api/chat/completions',r=>r.continue({url:`http://localhost:5188/__selection_sse?kind=${kind}`}));
  await page.goto('http://localhost:5188/__selection_reasoning',{waitUntil:'domcontentloaded',timeout:90000});await page.waitForFunction(()=>window.__selectionSetModel);
  await page.evaluate(effort=>window.__selectionSetModel({id:effort?'gpt-oss':'local/selection-test'}),effort);
  await page.locator('main p').first().evaluate(e=>{const r=document.createRange();r.selectNodeContents(e);getSelection().removeAllRanges();getSelection().addRange(r);e.dispatchEvent(new MouseEvent('mouseup',{bubbles:true}));});
  const menu=page.locator('#floating-buttons-selection-reasoning');await menu.waitFor({state:'visible'});await menu.locator('button').nth(1).click();
  const response=menu.locator('[data-selection-response]'),reason=response.locator('.reasoning-text');await reason.waitFor({state:'attached'});
  const closed=await reason.evaluate(e=>{const box=e.closest('[aria-hidden]');return{hidden:box.getAttribute('aria-hidden'),height:box.getBoundingClientRect().height};});
  assert.equal(closed.hidden,'true');assert(closed.height<=0.5,'Closed reasoning is not clipped');
  const liveOutside=await response.evaluate(e=>{const c=e.cloneNode(true);c.querySelectorAll('.reasoning-text').forEach(n=>n.remove());return c.textContent;});assert(!liveOutside.includes('Private thought'),'Live reasoning leaked outside block');
  await response.locator('.reasoning-header').click();await page.waitForTimeout(180);assert((await reason.evaluate(e=>e.closest('[aria-hidden]').getBoundingClientRect().height))>30);
  await page.waitForFunction(()=>document.querySelector('[data-selection-response]')?.textContent.includes('Answer.'));await page.waitForTimeout(200);
  assert.equal(await reason.evaluate(e=>e.closest('[aria-hidden]')?.getAttribute('aria-hidden')),'true','Completed reasoning did not close');
  const outside=await response.evaluate(e=>{const c=e.cloneNode(true);c.querySelectorAll('.reasoning-text').forEach(n=>n.remove());return c.textContent;});assert(!outside.includes('Private thought'));
  assert.deepEqual(errors,[]);results.push({viewport,effort,kind,live:true});await page.close();
 }
 await fs.writeFile('logs/selection-reasoning-visual.json',JSON.stringify(results,null,2));console.log('PASS',results.length,'selection cases');
}finally{await browser?.close();await server?.close();await fs.unlink(file);await fs.rmdir(dir);}
