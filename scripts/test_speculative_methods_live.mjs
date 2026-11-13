import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {execFileSync} from 'node:child_process';
import {chromium} from '../logs/ui-image-26/node_modules/playwright/index.mjs';

const base='http://127.0.0.1:8080', model='local/Qwen3.5-9B-UD-Q4_K_XL';
const original={filename:'Qwen3.5-9B-UD-Q4_K_XL.gguf',n_ctx:16384,mmproj_filename:'',cache_type:'q8_0',n_gpu_layers:-1,prioritize_gpu:true,speculative_decoding:'off',token_prediction:'off',context_shift:'off'};
async function api(path,body){const r=await fetch(base+path,body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{});const text=await r.text();assert(r.ok,text);return JSON.parse(text);}
assert.deepEqual((await api('/api/tasks')).tasks,[]);
const records=[];
let browser;
try{
 for(const [name,prediction,speculative,expected] of [
  ['normal','off','off','off'],['ngram','off','high','ngram'],['mtp','on','off','mtp'],['auto_mtp','auto','off','mtp'],['auto_ngram','auto','off','ngram'],
 ]){
  const config={...original,token_prediction:prediction,speculative_decoding:speculative};
  if(name==='auto_ngram'){config.filename='GPT-OSS-20B-UD-Q4_K_XL.gguf';config.n_ctx=4096;}
  const start=performance.now(),loaded=await api('/llamacpp/models/load',config);
  assert.equal(loaded.speculative_method,expected);assert.equal(loaded.token_prediction,prediction);
  const cli=JSON.parse(execFileSync('backend/neveai/venv/Scripts/python.exe',['-c',`import psutil,json
out=[p.cmdline() for p in psutil.process_iter(['name']) if (p.info['name'] or '').lower()=='llama-server.exe']
print(json.dumps(out))`],{encoding:'utf8'}));
  const args=cli.find(args=>args.includes(config.filename)||args.some(arg=>arg.endsWith('\\'+config.filename)));
  assert(args,'Must locate this model runtime');
  if(expected==='off')assert(!args.includes('--spec-type'));
  else assert.equal(args[args.indexOf('--spec-type')+1],expected==='mtp'?'draft-mtp':'ngram-mod');
  const againStart=performance.now();await api('/llamacpp/models/load',config);const reusedMs=performance.now()-againStart;
  assert(reusedMs<1500,'Reopening the same profile must not reload the model');
  const payload={model:loaded.id,stream:false,messages:[{role:'user',content:'Return only these integers separated by commas: 1 to 30, in ascending order.'}],max_tokens:384,temperature:0,seed:42,chat_template_kwargs:expected==='ngram'&&name==='auto_ngram'?{reasoning_effort:'low'}:{enable_thinking:false},reasoning_effort:name==='auto_ngram'?'low':undefined};
  const r=await fetch('http://127.0.0.1:8281/v1/chat/completions',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
  const result=await r.json();assert(r.ok,JSON.stringify(result));assert.equal(result.choices[0].finish_reason,'stop');
  const content=result.choices[0].message.content;assert(content.includes('30'));assert(content.includes('1'));
  records.push({name,requested:prediction,effective:loaded.speculative_method,seconds:(performance.now()-start)/1000,reusedMs,finish:result.choices[0].finish_reason,content});
  console.log('PASS',name,expected,reusedMs.toFixed(1),'ms reuse');
 }
 browser=await chromium.launch();const page=await browser.newPage({viewport:{width:1440,height:1000}}),chatRecords=[],loadRequests=[],errors=[];
 await page.addInitScript(()=>{for(const [key,value] of Object.entries({llamacpp_load_context:'16384',llamacpp_load_vision:'no',llamacpp_cache_type:'q8_0',llamacpp_prioritize_gpu:'true',llamacpp_context_shift:'off',llamacpp_speculative_method:'auto',llamacpp_speculative_enabled:'true'}))localStorage.setItem(key,value)});
 page.on('pageerror',e=>errors.push(e.message));
 page.on('websocket',socket=>socket.on('framereceived',({payload})=>{
  if(typeof payload!=='string'||!payload.startsWith('42['))return;
  const event=JSON.parse(payload.slice(2))[1],record=chatRecords.find(r=>r.id===event?.message_id);
  if(record&&event.data?.type==='chat:completion'){
   if(event.data.data.content!=null)record.content=event.data.data.content;
   if(event.data.data.done){record.done=true;record.finish=event.data.data.finish_reason;}
  }
 }));
 await page.route('**/api/v1/chats/**',r=>r.request().method()==='GET'?r.continue():r.abort());
 await page.route('**/api/v1/users/user/settings/update',r=>r.fulfill({json:{}}));
 await page.route('**/llamacpp/models/load',r=>{const body=r.request().postDataJSON();loadRequests.push(body);assert.equal(body.token_prediction,'auto');return r.continue()});
 await page.route('**/api/chat/completions',r=>{const body=r.request().postDataJSON();assert(body.chat_id.startsWith('local:'));body.features={};body.files=[];body.tool_ids=[];body.tool_servers=[];body.params={...body.params,reasoning_mode:'quick',max_tokens:64};chatRecords.push({id:body.id});return r.continue({postData:JSON.stringify(body)})});
 await page.goto(base+'/?temporary-chat=true&models='+encodeURIComponent(model),{waitUntil:'networkidle',timeout:90000});await page.locator('#chat-input').waitFor();
 for(let i=0;i<2;i++){
  await page.locator('#chat-input').fill('Responda somente com a palavra Olá.');await page.locator('#send-message-button').click();
  const deadline=Date.now()+90000;while(!chatRecords[i]?.done&&Date.now()<deadline)await page.waitForTimeout(150);
  assert(chatRecords[i]?.done,JSON.stringify(chatRecords));assert.equal(chatRecords[i].finish,'stop');assert.match(chatRecords[i].content,/ol[aá]/i);
 }
 assert.equal(loadRequests.length,1,'Auto must not reload the model on every message');assert.deepEqual(errors,[]);
 await fs.writeFile('logs/speculative-live.json',JSON.stringify({native:records,chat:chatRecords,loadRequests},null,2));
 console.log('PASS actual chat Auto, two messages, one model load');
}finally{
 await browser?.close();
 assert.deepEqual((await api('/api/tasks')).tasks,[]);
 await api('/llamacpp/models/load',original);
}
