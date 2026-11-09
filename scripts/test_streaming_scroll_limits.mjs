import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
import {createServer} from 'vite';
import path from 'node:path';
import {spawn} from 'node:child_process';
import {chromium} from '../logs/ui-image-26/node_modules/playwright/index.mjs';

const hook=`
onMount(()=>{
 const scrollDescriptor=Object.getOwnPropertyDescriptor(Element.prototype,'scrollTop');
 const installScrollWriteAudit=()=>{
  const scrollViewport=messagesContainerElement;
  if(scrollViewport&&!Object.getOwnPropertyDescriptor(scrollViewport,'scrollTop')&&scrollDescriptor?.get&&scrollDescriptor?.set)Object.defineProperty(scrollViewport,'scrollTop',{configurable:true,get(){return scrollDescriptor.get.call(this);},set(value){const from=scrollDescriptor.get.call(this);if(value<from-0.5)window.__scrollWrites?.push({at:performance.now(),from,to:value,stack:new Error().stack});scrollDescriptor.set.call(this,value);}});
 };
 window.__scrollAudit={async seed(value,media=null){
  cancelGenerationAnchorRAF();releaseGeneratingMessageAnchor();cancelMessagesBottomWheelLock();
  generationBottomSpacerHeight=0;generationSpacerScrollLimit=null;generationSpacerScrollAllowance=null;
  selectedModels=['layout-test'];models.set([{id:'layout-test',name:'Test',info:{meta:{capabilities:{}}}}]);
  if(media){value.messages.tail.content='';value.messages.tail.statusHistory=[{action:media,done:false,progress:25,width:768,height:512}];}
  history=value;autoScroll=false;generating=false;taskIds=['fixture'];await tick();installScrollWriteAudit();await waitForLayout(4);
  if(media)await anchorVisualMediaGeneration('prompt','tail');else await anchorGeneratingMessageTop('prompt','tail',{stabilizeAcrossFrames:false});await waitForLayout(3);
 },async chunk(content){await chatCompletionEventHandler({content},history.messages.tail,'layout-fixture');},
 async overshoot(){const limit=Math.max(textGenerationAnchorScrollTop??0,getMaxScrollWithoutGenerationSpacer());generationBottomSpacerHeight+=120;textGenerationAnchorUserMoved=true;flushSync();messagesContainerElement.scrollTop=limit+80;lastMessagesScrollTop=messagesContainerElement.scrollTop;await waitForLayout(2);},
 async finish(){await chatCompletionEventHandler({done:true},history.messages.tail,'layout-fixture');},
 state(){const row=messagesContainerElement.querySelector('[role="log"] > :first-child');const first=row?.querySelector('[role="listitem"]')??row;return {top:messagesContainerElement.scrollTop,last:lastMessagesScrollTop,max:getMessagesMaxScrollTop(),natural:getMaxScrollWithoutGenerationSpacer(),spacer:generationBottomSpacerHeight,anchor:textGenerationAnchorScrollTop,moved:textGenerationAnchorUserMoved,scrollbarHidden:messageScrollbarHidden,firstTop:first?.getBoundingClientRect().top,viewportTop:messagesContainerElement.getBoundingClientRect().top};}
 };return()=>delete window.__scrollAudit;
});`;
const transcript=(count)=>{const messages={};let parent=null;for(let i=0;i<count;i++){const id='old-'+i;messages[id]={id,parentId:parent,childrenIds:[],role:i%2?'assistant':'user',content:'Previous paragraph. '.repeat(30),done:true,model:'layout-test'};if(parent)messages[parent].childrenIds=[id];parent=id;}if(parent)messages[parent].childrenIds=['prompt'];messages.prompt={id:'prompt',parentId:parent,childrenIds:['tail'],role:'user',content:'Write a detailed response.',done:true};messages.tail={id:'tail',parentId:'prompt',childrenIds:[],role:'assistant',model:'layout-test',content:'First paragraph.',done:false};return{messages,currentId:'tail'};};
let server,browser,host,native;const results=[];
try{
 server=await createServer({plugins:[{name:'stream-scroll-audit',enforce:'pre',async load(id){if(id.endsWith('/src/lib/components/chat/Chat.svelte'))return(await fs.readFile(id,'utf8')).replace('void fitGenerationSpacerToViewport(desiredTop, true);','window.__positionRepairs?.push({at:performance.now(),from:messagesContainerElement.scrollTop,to:desiredTop});\nvoid fitGenerationSpacerToViewport(desiredTop, true);').replace('</script>',hook+'\n</script>');if(id.endsWith('/src/lib/utils/streamingTextFade.ts'))return(await fs.readFile(id,'utf8')).replace('if (!from) clear();','if (!from && previous) window.__fadeResets?.push({previous,text});\nif (!from) clear();');}}],server:{port:5188,strictPort:true,watch:{ignored:['**/logs/**','**/scripts/**','**/docs/**']}}});await server.listen();
 if(process.env.SCROLL_NATIVE){
  const installed=JSON.parse(await fs.readFile('.desktop/installed.json','utf8'));
  host=spawn(path.resolve('.desktop',installed.host),['--root',process.cwd(),'--runtime',path.resolve('.desktop',installed.runtime),'--profile',path.resolve('logs/stream-native/profile'),'--url','http://localhost:5188'],{windowsHide:true,env:{...process.env,NEVE_WEBVIEW2_TEST_MODE:'1',NEVE_WEBVIEW2_DEBUG_PORT:'9233'}});
  for(let i=0;i<150;i++){try{browser=await chromium.connectOverCDP('http://127.0.0.1:9233');break;}catch{await new Promise(r=>setTimeout(r,200));}}
  assert(browser,'Native WebView2 did not expose its test endpoint');
  if(process.env.SCROLL_PHYSICAL){
   native=spawn('powershell.exe',['-NoProfile','-ExecutionPolicy','Bypass','-File','scripts/native_hover_input.ps1','-WindowProcessId',String(host.pid)],{windowsHide:true});
   await new Promise((resolve,reject)=>{native.stdout.on('data',b=>{if(String(b).includes('READY'))resolve();});native.stderr.on('data',b=>console.error(String(b)));native.on('exit',c=>{if(c)reject(Error('Native input failed'));});});
  }
 }else browser=await chromium.launch({headless:!process.env.SCROLL_HEADED,ignoreDefaultArgs:['--hide-scrollbars'],args:process.env.SCROLL_SMOOTH?['--enable-smooth-scrolling']:[]});
 for(const viewport of process.env.SCROLL_NATIVE?[{width:1440,height:1000}]:[{width:1440,height:1000},{width:390,height:844}]){
  const page=process.env.SCROLL_NATIVE?browser.contexts()[0].pages()[0]:await browser.newPage({viewport});
  if(process.env.SCROLL_NATIVE)await page.setViewportSize(viewport);
  if(process.env.SCROLL_CPU){const cdp=await page.context().newCDPSession(page);await cdp.send('Emulation.setCPUThrottlingRate',{rate:Number(process.env.SCROLL_CPU)});}
  page.setDefaultTimeout(60000);const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/api/**',r=>r.request().method()==='GET'||r.request().url().includes('/auths/')?r.continue():r.fulfill({json:{}}));
  await page.goto('http://localhost:5188',{waitUntil:'domcontentloaded',timeout:90000});await page.waitForFunction(()=>window.__scrollAudit);await page.evaluate(()=>document.fonts.ready);
  for(const count of process.env.SCROLL_MEDIA_ONLY||process.env.SCROLL_FAST_ONLY?[]:[0,8,120]){
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
  if(process.env.SCROLL_SHRINK_ONLY)for(const count of [0,8]){
   await page.evaluate(v=>window.__scrollAudit.seed(v),transcript(count));
   const reference='reference-to-the-complete-guide-to-the-old-library';
   const source=Array.from({length:18},(_,i)=>'Paragraph '+i+'. Read [the guide]['+reference+'] for the complete details about the library and its history.').join('\n\n');
   await page.evaluate(text=>window.__scrollAudit.chunk(text),source);await page.waitForTimeout(300);
   const v=page.locator('#messages-container'),box=await v.boundingBox();await page.mouse.move(box.x+12,box.y+box.height/2);await page.mouse.wheel(0,100000);await page.waitForTimeout(100);
   const before=await page.evaluate(()=>window.__scrollAudit.state());
   await page.evaluate(text=>window.__scrollAudit.chunk(text),source+'\n\n['+reference+']: https://example.com/library\n');await page.waitForTimeout(300);
   const reformatted=await page.evaluate(()=>window.__scrollAudit.state());
   for(let i=0;i<5;i++){await page.mouse.wheel(0,100);await page.waitForTimeout(30);}
   const after=await page.evaluate(()=>window.__scrollAudit.state());
   results.push({viewport:viewport.width,count,kind:'forward-reference-shrink',before,reformatted,after});
   console.log(JSON.stringify(results.at(-1)));
   if(process.env.SCROLL_ASSERT_SHRINK)assert(after.top>=reformatted.top-0.5,'Downward wheel rolled back a preserved position after Markdown shrink');
   await page.mouse.wheel(0,-12);await page.waitForTimeout(100);
   const up=await page.evaluate(()=>window.__scrollAudit.state());
   await page.mouse.wheel(0,100);await page.waitForTimeout(100);
   const down=await page.evaluate(()=>window.__scrollAudit.state());
   if(process.env.SCROLL_ASSERT_SHRINK){
    assert(after.spacer-up.spacer>0&&after.spacer-up.spacer<=13,'Upward scroll must still consume only its spacer distance');
    assert(down.top<=up.max+1,'Downward scroll recreated consumed spacer');
    assert.equal(down.spacer,up.spacer,'Downward scroll changed the preserved spacer');
   }
   results.push({viewport:viewport.width,count,kind:'preserved-spacer-consumption',up,down});
   await page.evaluate(text=>window.__scrollAudit.chunk(text),source+'\n\n['+reference+']: https://example.com/library\n\n'+('New content continues growing normally. '.repeat(150)));await page.waitForTimeout(300);
   await page.mouse.wheel(0,100);await page.waitForTimeout(100);
   const regrown=await page.evaluate(()=>window.__scrollAudit.state());
   if(process.env.SCROLL_ASSERT_SHRINK)assert(regrown.top>down.top,'The protected limit must not freeze scrolling as content grows again');
   results.push({viewport:viewport.width,count,kind:'regrown-after-shrink',regrown});
   await page.evaluate(()=>window.__scrollAudit.finish());
  }
  if(process.env.SCROLL_FAST_ONLY&&!process.env.SCROLL_SHRINK_ONLY)for(const count of process.env.SCROLL_SOAK?[0,8,120,0,8,120,0,8,120]:[8,120]){
   const fixture=transcript(count);
   for(const message of Object.values(fixture.messages))if(message.id.startsWith('old-')&&message.role==='assistant')message.content+='\n\n| Item | Value |\n| --- | --- |\n| First | Second |\n\n```js\n'+('const value = 1;\n'.repeat(40))+'```';
   await page.evaluate(v=>window.__scrollAudit.seed(v),fixture);await page.waitForTimeout(250);
   const box=await page.locator('#messages-container').boundingBox();
   const mouseX=process.env.SCROLL_REVISIT?box.x+12:box.x+box.width/2;
   await page.mouse.move(mouseX,box.y+box.height/2);
   if(native)native.stdin.write(JSON.stringify({type:'move',x:mouseX,y:box.y+box.height/2})+'\n');
   if(process.env.SCROLL_REVISIT){
    for(let i=0;i<8;i++){await page.mouse.wheel(0,-1200);await page.waitForTimeout(60);}
    await page.waitForTimeout(250);
   }
   await page.evaluate(()=>{window.__positionRepairs=[];window.__scrollWrites=[];window.__fastFrames=[];window.__sampling=true;const sample=()=>{const v=document.querySelector('#messages-container'),p=document.querySelector('#message-prompt');window.__fastFrames.push({at:performance.now(),top:v.scrollTop,last:window.__scrollAudit.state().last,promptTop:p?p.getBoundingClientRect().top+v.scrollTop:null});if(window.__sampling)requestAnimationFrame(sample);};sample();});
   const replay=process.env.SCROLL_REPLAY?(await(await fetch('http://localhost:8080/api/v1/chats/f65f45de-0c88-4e85-a18d-961ce5190f32')).json()).chat.history.messages['8b08c3fb-09f0-4572-91e7-e1ed9fe79fa6'].content:null;
   const burst=page.evaluate(async(replay)=>{
    let text='First paragraph.';
    if(replay){for(let end=16;end<replay.length+16;end+=16){await window.__scrollAudit.chunk(replay.slice(0,end));await new Promise(r=>setTimeout(r,12));}}
    else for(let i=0;i<160;i++){text+='\n\nParagraph '+i+'. '+'Stable streaming content. '.repeat(12);await window.__scrollAudit.chunk(text);await new Promise(r=>setTimeout(r,12));}
   },replay);
   if(process.env.SCROLL_TOUCH){
    const cdp=await page.context().newCDPSession(page);
    for(let i=0;i<12;i++)await cdp.send('Input.synthesizeScrollGesture',{x:mouseX,y:box.y+box.height/2,yDistance:-1500,speed:6000,gestureSourceType:'touch'});
   }else for(let i=0;i<(native?900:110);i++){
    const delta=process.env.SCROLL_SOAK?(i%25<3?-100:100):Number(process.env.SCROLL_DELTA??1600);
    if(native)native.stdin.write(JSON.stringify({type:'wheel',delta:-Number(process.env.SCROLL_DELTA??960)})+'\n');else await page.mouse.wheel(0,delta);
    await page.waitForTimeout(process.env.SCROLL_SOAK&&i%25===24?80:4);
   }
   await burst;await page.waitForTimeout(200);
   const data=await page.evaluate(()=>{window.__sampling=false;return {frames:window.__fastFrames,repairs:window.__positionRepairs,writes:window.__scrollWrites,state:window.__scrollAudit.state()};});
   const rollbacks=data.repairs.filter(r=>r.from>r.to+0.5);
   results.push({viewport:viewport.width,count,kind:'fast-burst',rollbacks,...data});
   await fs.writeFile('logs/fast-scroll-partial.json',JSON.stringify(results,null,2));
   if(process.env.SCROLL_ASSERT_FAST)assert.equal(rollbacks.length,0,'Content rolled back during fast downward wheel');
   await page.evaluate(()=>window.__scrollAudit.finish());
  }
  for(const media of process.env.SCROLL_FAST_ONLY?[]:['stable_diffusion','video_generation'])for(const lines of [1,3,35]){
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
}finally{if(native&&native.exitCode===null){native.stdin.write('{"type":"quit"}\n');native.stdin.end();await new Promise(r=>native.on('exit',r));}await browser?.close();host?.kill();await server?.close();}
