import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
import {createServer} from 'vite';
import {chromium} from '../logs/ui-image-26/node_modules/playwright/index.mjs';

const hook=`
onMount(()=>{
 window.__scrollAudit={async seed(value,media=null){
  cancelGenerationAnchorRAF();releaseGeneratingMessageAnchor();cancelMessagesBottomWheelLock();
  generationBottomSpacerHeight=0;generationSpacerScrollLimit=null;generationSpacerScrollAllowance=null;
  selectedModels=['layout-test'];models.set([{id:'layout-test',name:'Test',info:{meta:{capabilities:{}}}}]);
  if(media){value.messages.tail.content='';value.messages.tail.statusHistory=[{action:media,done:false,progress:25,width:768,height:512}];}
  history=value;autoScroll=false;generating=false;taskIds=['fixture'];await tick();await waitForLayout(4);
  if(media)await anchorVisualMediaGeneration('prompt','tail');else await anchorGeneratingMessageTop('prompt','tail',{stabilizeAcrossFrames:false});await waitForLayout(3);
 },async chunk(content){await chatCompletionEventHandler({content},history.messages.tail,'layout-fixture');},
 async overshoot(){const limit=Math.max(textGenerationAnchorScrollTop??0,getMaxScrollWithoutGenerationSpacer());generationBottomSpacerHeight+=120;textGenerationAnchorUserMoved=true;flushSync();messagesContainerElement.scrollTop=limit+80;lastMessagesScrollTop=messagesContainerElement.scrollTop;await waitForLayout(2);},
 async finish(){await chatCompletionEventHandler({done:true},history.messages.tail,'layout-fixture');},
 state(){const row=messagesContainerElement.querySelector('[role="log"] > :first-child');const first=row?.querySelector('[role="listitem"]')??row;return {top:messagesContainerElement.scrollTop,last:lastMessagesScrollTop,max:getMessagesMaxScrollTop(),natural:getMaxScrollWithoutGenerationSpacer(),spacer:generationBottomSpacerHeight,anchor:textGenerationAnchorScrollTop,moved:textGenerationAnchorUserMoved,scrollbarHidden:messageScrollbarHidden,firstTop:first?.getBoundingClientRect().top,viewportTop:messagesContainerElement.getBoundingClientRect().top};}
 };return()=>delete window.__scrollAudit;
});`;
const transcript=(count)=>{const messages={};let parent=null;for(let i=0;i<count;i++){const id='old-'+i;messages[id]={id,parentId:parent,childrenIds:[],role:i%2?'assistant':'user',content:'Previous paragraph. '.repeat(30),done:true,model:'layout-test'};if(parent)messages[parent].childrenIds=[id];parent=id;}if(parent)messages[parent].childrenIds=['prompt'];messages.prompt={id:'prompt',parentId:parent,childrenIds:['tail'],role:'user',content:'Write a detailed response.',done:true};messages.tail={id:'tail',parentId:'prompt',childrenIds:[],role:'assistant',model:'layout-test',content:'First paragraph.',done:false};return{messages,currentId:'tail'};};
let server,browser;const results=[];
try{
 server=await createServer({plugins:[{name:'stream-scroll-audit',enforce:'pre',async load(id){if(id.endsWith('/src/lib/components/chat/Chat.svelte'))return(await fs.readFile(id,'utf8')).replace('void fitGenerationSpacerToViewport(desiredTop, true);','window.__positionRepairs?.push({at:performance.now(),from:messagesContainerElement.scrollTop,to:desiredTop});\nvoid fitGenerationSpacerToViewport(desiredTop, true);').replace('</script>',hook+'\n</script>');if(id.endsWith('/src/lib/utils/streamingTextFade.ts'))return(await fs.readFile(id,'utf8')).replace('if (!from) clear();','if (!from && previous) window.__fadeResets?.push({previous,text});\nif (!from) clear();');}}],server:{port:5188,strictPort:true,watch:{ignored:['**/logs/**','**/scripts/**','**/docs/**']}}});await server.listen();
 browser=await chromium.launch({ignoreDefaultArgs:['--hide-scrollbars']});
 for(const viewport of [{width:1440,height:1000},{width:390,height:844}]){
  const page=await browser.newPage({viewport});page.setDefaultTimeout(60000);const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/api/**',r=>r.request().method()==='GET'||r.request().url().includes('/auths/')?r.continue():r.fulfill({json:{}}));
  await page.goto('http://localhost:5188',{waitUntil:'domcontentloaded',timeout:90000});await page.waitForFunction(()=>window.__scrollAudit);await page.evaluate(()=>document.fonts.ready);
  for(const count of process.env.SCROLL_MEDIA_ONLY?[]:[0,8,120]){
   await page.evaluate(v=>window.__scrollAudit.seed(v),transcript(count));await page.waitForTimeout(250);
   await page.evaluate(()=>window.__scrollAudit.chunk('First paragraph.\n\nNew text.'));await page.waitForTimeout(150);
   const v=page.locator('#messages-container'),box=await v.boundingBox();await page.mouse.move(box.x+box.width/2,box.y+box.height/2);
   const before=await page.evaluate(()=>window.__scrollAudit.state());
   for(let i=0;i<4;i++){await page.mouse.wheel(0,100);await page.waitForTimeout(70);}
   const after=await page.evaluate(()=>window.__scrollAudit.state());
   results.push({viewport:viewport.width,count,kind:'initial',before,after});
   if(process.env.SCROLL_ASSERT)assert(Math.abs(after.top-before.top)<=0.5,'Scrolled into generation filler before overflow');
   assert.equal(after.scrollbarHidden,count===0,'Scrollbar should reflect real content, not reserved space');
   await page.evaluate(()=>window.__scrollAudit.finish());await page.waitForTimeout(200);
   const idle=await page.evaluate(()=>window.__scrollAudit.state());await page.mouse.wheel(0,-12);await page.waitForTimeout(100);const idleUp=await page.evaluate(()=>window.__scrollAudit.state());await page.mouse.wheel(0,100);await page.waitForTimeout(100);const idleDown=await page.evaluate(()=>window.__scrollAudit.state());
   results.push({viewport:viewport.width,count,kind:'short-spacer',idle,idleUp,idleDown});
   if(process.env.SCROLL_ASSERT){assert(idle.spacer-idleUp.spacer>0&&idle.spacer-idleUp.spacer<=13,'Upward scroll removed more than its distance');assert(Math.abs(idleDown.spacer-idleUp.spacer)<=0.5,'Downward scroll swallowed the spacer');}
   await page.evaluate(v=>window.__scrollAudit.seed(v),transcript(count));await page.waitForTimeout(200);
   const anchor=await page.evaluate(()=>window.__scrollAudit.state());await page.evaluate(()=>window.__scrollAudit.overshoot());const excess=await page.evaluate(()=>window.__scrollAudit.state());await page.mouse.wheel(0,100);await page.waitForTimeout(100);const recovered=await page.evaluate(()=>window.__scrollAudit.state());
   assert(excess.top>anchor.top+1,'Overshoot fixture did not move beyond the anchor');assert(recovered.top<=Math.max(anchor.anchor,anchor.natural)+0.5,'Existing excess was not clamped');results.push({viewport:viewport.width,count,kind:'existing-excess',anchor,excess,recovered});
   await page.evaluate(v=>window.__scrollAudit.seed(v),transcript(count));await page.waitForTimeout(200);
   await page.evaluate(()=>{window.__positionRepairs=[];window.__scrollFrames=[];window.__scrollEnds=performance.now()+7000;const sample=()=>{const v=document.querySelector('#messages-container'),p=document.querySelector('#message-tail p:last-of-type');if(p)window.__scrollFrames.push({top:v.scrollTop,y:p.getBoundingClientRect().top,text:p.textContent,last:window.__scrollAudit.state().last,hidden:v.classList.contains('reasoning-layout-no-scroll')});if(performance.now()<window.__scrollEnds)requestAnimationFrame(sample);};sample();});
   let text='First paragraph.';
   for(let i=0;i<24;i++){text+='\n\nParagraph '+i+'. '+'Stable words in a streamed response. '.repeat(7);await page.evaluate(text=>window.__scrollAudit.chunk(text),text);await page.mouse.wheel(0,200);await page.waitForTimeout(65);}
   await page.waitForTimeout(220);
   const long=await page.evaluate(()=>window.__scrollAudit.state());
   for(let i=0;i<10;i++){await page.mouse.wheel(0,180);await page.waitForTimeout(25);}
   const settled=await page.evaluate(()=>window.__scrollAudit.state());
   assert(!settled.scrollbarHidden,'Long content lost its scrollbar');
   const frames=await page.evaluate(()=>{window.__scrollEnds=0;return window.__scrollFrames;});
   const reversals=frames.filter((f,i)=>i&&f.top<frames[i-1].top-1&&f.text===frames[i-1].text);
   const firstVisible=frames.findIndex(f=>!f.hidden);
   if(process.env.SCROLL_ASSERT){assert(firstVisible>=0,'Scrollbar never appeared for long content');assert(frames.slice(firstVisible).every(f=>!f.hidden),'Scrollbar blinked during append-only streaming');}
   results.push({viewport:viewport.width,count,kind:'growing',long,settled,reversals,frames,repairs:await page.evaluate(()=>window.__positionRepairs)});
   if(process.env.SCROLL_ASSERT)assert.equal(reversals.length,0,'Scroll was rolled back while scrolling down');
   await page.evaluate(()=>{window.__fadeResets=[];});
   const burst=page.evaluate(async text=>{for(let i=0;i<100;i++){text+=(i%20===0?'\n\n':'')+[' more',' text',' with',' *emphasis',' and',' detail*',' in',' a',' growing',' paragraph.'][i%10];await window.__scrollAudit.chunk(text);await new Promise(r=>setTimeout(r,25));}},text);
   for(let i=0;i<100;i++){await page.mouse.wheel(0,140);await page.waitForTimeout(12);}
   await burst;await page.waitForTimeout(250);
   results.push({viewport:viewport.width,count,kind:'burst',resets:await page.evaluate(()=>window.__fadeResets),repairs:await page.evaluate(()=>window.__positionRepairs)});
   await page.evaluate(()=>window.__scrollAudit.finish());await page.waitForTimeout(250);
   const completed=await page.evaluate(()=>window.__scrollAudit.state());await page.mouse.wheel(0,-12);await page.waitForTimeout(120);const up=await page.evaluate(()=>window.__scrollAudit.state());await page.mouse.wheel(0,12);await page.waitForTimeout(120);const down=await page.evaluate(()=>window.__scrollAudit.state());
   results.push({viewport:viewport.width,count,kind:'completed',completed,up,down});
   await page.screenshot({path:'logs/stream-scroll-'+viewport.width+'-'+count+'.png'});
  }
  if(!process.env.SCROLL_MEDIA_ONLY){
  await page.evaluate(v=>window.__scrollAudit.seed(v),transcript(8));await page.evaluate(()=>window.__scrollAudit.chunk('```python\n'+Array.from({length:70},(_,i)=>'print('+i+')').join('\n')+'\n```'));await page.waitForTimeout(250);
  const code=page.locator('#message-tail .code-scroll');await code.hover();const outerBefore=await page.evaluate(()=>window.__scrollAudit.state());await page.mouse.wheel(0,100);await page.waitForTimeout(150);const inner=await code.evaluate(e=>e.scrollTop),outerAfter=await page.evaluate(()=>window.__scrollAudit.state());assert(inner>0,'Nested code scrolling was blocked');assert(Math.abs(outerAfter.top-outerBefore.top)<=0.5,'Nested code scrolled the transcript');
  results.push({viewport:viewport.width,kind:'nested-code',inner,outerBefore,outerAfter});
  }
  for(const media of ['stable_diffusion','video_generation'])for(const lines of [1,3,35]){
   await page.evaluate(({value,media})=>window.__scrollAudit.seed(value,media),{value:transcript(8),media});await page.waitForTimeout(250);
   await page.locator('#chat-input').fill(Array.from({length:lines},(_,i)=>'Line '+i).join('\n'));await page.waitForTimeout(400);
   await page.locator('#messages-container').evaluate(e=>{e.scrollTop=e.scrollHeight;});await page.waitForTimeout(150);
   const before=await page.evaluate(()=>window.__scrollAudit.state());const box=await page.locator('#messages-container').boundingBox();await page.mouse.move(box.x+box.width/2,box.y+box.height/2);
   for(let i=0;i<5;i++){await page.mouse.wheel(0,100);await page.waitForTimeout(30);}
   const after=await page.evaluate(()=>window.__scrollAudit.state());assert(Math.abs(before.top-after.top)<=0.5,'Media bottom moved under repeated wheel');assert.equal(before.spacer,after.spacer,'Media wheel removed reserved space');
   results.push({viewport:viewport.width,kind:'media',media,lines,before,after});
  }
  assert.deepEqual(errors,[]);await page.close();
 }
 await fs.writeFile(process.env.SCROLL_RESULT??'logs/stream-scroll-results.json',JSON.stringify(results,null,2));
 console.log(JSON.stringify(results.map(({frames,...rest})=>rest),null,2));
}finally{await browser?.close();await server?.close();}
