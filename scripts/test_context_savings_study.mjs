import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {createServer} from 'vite';
import {chromium} from '../logs/ui-image-26/node_modules/playwright/index.mjs';
import {installMobileOfflineApi} from './fixtures/mobile-offline-api.mjs';

// Study only: production request construction is exercised; no real completion is sent.
const hook=String.raw`onMount(()=>{window.__contextSavings={async request(){
 cancelGenerationAnchorRAF();releaseGeneratingMessageAnchor();cancelMessagesBottomWheelLock();
 temporaryChatEnabled.set(true);chatId.set('local:context-savings');loading=false;loadedChatViewportReady=true;deferLoadedChatMessages=false;selectedModels=['local/mobile-fixture'];taskIds=[];autoScroll=false;
 params={system:'Preserve all user instructions.'};
 const entries=[['u1','user','Responda sempre em portugues. Preserve acessibilidade.'],['a1','assistant','Original implementation.\n'+ '\x60\x60\x60js\\nconst originalColor = "MAGENTA_OLD_VERSION_873";\\nfunction price(){return 37;}\\n\x60\x60\x60'.replaceAll('\\n','\n')],['u2','user','Troque a cor por azul e mantenha o preco.'],['a2','assistant','Current implementation.\n'+ '\x60\x60\x60js\\nconst currentColor = "blue";\\nfunction price(){return 37;}\\n\x60\x60\x60'.replaceAll('\\n','\n')],['u3','user','Qual era o valor literal da cor na primeira versao? Depois restaure aquela versao.']];
 const messages={};for(let i=0;i<entries.length;i++){const [id,role,content]=entries[i];messages[id]={id,role,content,parentId:entries[i-1]?.[0]??null,childrenIds:[entries[i+1]?.[0]??'pending'],done:true,timestamp:1700000000+i};}
 messages.other={id:'other',role:'assistant',content:'INACTIVE_BRANCH_MUST_NOT_BE_SENT',parentId:'u1',done:true,childrenIds:[]};
 messages.pending={id:'pending',role:'assistant',content:'',done:false,parentId:'u3',childrenIds:[],model:'local/mobile-fixture'};
 history={currentId:'pending',messages};await tick();
 await sendMessageSocket({id:'local/mobile-fixture',name:'Fixture',info:{meta:{}}},createMessagesList(history,'u3'),history,'pending',$chatId,{});
 },state(){return history}};return()=>delete window.__contextSavings;});`;
let server,browser,page;
const results=[];
try{
 server=await createServer({plugins:[{name:'context-savings-study',enforce:'pre',async load(id){if(id.endsWith('/src/lib/components/chat/Chat.svelte'))return(await fs.readFile(id,'utf8')).replace('const waitForChatSocketReady = async (): Promise<string> => {','const waitForChatSocketReady = async (): Promise<string> => { return "fixture-socket";').replace('</script>',hook+'\n</script>')}}],server:{port:5197,strictPort:true,watch:{ignored:['**/logs/**','**/scripts/**','**/docs/**']}}});
 await server.listen();browser=await chromium.launch();
 for(const width of [1440,390]){
  page=await browser.newPage({viewport:{width,height:1000}});await installMobileOfflineApi(page);
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  let payload;
  await page.route('**/api/chat/completions',route=>{payload=route.request().postDataJSON();assert(payload.chat_id.startsWith('local:'));return route.fulfill({json:{task_id:'fixture-only'}})});
  await page.goto('http://localhost:5197',{waitUntil:'networkidle',timeout:90000});await page.waitForFunction(()=>window.__contextSavings);
  await page.evaluate(()=>window.__contextSavings.request());
  assert.equal(payload.params.context_compaction,false);
  await page.evaluate(async()=>{localStorage.setItem('llamacpp_context_compaction','true');await window.__contextSavings.request()});
  assert.equal(payload.params.context_compaction,true);
  assert(payload);const original=payload.messages;
  assert.equal(original[0].role,'system');assert.equal(original.filter(m=>m.role==='assistant').length,2);
  assert(original.some(m=>m.content.includes('MAGENTA_OLD_VERSION_873')));
  assert(!original.some(m=>m.content.includes('INACTIVE_BRANCH_MUST_NOT_BE_SENT')));
  const latest=original.findLast(m=>m.role==='assistant');
  const latestOnly=original.filter(m=>m.role!=='assistant'||m===latest);
  assert(latestOnly.some(m=>m.content.includes('Preserve acessibilidade')));
  assert(!latestOnly.some(m=>m.content.includes('MAGENTA_OLD_VERSION_873')),'Latest-only loses information explicitly requested by the new turn');
  const rolling=[original[0],...original.slice(-2)];
  assert(!rolling.some(m=>m.content.includes('Preserve acessibilidade')),'Dropping old turns also removes persistent instructions');
  const code='return `first\nsecond`;';
  assert.notEqual(Function(code)(),Function(code.replace(/\s+/g,' '))(),'Whitespace compaction can change code data');
  assert.deepEqual(errors,[]);
  await page.screenshot({path:`logs/context-savings-study-${width}.png`});
  results.push({width,actual_request_constructed:true,active_branch_only:true,no_duplicate_assistant_serialization:true,latest_only_characters_saved:JSON.stringify(original).length-JSON.stringify(latestOnly).length,latest_only_loses_requested_original:true,rolling_loses_standing_instruction:true,whitespace_changes_program_data:true,inference_performed:false,production_changed:false});
  console.log('PASS',width);await page.close();
 }
 await fs.writeFile('logs/context-savings-study.json',JSON.stringify(results,null,2));
}catch(error){await page?.screenshot({path:'logs/context-savings-study-failed.png'});throw error}finally{await browser?.close();await server?.close()}
