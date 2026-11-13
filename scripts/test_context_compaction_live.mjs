import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {execFileSync} from 'node:child_process';
import {chromium} from '../logs/ui-image-26/node_modules/playwright/index.mjs';

const base='http://127.0.0.1:8080', model='local/Qwen3.5-9B-UD-Q4_K_XL';
const config={filename:'Qwen3.5-9B-UD-Q4_K_XL.gguf',n_ctx:16384,mmproj_filename:'',cache_type:'q8_0',n_gpu_layers:-1,prioritize_gpu:true,speculative_decoding:'off',token_prediction:'off'};
async function request(path,body){const r=await fetch(base+path,body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{});const text=await r.text();assert(r.ok,text);return JSON.parse(text);}
const original=await request('/llamacpp/models/loaded');
assert(original.models.length===1&&original.models[0].id===model,'Run after loading only the authorized test model');
assert.deepEqual((await request('/api/tasks')).tasks,[]);
const chatsBefore=await request('/api/v1/chats/');
const records=[],errors=[];
const saved = process.argv.includes('--saved');
let browser,page,active;
try{
 let repeat=100,messages;
 async function count(items){
  const template=await fetch('http://127.0.0.1:8281/apply-template',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({messages:items,add_generation_prompt:true,chat_template_kwargs:{enable_thinking:false}})}).then(r=>r.json());
  const tokens=await fetch('http://127.0.0.1:8281/tokenize',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({content:template.prompt,add_special:true,parse_special:true})}).then(r=>r.json());return tokens.tokens.length;
 }
 for(let attempt=0;attempt<3;attempt++){
  messages=[{role:'system',content:'Responda em português, de forma breve. Mantenha as instruções e valores literais.'}];
  for(let i=0;i<5;i++)messages.push(
   {role:'user',content:i===0?'Defina uma cor literal e um preço. Preserve acessibilidade e responda sempre em português.':`Revise a implementação, etapa ${i}. Preserve os requisitos anteriores.`},
   {role:'assistant',content:(i===0?'Defini a cor literal MAGENTA_873 e o preço 37.\n':'')+(`Etapa ${i}: implementação responsiva com contraste acessível; componentes, botão Salvar e layout móvel preservados sem alterar os valores anteriores.\n`).repeat(repeat)}
  );
  messages.push({role:'user',content:'Qual era a cor literal original e o preço? Diga também o idioma e o requisito de acessibilidade. Responda em uma frase.'});
  const n=await count(messages);if(n>=11800&&n<=13500)break;repeat=Math.round(repeat*12500/n);
 }
 if(saved)messages=JSON.parse(execFileSync('backend/neveai/venv/Scripts/python.exe',['-c',`import sqlite3,json
c=sqlite3.connect('file:backend/data/neve.db?mode=ro',uri=True)
d=json.loads(c.execute('SELECT chat FROM chat WHERE id=?',('57e88c8b-5cf0-475f-916e-d46ef0e76c6e',)).fetchone()[0])
m=d['history']['messages']; p=m[d['history']['currentId']]['parentId']; out=[]
while p:
 x=m[p];out.append({'role':x['role'],'content':x['content']});p=x.get('parentId')
print(json.dumps(out[::-1]))`],{encoding:'utf8'}));
 const nativeCount=await count(messages);assert(nativeCount>=11469&&nativeCount<14000,nativeCount);
 browser=await chromium.launch();page=await browser.newPage({viewport:{width:1440,height:1000}});
 await page.addInitScript(()=>{localStorage.setItem('neveai.language','pt-BR');for(const [k,v] of Object.entries({llamacpp_load_context:'16384',llamacpp_load_vision:'no',llamacpp_cache_type:'q8_0',llamacpp_prioritize_gpu:'true',llamacpp_speculative_decoding:'off',llamacpp_context_shift:'off'}))localStorage.setItem(k,v)});
 page.on('pageerror',e=>errors.push(e.message));
 page.on('websocket',s=>s.on('framereceived',({payload})=>{
  if(typeof payload!=='string'||!payload.startsWith('42['))return;
  const e=JSON.parse(payload.slice(2))[1];if(e?.message_id!==active?.id||e.data?.type!=='chat:completion')return;
  const d=e.data.data;if(d.usage)active.usage=d.usage;if(d.content!=null)active.content=d.content;
  if(d.done){active.done=true;active.finish_reason=d.finish_reason;active.seconds=(Date.now()-active.start)/1000;}
 }));
 await page.route('**/api/v1/chats/**',r=>r.request().method()==='GET'?r.continue():r.abort());
 await page.route('**/api/v1/users/user/settings/update',r=>r.fulfill({json:{}}));
 await page.route('**/api/chat/completions',async r=>{
  const body=r.request().postDataJSON();assert(body.chat_id.startsWith('local:'));
  active.id=body.id;body.model=model;body.messages=messages;body.features={};body.files=[];body.tool_ids=[];body.tool_servers=[];
  body.params={...body.params,context_compaction:active.enabled,temperature:saved?0.4:0,seed:42,max_tokens:saved?-1:128,reasoning_mode:'quick'};
  return r.continue({postData:JSON.stringify(body)});
 });
 await page.goto(base+'/?temporary-chat=true&models='+encodeURIComponent(model),{waitUntil:'networkidle',timeout:90000});
 await page.locator('#chat-input').waitFor();
 for(const shift of saved?['off']:['off','on']){
  await request('/llamacpp/models/load',{...config,context_shift:shift});
  for(const enabled of saved?[false,true]:[false,true,true,false]){
   active={shift,enabled,start:Date.now(),nativeCount};records.push(active);
   await page.locator('#chat-input').fill(`Temporary context compaction test ${records.length}`);
   await page.locator('#send-message-button').click();
   const deadline=Date.now()+120000;
   while(!active.done&&Date.now()<deadline)await page.waitForTimeout(150);
   assert(active.done,JSON.stringify(active));
   if(saved){
    assert.equal(active.finish_reason,enabled?'stop':'length');
    if(enabled)assert.match(active.content,/<\/html>\s*\n```/i);
   }else{
    assert.equal(active.finish_reason,'stop');
    assert.match(active.content,/MAGENTA_873/);assert.match(active.content,/37/);assert.match(active.content,/portugu[eê]s/i);assert.match(active.content,/acess/i);
   }
   const input=active.usage.input_tokens;
   assert(Number.isFinite(input),JSON.stringify(active.usage));
   if(enabled)assert(input<nativeCount*(saved?.9:.65),`Expected actual savings, got ${input}/${nativeCount}`);
   else assert(Math.abs(input-nativeCount)<32,`Disabled must send full transcript: ${input}/${nativeCount}`);
   console.log('PASS',shift,enabled,input,'of',nativeCount,active.seconds,'s');
  }
 }
 assert.deepEqual(errors,[]);assert.deepEqual(await request('/api/v1/chats/'),chatsBefore);
 await page.screenshot({path:`logs/context-compaction-live${saved?'-code':''}.png`});
 await fs.writeFile(`logs/context-compaction-live${saved?'-code':''}.json`,JSON.stringify(records,null,2));
}catch(e){console.log('STATE',records);await page?.screenshot({path:'logs/context-compaction-live-failed.png'});throw e}
finally{
 await browser?.close();
 assert.deepEqual((await request('/api/tasks')).tasks,[]);
 await request('/llamacpp/models/load',{...config,context_shift:original.models[0].context_shift});
}
