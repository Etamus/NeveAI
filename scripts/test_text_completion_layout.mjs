import fs from 'node:fs/promises';
import {createServer} from 'vite';
import {chromium} from '../logs/ui-image-26/node_modules/playwright/index.mjs';
import assert from 'node:assert/strict';
const hook=`
onMount(()=>{
 window.__completionAudit={async seed({value,mode,spacer,fade}){
  cancelGenerationAnchorRAF();releaseGeneratingMessageAnchor();
  generationBottomSpacerHeight=spacer;generationSpacerScrollLimit=null;generationSpacerScrollAllowance=null;
  selectedModels=['layout-test'];models.set([{id:'layout-test',name:'Test',info:{meta:{capabilities:{}}}}]);
  settings.update(s=>({...s,chatFadeStreamingText:fade}));
  history=value;autoScroll=false;generating=false;taskIds=['fixture'];await tick();await waitForLayout(4);
  messagesContainerElement.scrollTop=messagesContainerElement.scrollHeight;await waitForLayout(3);
  if(mode==='reading')messagesContainerElement.scrollTop-=140;
  if(mode!=='follow'){anchoredGeneratingMessageId='tail';textGenerationAnchorScrollTop=messagesContainerElement.scrollTop;textGenerationAnchorUserMoved=mode==='reading';}
  autoScroll=mode==='follow';await tick();
 },async settle(residual=0){messagesContainerElement.scrollTop=messagesContainerElement.scrollHeight;await waitForLayout(2);if(residual)messagesContainerElement.scrollTop-=residual;autoScroll=true;},
 async finish(){await chatCompletionEventHandler({done:true},history.messages.tail,'layout-fixture');await tick();},
 async finalChunk(content){await chatCompletionEventHandler({content},history.messages.tail,'layout-fixture');}
 };return()=>delete window.__completionAudit;
});`;
let browser,server;const results=[];
try{
 server=await createServer({plugins:[{name:'completion-test-hook',enforce:'pre',async load(id){if(id.endsWith('/src/lib/components/chat/Chat.svelte'))return(await fs.readFile(id,'utf8')).replace('</script>',hook+'\n</script>');}}],server:{port:5188,strictPort:true,watch:{ignored:['**/logs/**','**/scripts/**','**/docs/**']}}});await server.listen();
 browser=await chromium.launch({ignoreDefaultArgs:['--hide-scrollbars']});
 const samples={short:'First paragraph.\n\nLast paragraph.',long:Array.from({length:32},(_,i)=>`Paragraph ${i}. `+'Words in a stable response. '.repeat(5)).join('\n\n'),table:'First paragraph.\n\n| Name | Value |\n| --- | --- |\n| Alpha | One |\n| Beta | Two |',code:'First paragraph.\n\n```python\n'+Array.from({length:40},(_,i)=>`print(${i})`).join('\n')+'\n```',reasoning:'<details type="reasoning" done="true" duration="3">\n<summary>Thought</summary>\n&gt; Completed thought.\n</details>\n\nFirst paragraph.\n\nLast paragraph.',list:'First paragraph.\n\n- One\n- Two\n- Three\n\nFinal paragraph.'};
 if(process.env.COMPLETION_EXTENDED){
  samples.math='First paragraph.\n\nMath $x^2$ and display:\n\n$$\nx^2+y^2=z^2\n$$\n\nFinal paragraph.';
  samples.document='Document prepared.';
  samples.tools='<details type="tool_calls" name="Lookup" done="true" arguments="{}" result="{}">\n<summary>Tool</summary>\nResult\n</details>\n\nFinal paragraph.';
 }
 for(const [name,viewport] of [['desktop',{width:1440,height:1000}],['mobile',{width:390,height:844}]]){
  const page=await browser.newPage({viewport});page.setDefaultTimeout(60000);const errors=[];page.on('pageerror',e=>{errors.push(e.message);console.log('pageerror',e.message);});
  await page.route('**/api/**',r=>r.request().method()==='GET'||r.request().url().includes('/auths/')?r.continue():r.fulfill({json:{}}));
  await page.goto('http://localhost:5188',{waitUntil:'domcontentloaded',timeout:90000});await page.waitForFunction(()=>window.__completionAudit);
  const configurations=process.env.COMPLETION_EMPTY?[[0,true],[0,false]]:process.env.COMPLETION_EXTENDED?[[8,true],[8,false],[120,true]]:[[8,true]];
  for(const [count,fade] of configurations)for(const [kind,content] of Object.entries(samples))for(const mode of ['follow','anchored','reading']){
   const messages={};let previous=null;for(let i=0;i<count;i++){const id='old-'+i;messages[id]={id,parentId:previous,childrenIds:[],role:i%2?'assistant':'user',model:'layout-test',content:'Previous text. '.repeat(15),done:true};if(previous)messages[previous].childrenIds=[id];previous=id;}
   if(previous)messages[previous].childrenIds=['prompt'];messages.prompt={id:'prompt',role:'user',content:'Fixture prompt',parentId:previous,childrenIds:['tail'],done:true};messages.tail={id:'tail',role:'assistant',content,parentId:'prompt',childrenIds:[],model:'layout-test',done:false};
   if(kind==='document')messages.tail.files=[{id:'fixture-document',name:'Example.pdf',type:'file',content_type:'application/pdf',generated:true,size:1024}];
   await page.evaluate(v=>window.__completionAudit.seed(v),{value:{messages,currentId:'tail'},mode,spacer:mode==='follow'?0:250,fade});await page.waitForTimeout(250);await page.evaluate(()=>document.fonts.ready);
   if(mode==='follow')await page.evaluate(residual=>window.__completionAudit.settle(residual),kind==='math'?1:0);
   const measure=()=>page.evaluate(()=>{const e=document.querySelector('#message-tail'),v=document.querySelector('#messages-container'),c=e.querySelector('#response-content-container'),blocks=c.querySelectorAll('p,table,pre,li');const last=blocks[blocks.length-1]??c;return{scroll:v.scrollTop,total:v.scrollHeight,bodyY:c.getBoundingClientRect().y,bodyHeight:c.getBoundingClientRect().height,lastY:last.getBoundingClientRect().y,lastHeight:last.getBoundingClientRect().height,toolbar:e.querySelector('.buttons')?.getBoundingClientRect().height,spacer:document.querySelector('[data-generation-spacer]')?.getBoundingClientRect().height??0};});
   const before=await measure();await page.evaluate(()=>window.__completionAudit.finish());await page.waitForTimeout(350);const after=await measure();
   const result={name,kind,mode,count,fade,before,after,dy:after.lastY-before.lastY};results.push(result);console.log(JSON.stringify(result));
   if(process.env.COMPLETION_ASSERT)for(const key of ['scroll','bodyY','bodyHeight','lastY','lastHeight','toolbar'])assert(Math.abs(after[key]-before[key])<=0.5,`${name} ${kind} ${mode}: ${key} changed`);
  }
  assert.deepEqual(errors,[]);console.log('errors',JSON.stringify(errors));await page.close();
 }
 await fs.writeFile(process.env.COMPLETION_RESULT??'logs/text-completion-results.json',JSON.stringify(results,null,2));
}finally{await browser?.close();await server?.close();}
