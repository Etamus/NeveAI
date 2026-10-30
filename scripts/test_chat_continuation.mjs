import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
import {createServer} from 'vite';
import {chromium} from '../logs/ui-image-26/node_modules/playwright/index.mjs';

const hook=`
onMount(()=>{
 window.__continueAudit={async seed(value,spacer){
  cancelGenerationAnchorRAF();releaseGeneratingMessageAnchor();cancelMessagesBottomWheelLock();
  generationBottomSpacerHeight=spacer;generationSpacerScrollLimit=null;generationSpacerScrollAllowance=null;
  selectedModels=['layout-test'];models.set([{id:'layout-test',name:'Test',info:{meta:{capabilities:{}}}}]);
  history=value;autoScroll=false;generating=false;taskIds=[];await tick();await waitForLayout(4);
  messagesContainerElement.scrollTop=messagesContainerElement.scrollHeight;await waitForLayout(2);
 },start:()=>continueResponse(),async update(data){await chatCompletionEventHandler(data,history.messages.tail,'fixture');},
 async reading(){messagesContainerElement.scrollTop=Math.max(0,messagesContainerElement.scrollTop-160);lastMessagesScrollTop=messagesContainerElement.scrollTop;await waitForLayout(2);},
 state(){return {top:messagesContainerElement.scrollTop,spacer:generationBottomSpacerHeight,done:history.messages.tail.done,anchor:anchoredGeneratingMessageId};}
 };return()=>delete window.__continueAudit;
});`;
let browser,server;const results=[];
try{
 server=await createServer({plugins:[{name:'continue-audit',enforce:'pre',async load(id){if(id.endsWith('/src/lib/components/chat/Chat.svelte'))return(await fs.readFile(id,'utf8')).replace("socketId = await waitForChatSocketReady();","socketId = 'fixture-socket';").replace('</script>',hook+'\n</script>');}}],server:{port:5188,strictPort:true,watch:{ignored:['**/logs/**','**/scripts/**','**/docs/**']}}});await server.listen();
 browser=await chromium.launch({ignoreDefaultArgs:['--hide-scrollbars']});
 for(const viewport of [{width:1440,height:1000},{width:390,height:844}]){
  const page=await browser.newPage({viewport});page.setDefaultTimeout(60000);const requests=[],errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/api/**',r=>{if(r.request().url().endsWith('/api/chat/completions')){requests.push(r.request().postDataJSON());return r.fulfill({json:{task_id:'fixture'}});}return r.request().method()==='GET'||r.request().url().includes('/auths/')?r.continue():r.fulfill({json:{}});});
  await page.goto('http://localhost:5188',{waitUntil:'domcontentloaded',timeout:90000});await page.waitForFunction(()=>window.__continueAudit);await page.evaluate(()=>document.fonts.ready);
  for(const reading of [false,true])for(const spacer of [0,240])for(const reason of [false,true]){
   const output=[...(reason?[{type:'reasoning',id:'old-reason',status:'completed',attributes:{type:'reasoning_content'},content:[{type:'output_text',text:'Previous thought'}]}]:[]),{type:'message',id:'old-answer',status:'completed',role:'assistant',content:[{type:'output_text',text:'Previous answer.'}]}];
   const content=(reason?'<details type="reasoning" done="true" duration="3">\n<summary>Thought</summary>\n&gt; Previous thought\n</details>\n\n':'')+('Previous answer. '.repeat(15)+'\n\n').repeat(12);
   const messages={prompt:{id:'prompt',parentId:null,childrenIds:['tail'],role:'user',content:'Tell a story',done:true},tail:{id:'tail',parentId:'prompt',childrenIds:[],role:'assistant',model:'layout-test',content,output,done:true}};
   await page.evaluate(({value,spacer})=>window.__continueAudit.seed(value,spacer),{value:{messages,currentId:'tail'},spacer});await page.waitForTimeout(250);if(reading)await page.evaluate(()=>window.__continueAudit.reading());
   const before=await page.evaluate(()=>window.__continueAudit.state());
   await page.evaluate(()=>{window.__continueFrames=[];window.__continueUntil=performance.now()+600;const sample=()=>{window.__continueFrames.push(document.querySelector('#messages-container').scrollTop);if(performance.now()<window.__continueUntil)requestAnimationFrame(sample);};sample();});
   await page.evaluate(()=>window.__continueAudit.start());await page.waitForTimeout(250);
   const after=await page.evaluate(()=>window.__continueAudit.state()),frames=await page.evaluate(()=>window.__continueFrames),request=requests.at(-1);
   assert.equal(request.continue_response,true);assert.equal(request.continuation_content,content);assert.equal(request.parent_id,'prompt');assert.equal(request.messages.at(-1).role,'assistant');assert.deepEqual(request.messages.at(-1).output,output);
   assert.equal(after.done,false);assert.equal(after.anchor,'tail');assert.equal(after.spacer,before.spacer);
   assert(frames.every(v=>Math.abs(v-before.top)<=0.5),`Continue moved ${before.top} -> ${JSON.stringify(frames)}`);
   assert(Math.abs(after.top-before.top)<=0.5,'Continue changed scroll position');
   const next=content+'\n<details type="reasoning" done="false">\n<summary>Thinking</summary>\n&gt; New private thought\n</details>';
   await page.evaluate(content=>window.__continueAudit.update({content}),next);await page.waitForTimeout(120);
   const outside=await page.locator('#message-tail #response-content-container').evaluate(e=>{const clone=e.cloneNode(true);clone.querySelectorAll('.reasoning-text').forEach(n=>n.remove());return clone.textContent;});assert(!outside.includes('New private thought'));
   await page.evaluate(content=>window.__continueAudit.update({content,done:true}),next.replace('done="false"','done="true"')+'\n\nContinued answer.');await page.waitForTimeout(250);
   results.push({viewport:viewport.width,reading,spacer,reason,before,after});
  }
  await page.screenshot({path:'logs/continue-'+viewport.width+'.png'});assert.deepEqual(errors,[]);await page.close();
 }
 await fs.writeFile('logs/chat-continuation-visual.json',JSON.stringify(results,null,2));console.log('PASS '+results.length+' continuation cases');
}finally{await browser?.close();await server?.close();}
