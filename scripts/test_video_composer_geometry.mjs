import fs from 'node:fs/promises';
import {existsSync} from 'node:fs';
import assert from 'node:assert/strict';
import {createServer} from 'vite';
import {chromium} from '../logs/ui-image-26/node_modules/playwright/index.mjs';
const inputHook=`onMount(()=>{window.__geometryInput={mode(value){webSearchEnabled=value==='web';deepSearchEnabled=value==='deep';codeExecutionEnabled=value==='code';stableDiffusionEnabled=value==='image';stableDiffusionQuality='neve_image_2';videoGenerationEnabled=value==='video';musicGenerationEnabled=value==='music';},text:setText};return()=>delete window.__geometryInput;});`;
const hook=`onMount(()=>{let portrait=false;window.__geometryChat={
 async seed(count,reference=false){portrait=reference;cancelGenerationAnchorRAF();releaseGeneratingMessageAnchor();generationBottomSpacerHeight=0;generationSpacerScrollLimit=null;generationSpacerScrollAllowance=null;taskIds=null;generating=false;
 selectedModels=['geometry'];models.set([{id:'geometry',name:'Geometry',info:{meta:{capabilities:{}}}}]);
 const messages={};let parent=null;for(let i=0;i<count;i++){let id='old-'+i;messages[id]={id,parentId:parent,childrenIds:[],role:i%2?'assistant':'user',model:'geometry',content:'Previous content. '.repeat(25),done:true};if(parent)messages[parent].childrenIds=[id];parent=id;}
 history={messages,currentId:parent};await tick();await waitForLayout(3);},
 async start(){await messageInput.setText('');prompt='';const parent=history.currentId;const id='prompt';history.messages[id]={id,parentId:parent,childrenIds:['tail'],role:'user',content:'Create a video.',done:true,...(portrait?{files:[{type:'image',url:'/geometry.png',image_width:480,image_height:864}]}:{})};if(parent)history.messages[parent].childrenIds=[id];history.messages.tail={id:'tail',parentId:id,childrenIds:[],role:'assistant',model:'geometry',content:'',done:false,video_generation_features:{video_generation:true,video_generation_aspect_ratio:'16:9'}};history.currentId='tail';history=history;taskIds=['fixture'];await anchorVisualMediaGeneration('prompt','tail');},
 async progress(){history.messages.tail.statusHistory=[{action:'video_generation',description:'Creating video',done:false,progress:50,width:864,height:480}];history=history;await tick();},
 async finish(){const m=history.messages.tail;m.statusHistory=[{...m.statusHistory[0],width:portrait?480:864,height:portrait?864:480,done:true,progress:100}];m.files=[{id:'geometry-video',type:'video',content_type:'video/mp4',url:portrait?'/geometry-portrait.mp4':'/geometry.mp4',name:'fixture.mp4'}];history=history;await chatCompletionEventHandler({done:true},m,'geometry-fixture');}
 };return()=>delete window.__geometryChat;});`;
let server,browser;const results=[];
try{
 server=await createServer({plugins:[{name:'video-geometry',enforce:'pre',async load(id){if(id.endsWith('/src/lib/components/chat/MessageInput.svelte'))return(await fs.readFile(id,'utf8')).replace('</script>',inputHook+'\n</script>');if(id.endsWith('/src/lib/components/chat/Chat.svelte'))return(await fs.readFile(id,'utf8')).replace('</script>',hook+'\n</script>');}}],server:{port:5188,strictPort:true,watch:{ignored:['**/logs/**','**/scripts/**','**/docs/**']}}});await server.listen();
 const brave='C:/Program Files/BraveSoftware/Brave-Browser/Application/brave.exe';
 browser=await chromium.launch({executablePath:existsSync(brave)?brave:undefined,args:['--autoplay-policy=no-user-gesture-required']});
 const asset=await fs.readFile('logs/video15-vlog-api-20261102/vdn_h3-api.mp4');
 const portraitAsset=await fs.readFile('logs/video-audio-20261102/h3-first-frame.mp4');
 const portraitImage=await fs.readFile('logs/video-audio-20261102/h3-first-frame.first.png');
 for(const width of [1440,1024,390]){
  const page=await browser.newPage({viewport:{width,height:1000}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/api/**',r=>r.request().method()==='GET'||r.request().url().includes('/auths/')?r.continue():r.fulfill({json:{}}));
  await page.route('**/geometry.mp4',r=>r.fulfill({body:asset,contentType:'video/mp4'}));
  await page.route('**/geometry-portrait.mp4',r=>r.fulfill({body:portraitAsset,contentType:'video/mp4'}));
  await page.route('**/geometry.png',r=>r.fulfill({body:portraitImage,contentType:'image/png'}));
  await page.goto('http://localhost:5188',{waitUntil:'domcontentloaded',timeout:90000});await page.waitForFunction(()=>window.__geometryChat&&window.__geometryInput);await page.evaluate(async dark=>{document.documentElement.classList.toggle('dark',dark);await document.fonts.ready;},width!==1024);
  await page.evaluate(()=>window.__geometryChat.seed(8));
  await page.locator('#chat-input').fill('First line of the draft.\nSecond line of the draft.\nThird line of the draft.');await page.waitForTimeout(200);
  const measure=()=>page.evaluate(()=>{const rect=s=>{const e=document.querySelector(s);if(!e)return null;const r=e.getBoundingClientRect();return{x:r.x,y:r.y,w:r.width,h:r.height};};return{editor:rect('#chat-input'),plus:rect('#input-menu-button'),send:rect('#send-message-button'),actions:rect('.message-input-actions'),composer:rect('#message-input-container'),bubble:rect('#message-prompt'),media:rect('[data-generated-visual-media]')??rect('[role="progressbar"]'),scroll:document.querySelector('#messages-container')?.scrollTop};});
  const modes=[];for(const mode of ['none','web','deep','code','image','video','music','none']){await page.evaluate(v=>window.__geometryInput.mode(v),mode);await page.waitForTimeout(180);modes.push({mode,...await measure()});}
  results.push({width,kind:'chips',modes});await page.screenshot({path:'logs/video-composer-chips-'+width+'.png'});
  for(const reference of [false,true])for(const count of [0,8])for(const position of ['anchor','end','reading']){
   await page.evaluate(({count,reference})=>window.__geometryChat.seed(count,reference),{count,reference});await page.evaluate(()=>window.__geometryInput.mode('video'));await page.locator('#chat-input').fill('First line\nSecond line\nThird line');await page.waitForTimeout(100);
   await page.evaluate(()=>window.__geometryChat.start());await page.waitForTimeout(150);const anchored=await measure();
   await page.evaluate(()=>window.__geometryChat.progress());await page.waitForTimeout(200);const started=await measure();
   if(position!=='anchor'){await page.locator('#messages-container').evaluate((e,position)=>{e.scrollTop=e.scrollHeight;if(position==='reading')e.scrollTop-=100;},position);await page.waitForTimeout(120);}
   const progress=await measure();
   await page.evaluate(()=>window.__geometryChat.finish());await page.waitForTimeout(200);const final=await measure();
   const decoded=await page.locator('#message-tail video').evaluate(async video=>{video.muted=true;await video.play();await new Promise(resolve=>setTimeout(resolve,80));video.pause();return{width:video.videoWidth,height:video.videoHeight,ready:video.readyState};});
   assert(decoded.width>0&&decoded.height>0&&decoded.ready>=2,'Fixture video did not decode');
   const decodedLayout=await measure();
   assert(Math.abs(decodedLayout.media.y-final.media.y)<=0.5&&Math.abs(decodedLayout.media.h-final.media.h)<=0.5,'Decoded metadata changed final geometry');
   results.push({width,kind:'video',count,reference,position,anchored,started,progress,final});
   await page.screenshot({path:'logs/video-composer-final-'+width+'-'+count+'.png'});
  }
  assert.deepEqual(errors,[]);await page.close();
 }
 await fs.writeFile('logs/video-composer-geometry.json',JSON.stringify(results,null,2));
 console.log(JSON.stringify(results,null,2));
 if(process.env.GEOMETRY_ASSERT)for(const row of results){if(row.kind==='chips'){const baseline=row.modes[0];for(const state of row.modes)for(const key of ['editor','plus','send'])assert(Math.abs(state[key].y-baseline[key].y)<=0.1,JSON.stringify({width:row.width,mode:state.mode,key,baseline:baseline[key],actual:state[key]}));}else{assert(row.anchored.media,'Initial preview was not reserved');assert(Math.abs(row.anchored.bubble.y-row.started.bubble.y)<=0.5,'Start moved user bubble');assert(Math.abs(row.final.bubble.y-row.progress.bubble.y)<=0.5,'Completion moved user bubble');assert(Math.abs(row.final.media.h-row.progress.media.h)<=0.5,'Completion changed media height');assert(Math.abs(row.final.media.y-row.progress.media.y)<=0.5,'Completion moved video');}}
}finally{await browser?.close();await server?.close();}
