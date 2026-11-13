import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {execFileSync} from 'node:child_process';
import {chromium} from '../logs/ui-image-26/node_modules/playwright/index.mjs';

const base='http://127.0.0.1:8080';
const data=JSON.parse(execFileSync('backend/neveai/venv/Scripts/python.exe',['-c',`import sqlite3,json
c=sqlite3.connect('file:backend/data/neve.db?mode=ro',uri=True)
d=json.loads(c.execute('SELECT chat FROM chat WHERE id=?',('57e88c8b-5cf0-475f-916e-d46ef0e76c6e',)).fetchone()[0])
m=d['history']['messages']; last=m[d['history']['currentId']]; p=last['parentId']; out=[]
while p:
 x=m[p];out.append({'role':x['role'],'content':x['content']});p=x.get('parentId')
print(json.dumps({'model':last['model'],'messages':out[::-1]}))`],{encoding:'utf8'}));
const records=[],errors=[],ownTasks=new Set();
let browser,page;
try{
 assert.deepEqual((await(await fetch(base+'/api/tasks')).json()).tasks,[]);
 const chatsBefore=await(await fetch(base+'/api/v1/chats/')).json();
 browser=await chromium.launch();page=await browser.newPage({viewport:{width:1440,height:1000}});
 await page.addInitScript(()=>{
  for(const [key,value] of Object.entries({'neveai.language':'pt-BR','llamacpp_load_context':'16384','llamacpp_load_vision':'no','llamacpp_cache_type':'q8_0','llamacpp_prioritize_gpu':'true','llamacpp_speculative_decoding':'off','llamacpp_context_shift':'off','neveai.responseSpeed':'normal'}))localStorage.setItem(key,value);
 });
 await page.route('**/llamacpp/models/load',route=>{
  const request=route.request().postDataJSON();
  assert.equal(request.n_ctx,16384);assert.equal(request.cache_type,'q8_0');assert.equal(request.prioritize_gpu,true);assert(!request.mmproj_filename);
  return route.continue();
 });
 page.on('pageerror',error=>errors.push(error.message));
 page.on('websocket',socket=>socket.on('framereceived',({payload})=>{
  if(typeof payload!=='string'||!payload.startsWith('42['))return;
  const event=JSON.parse(payload.slice(2))[1];
  const record=records.find(item=>item.id===event?.message_id);
  if(!record||event.data?.type!=='chat:completion')return;
  const value=event.data.data;
  if(value.usage)record.usage=value.usage;
  if(value.content!=null)record.content=value.content;
  if(value.done){record.done=true;record.finish_reason=value.finish_reason;record.seconds=(Date.now()-record.start)/1000;}
 }));
 await page.route('**/api/v1/chats/**',route=>route.request().method()==='GET'?route.continue():route.abort());
 await page.route('**/api/chat/completions',async route=>{
  const body=route.request().postDataJSON();assert(body.chat_id.startsWith('local:'));
  const index=records.length;
  body.messages=index===2?[data.messages[0],...data.messages.slice(-2)]:data.messages;
  body.model=data.model;body.features={};body.files=[];body.tool_ids=[];body.tool_servers=[];
  body.params={...body.params,temperature:0.4,min_p:0.1,seed:42,max_tokens:index===0?1:-1,reasoning_mode:'quick'};
  records.push({id:body.id,case:['warmup','cached_full_context','headroom'][index],start:Date.now()});
  await route.continue({postData:JSON.stringify(body)});
 });
 page.on('response',async response=>{if(response.url().endsWith('/api/chat/completions')){try{const value=await response.json();if(value.task_id)ownTasks.add(value.task_id)}catch{}}});
 await page.goto(base+'/?temporary-chat=true&models='+encodeURIComponent(data.model),{waitUntil:'networkidle',timeout:90000});
 await page.locator('#chat-input').waitFor();assert(page.url().includes('temporary-chat=true'));
 for(let index=0;index<3;index++){
  await page.locator('#chat-input').fill('Temporary context validation '+index);
  await page.locator('#send-message-button').click();
  const deadline=Date.now()+180000;
  while(!records[index]?.done&&Date.now()<deadline)await page.waitForTimeout(200);
  assert(records[index]?.done,'Generation must terminate with its metadata');
  const record=records[index];
  const nativeTotal=(record.usage?.cache_n??0)+(record.usage?.prompt_n??0)+(record.usage?.predicted_n??0);
  assert.equal(record.usage.total_tokens,nativeTotal);
  if(index===1){
   assert(record.usage.cache_n>0,'The reproduction must actually reuse a KV prefix');
   assert.equal(record.finish_reason,'length');
   assert.equal(record.usage.total_tokens,record.usage.context_window);
   await page.locator('[data-token-usage-trigger]').hover();
   assert((await page.locator('[data-token-usage-popup]').innerText()).includes('100.0%'));
   await page.screenshot({path:'logs/context-cache-live-full.png'});
   await page.mouse.move(1,1);
  }
  if(index===2){
   assert.equal(record.finish_reason,'stop');
   assert(record.usage.total_tokens<record.usage.context_window);
   assert(/<\/html>\s*\n```/i.test(record.content),'A comparable edit with headroom must finish its code block');
   await page.screenshot({path:'logs/context-cache-live-complete.png'});
  }
  console.log('PASS',record.case,record.finish_reason,record.usage.total_tokens,record.seconds);
 }
 assert.deepEqual(errors,[]);
 const chatsAfter=await(await fetch(base+'/api/v1/chats/')).json();assert.deepEqual(chatsAfter,chatsBefore,'No saved chats may be changed');
 const loaded=await(await fetch(base+'/llamacpp/models/loaded')).json();
 const model=loaded.models.find(item=>item.id===data.model);assert.equal(model.n_ctx,16384);assert.equal(model.cache_type,'q8_0');assert.equal(model.prioritize_gpu,true);assert(!model.mmproj_filename);
 await fs.writeFile('logs/context-cache-live-results.json',JSON.stringify(records.map(({content,...value})=>({...value,characters:content?.length})),null,2));
}catch(error){console.log('STATE',records.map(({content,...value})=>value));await page?.screenshot({path:'logs/context-cache-live-failed.png'});throw error}
finally{
 for(const id of ownTasks)await fetch(base+'/api/tasks/stop/'+id,{method:'POST'}).catch(()=>{});
 await browser?.close();
}
