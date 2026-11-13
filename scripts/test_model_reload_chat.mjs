import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {chromium} from '../logs/ui-image-26/node_modules/playwright/index.mjs';

const base='http://127.0.0.1:8080';
async function api(path,body){
 const r=await fetch(base+path,body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{});
 const data=await r.json();assert(r.ok,JSON.stringify(data));return data;
}
const original=(await api('/llamacpp/models/loaded')).models;
assert.deepEqual((await api('/api/tasks')).tasks,[]);
const model='local/Qwen3.5-9B-UD-Q4_K_XL', records=[], loads=[], errors=[];
const browser=await chromium.launch();
try{
 const page=await browser.newPage({viewport:{width:1440,height:1000}});
 await page.addInitScript(()=>{
  for(const [key,value] of Object.entries({llamacpp_load_context:'4096',llamacpp_load_vision:'no',llamacpp_cache_type:'q8_0',llamacpp_prioritize_gpu:'false',llamacpp_context_shift:'off',llamacpp_speculative_enabled:'false',llamacpp_speculative_method:'auto'}))localStorage.setItem(key,value);
 });
 page.on('pageerror',error=>errors.push(error.message));
 page.on('console',message=>{if(message.type()==='error')console.log('Browser:',message.text());});
 page.on('websocket',socket=>socket.on('framereceived',({payload})=>{
  if(typeof payload!=='string'||!payload.startsWith('42['))return;
  const event=JSON.parse(payload.slice(2))[1], record=records.find(value=>value.id===event?.message_id);
  if(record&&event.data?.type==='chat:completion'&&event.data.data.done){record.done=true;record.content=event.data.data.content;}
 }));
 await page.route('**/api/v1/chats/**',route=>route.request().method()==='GET'?route.continue():route.abort());
 await page.route('**/api/v1/users/user/settings/update',route=>route.fulfill({json:{}}));
 await page.route('**/llamacpp/models/load',route=>{loads.push(route.request().postDataJSON());console.log('Loading',JSON.stringify(loads.at(-1)));return route.continue();});
 await page.route('**/api/chat/completions',async route=>{
  const body=route.request().postDataJSON();assert(body.chat_id.startsWith('local:'));
  const loaded=(await api('/llamacpp/models/loaded')).models.find(item=>item.id===model);
  records.push({id:body.id,context:loaded?.n_ctx,cache:loaded?.cache_type});
  body.features={};body.tool_ids=[];body.tool_servers=[];body.files=[];
  body.params={...body.params,max_tokens:64,reasoning_mode:'quick',no_think:true};
  return route.continue({postData:JSON.stringify(body)});
 });
 await page.goto(base+'/?temporary-chat=true&models='+encodeURIComponent(model),{waitUntil:'networkidle'});
 console.log('Selected',await page.locator('#model-selector-0-button').innerText());
 async function done(index){
  const deadline=Date.now()+120000;
  while(!records[index]?.done&&Date.now()<deadline)await page.waitForTimeout(100);
  if(!records[index]?.done){await page.screenshot({path:'logs/model-reload-failure.png'});console.log('Page',await page.locator('body').innerText());}
  assert(records[index]?.done,JSON.stringify(records));
 }
 await page.locator('#chat-input').fill('Responda somente: um.');await page.locator('#send-message-button').click();await done(0);
 assert.equal(records[0].context,4096);
 // Use the same persisted preference consumed by the presets control.
 await page.evaluate(()=>{localStorage.setItem('llamacpp_load_context','8192');window.dispatchEvent(new Event('neve:response-speed-changed'));});
 await page.locator('.edit-user-message-button').first().evaluate(button=>button.click());
 await page.locator('textarea[id^="message-edit-"]').fill('Responda somente: dois.');
 await page.locator('#confirm-edit-message-button').click();await done(1);
 console.log('Edit profile before completion',JSON.stringify({records,loads}));
 await fs.writeFile('logs/model-reload-chat.json',JSON.stringify({records,loads,errors},null,2));
 assert.equal(records[1].context,8192,'Edited Send must reload the new context before generation');
 const count=loads.length;
 await page.locator('#chat-input').fill('Responda somente: tres.');await page.locator('#send-message-button').click();await done(2);
 assert.equal(records[2].context,8192);assert.equal(loads.length,count,'Unchanged profile must not reload');
 await page.evaluate(()=>{localStorage.setItem('llamacpp_load_context','16384');window.dispatchEvent(new Event('neve:response-speed-changed'));});
 await page.locator('#chat-input').fill('Responda somente: novo contexto.');await page.locator('#send-message-button').click();await done(3);
 assert.equal(records[3].context,16384);assert.equal(loads.length,count+1,'Composer Send must reload a changed context');
 await page.evaluate(()=>{localStorage.setItem('llamacpp_cache_type','q4_0');window.dispatchEvent(new Event('neve:response-speed-changed'));});
 await page.locator('.edit-user-message-button').last().evaluate(button=>button.click());
 await page.locator('textarea[id^="message-edit-"]').fill('Responda somente: quatro.');
 await page.locator('#confirm-edit-message-button').click();await done(4);
 assert.equal(records[4].cache,'q4_0');assert.equal(loads.length,count+2);
 assert.deepEqual(errors,[]);
 await fs.writeFile('logs/model-reload-chat.json',JSON.stringify({records,loads,errors},null,2));
 console.log('PASS real model: context/cache reload on edited Send; unchanged composer profile reused');
}finally{
 await browser.close();
 assert.deepEqual((await api('/api/tasks')).tasks,[]);
 if(original.length){
  const saved=original[0];
  await api('/llamacpp/models/load',{filename:saved.filename,n_gpu_layers:saved.n_gpu_layers,n_ctx:saved.context_auto?0:saved.n_ctx,mmproj_filename:saved.mmproj_filename,cache_type:saved.cache_type,speculative_decoding:saved.speculative_decoding,token_prediction:saved.token_prediction,context_shift:saved.context_shift,prioritize_gpu:saved.prioritize_gpu??false});
 }else{
  for(const loaded of (await api('/llamacpp/models/loaded')).models)await api('/llamacpp/models/unload',{model_id:loaded.id});
 }
}
