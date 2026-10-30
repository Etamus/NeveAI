import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
import {createServer} from 'vite';
import {chromium} from '../logs/ui-image-26/node_modules/playwright/index.mjs';
const hook=`
onMount(()=>{
 window.__liveContinuation={async seed(value,model){
  cancelGenerationAnchorRAF();releaseGeneratingMessageAnchor();cancelMessagesBottomWheelLock();
  temporaryChatEnabled.set(true);chatId.set('local:'+$socket.id);await tick();
  await new Promise(resolve=>setTimeout(resolve,500));
  loading=false;loadedChatViewportReady=true;deferLoadedChatMessages=false;
  history=value;selectedModels=[model];taskIds=[];autoScroll=false;
  params={...params,max_tokens:1536,temperature:0.2};thinkingEnabled=true;thinkingExtendedEnabled=false;thinkingUnlimitedEnabled=false;
  await tick();await waitForLayout(4);messagesContainerElement.scrollTop=messagesContainerElement.scrollHeight;await waitForLayout(2);
 },start:()=>continueResponse(),state(){const m=history.messages[history.currentId];const root=document.querySelector('#message-'+m.id+' #response-content-container');const copy=root?.cloneNode(true);copy?.querySelectorAll('.reasoning-text').forEach(e=>e.remove());const outside=copy?.textContent??'';return{done:m.done,content:m.content,output:m.output,error:m.error,leaked:/<details\\b|<summary>|&gt;|Thinking Process:/.test(outside),outside:outside.slice(-1600),highlights:CSS.highlights?.size??0,top:messagesContainerElement.scrollTop,spacer:generationBottomSpacerHeight};}
 };return()=>delete window.__liveContinuation;
});`;
let server,browser;const results=[];
try{
 const active=await(await fetch('http://localhost:8080/api/tasks')).json();assert.equal(active.tasks.length,0,'Wait for the user generation to finish');
 const loaded=await(await fetch('http://localhost:8080/llamacpp/models/loaded')).json();assert.equal(loaded.models.length,1);const model=loaded.models[0].id;
 const chatId=process.env.LIVE_CHAT??'c7e7801e-c017-4961-8d2b-c13848330d2b';
 const chat=await(await fetch('http://localhost:8080/api/v1/chats/'+chatId)).json();
 const savedOriginal=JSON.stringify(chat);
 server=await createServer({plugins:[{name:'real-continue-audit',enforce:'pre',async load(id){if(id.endsWith('/src/lib/components/chat/Chat.svelte'))return(await fs.readFile(id,'utf8')).replace('if (!(await ensureLocalModelsReady([model.id]))) {','if (false) {').replace('</script>',hook+'\n</script>');}}],server:{port:5188,strictPort:true,proxy:{'/ws':{target:'http://localhost:8080',ws:true,changeOrigin:true,rewriteWsOrigin:true}},watch:{ignored:['**/logs/**','**/scripts/**','**/docs/**']}}});await server.listen();
 browser=await chromium.launch({ignoreDefaultArgs:['--hide-scrollbars']});const page=await browser.newPage({viewport:{width:process.env.LIVE_MOBILE?390:1440,height:process.env.LIVE_MOBILE?844:1000},recordVideo:{dir:'logs/live-chat-recordings',size:{width:1440,height:1000}}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
 // Safety net: only temporary completion traffic can mutate state during this test.
 await page.route('**/api/v1/chats/**',r=>r.request().method()==='GET'?r.continue():r.abort());
 await page.route('**/api/chat/completions',async route=>{const body=route.request().postDataJSON();assert(body.chat_id.startsWith('local:'));body.params={...body.params,max_tokens:1536,reasoning_mode:'reasoning',reasoning_extended:false,reasoning_unlimited:false,no_think:false};await route.continue({postData:JSON.stringify(body)});});
 await page.goto('http://localhost:5188',{waitUntil:'networkidle',timeout:90000});await page.waitForFunction(()=>window.__liveContinuation);await page.evaluate(()=>document.fonts.ready);
 if(process.env.LIVE_DARK)await page.evaluate(()=>document.documentElement.classList.add('dark'));
 const value=chat.chat.history;if(process.env.LIVE_TARGET)value.currentId=process.env.LIVE_TARGET;
 if(process.env.LIVE_ARCHIVED){const old=JSON.parse(await fs.readFile('logs/live-continue-ui-before.json','utf8')).before;value.messages[value.currentId].content=old.content;value.messages[value.currentId].output=old.output;}
 if(process.env.LIVE_CLEAN_PREFIX){const m=value.messages[value.currentId];m.content=m.content.slice(0,m.content.indexOf('<details type="reasoning" done="false">'));}
 await page.evaluate(({value,model})=>window.__liveContinuation.seed(value,model),{value,model});
 await page.locator('#message-'+value.currentId).waitFor({state:'visible',timeout:30000});
 const before=await page.evaluate(()=>window.__liveContinuation.state());await page.screenshot({path:'logs/live-continue-before.png'});assert(!before.leaked,'Saved content already leaks reasoning');
 await page.locator('#messages-container').hover();await page.evaluate(()=>window.__liveContinuation.start());
 for(let i=0;i<1200;i++){await page.mouse.wheel(0,180);await page.waitForTimeout(20);const state=await page.evaluate(()=>window.__liveContinuation.state());if(state.leaked&&!results.some(f=>f.leaked))await page.screenshot({path:'logs/live-reasoning-leak.png'});results.push({at:Date.now(),...state});if(state.done&&i>3)break;}
 await page.waitForTimeout(300);
 const after=await page.evaluate(()=>window.__liveContinuation.state());results.push({at:Date.now(),...after});await page.screenshot({path:'logs/live-continue-after.png'});
 const previousOutput=new Map(),regressions=[];
 for(const [index,frame] of results.entries())for(const [itemIndex,item]of(frame.output??[]).entries())if(item.type==='message'){
  const text=item.content.map(part=>part.text??'').join(''),key=item.id??itemIndex,previous=previousOutput.get(key);
  if(previous&&!text.startsWith(previous))regressions.push({index,key,previous,text});previousOutput.set(key,text);
 }
 const visibleAnswer=await page.locator('#message-'+value.currentId+' #response-content-container p').last().evaluate(e=>{const r=e.getBoundingClientRect(),v=document.querySelector('#messages-container').getBoundingClientRect(),c=document.querySelector('#message-input-container').getBoundingClientRect();return{top:r.top,bottom:r.bottom,visibleTop:v.top,visibleBottom:Math.min(v.bottom,c.top)};});
 await fs.writeFile(process.env.LIVE_RESULT??'logs/live-continue-ui.json',JSON.stringify({model,before,after,errors,regressions,frames:results},null,2));
 console.log(JSON.stringify({model,before:before.content.length,after:after.content.length,error:after.error,done:after.done,leakedFrames:results.filter(f=>f.leaked).length,errors}));
 assert.equal(JSON.stringify(await(await fetch('http://localhost:8080/api/v1/chats/'+chatId)).json()),savedOriginal,'The saved chat changed');
 if(process.env.LIVE_ASSERT)assert(results.every(frame=>!frame.leaked),'Reasoning leaked outside its block DURING streaming');
 if(process.env.LIVE_ASSERT)assert.deepEqual(regressions,[],'Provider message content regressed');
 if(process.env.LIVE_ASSERT){assert(after.done);assert(!after.error);assert(after.content.length>before.content.length+80,'The real model did not continue');assert(after.output.slice(before.output.length).some(item=>item.type==='message'&&item.content.some(part=>(part.text??'').length>80)),'Only reasoning was generated, without a visible answer');assert(results.every(frame=>frame.highlights===0),'Transparent text remained while forcing downward scrolling');assert.deepEqual(errors,[]);}
 await page.close();
}finally{await browser?.close();await server?.close();}
