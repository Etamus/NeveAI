import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { createServer } from 'vite';
import { chromium } from '../logs/ui-image-26/node_modules/playwright/index.mjs';
import utils from '../logs/ui-image-26/node_modules/playwright-core/lib/utilsBundle.js';
const {PNG}=utils;
const hook=`
onMount(()=>{
 window.__tailAudit={async seed(value){
  cancelGenerationAnchorRAF();releaseGeneratingMessageAnchor();
  generationBottomSpacerHeight=0;generationSpacerScrollLimit=null;generationSpacerScrollAllowance=null;
  selectedModels=['tail-audit'];models.set([{id:'tail-audit',name:'Test',info:{meta:{capabilities:{}}}}]);
  history=value;autoScroll=false;generating=false;await tick();await waitForLayout(3);
  messagesContainerElement.scrollTop=messagesContainerElement.scrollHeight;await waitForLayout(3);
 }};return()=>delete window.__tailAudit;
});`;
const server=await createServer({plugins:[{name:'tail-hover-fixture',enforce:'pre',async load(id){
 if(id.endsWith('/src/lib/components/chat/Chat.svelte'))return(await fs.readFile(id,'utf8')).replace('</script>',hook+'\n</script>');
}}],server:{port:5188,strictPort:true,watch:{ignored:['**/logs/**']}}});
await server.listen();
let host;
let browser;
if(process.env.TAIL_NATIVE){
 const state=JSON.parse(await fs.readFile('.desktop/installed.json','utf8'));
 host=spawn(path.resolve('.desktop',state.host),['--root',process.cwd(),'--runtime',path.resolve('.desktop',state.runtime),'--profile',path.resolve('logs/tail-native/profile'),'--url','http://localhost:5188'],{windowsHide:true,env:{...process.env,NEVE_WEBVIEW2_TEST_MODE:'1',NEVE_WEBVIEW2_DEBUG_PORT:'9231'}});
 for(let i=0;i<150;i++){try{browser=await chromium.connectOverCDP('http://127.0.0.1:9231');break;}catch{await new Promise(r=>setTimeout(r,200));}}
 assert(browser,'Native host did not start');
}else browser=await chromium.launch({ignoreDefaultArgs:['--hide-scrollbars']});
const results=[];
function compare(a,b){
 const first=PNG.sync.read(a),second=PNG.sync.read(b);
 const masks=[first,second].map(p=>{const m=new Set();for(let y=0;y<p.height;y++)for(let x=0;x<p.width;x++){const i=(y*p.width+x)*4;if(Math.min(p.data[i],p.data[i+1],p.data[i+2])>180)m.add(y*p.width+x);}return m;});
 const scores=[];for(let dy=-2;dy<=2;dy++)for(let dx=-2;dx<=2;dx++){let common=0;for(const i of masks[0]){const x=i%first.width+dx,y=Math.floor(i/first.width)+dy;if(x>=0&&x<first.width&&y>=0&&y<first.height&&masks[1].has(y*first.width+x))common++;}scores.push({dx,dy,score:common/Math.max(1,masks[0].size+masks[1].size-common)});}
 scores.sort((a,b)=>b.score-a.score);return {best:scores[0],zero:scores.find(s=>s.dx===0&&s.dy===0)};
}
try{
 for(const [name,viewport,dpr,zoom] of [['desktop',{width:1440,height:1001},1,1],['scaled',{width:1365,height:901},1.25,1],['zoom90',{width:1440,height:1001},1,0.9],['zoom110',{width:1440,height:1001},1,1.1],['zoom125',{width:1440,height:1001},1,1.25],['mobile',{width:390,height:845},1,1]]){
  const page=process.env.TAIL_NATIVE ? browser.contexts()[0].pages()[0] : await browser.newPage({viewport,deviceScaleFactor:dpr});
  if(process.env.TAIL_NATIVE) await page.setViewportSize(viewport);
  page.setDefaultTimeout(15000);
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/api/chat/completions',r=>r.abort());
  await page.route('**/api/v1/chats/**',r=>r.request().method()==='GET'?r.continue():r.abort());
  await page.goto('http://localhost:5188',{waitUntil:'domcontentloaded',timeout:90000});await page.waitForFunction(()=>window.__tailAudit,{},{timeout:90000});
  await page.evaluate(()=>document.documentElement.classList.add('dark'));
  await page.evaluate(zoom=>document.documentElement.style.zoom=zoom,zoom);
  for(const kind of ['table','document']){
   const messages={};let previous=null;
   for(let n=0;n<36;n++){const id='old-'+n;messages[id]={id,role:n%2?'assistant':'user',parentId:previous,childrenIds:[],content:'Earlier message. '.repeat(10),done:true,model:'tail-audit'};if(previous)messages[previous].childrenIds=[id];previous=id;}
   messages[previous].childrenIds=['tail'];messages.tail={id:'tail',role:'assistant',parentId:previous,childrenIds:[],done:true,model:'tail-audit',content:kind==='table'?'| Header | Value |\n| --- | --- |\n| Stable text | Stable value |\n| Another row | Another value |\n| Last row | Last value |':'Document prepared.',...(kind==='document'?{files:[{id:'tail-test-file',type:'file',generated:true,name:'Stable test document.pdf',content_type:'application/pdf',size:12000}]}:{})};
   await page.evaluate(h=>window.__tailAudit.seed(h),{currentId:'tail',messages});await page.waitForTimeout(500);
   const viewportEl=page.locator('#messages-container');
   await viewportEl.hover();await page.mouse.wheel(0,-350);await page.waitForTimeout(150);
   await page.mouse.wheel(0,50000);await page.waitForTimeout(1000);
   const target=page.locator(kind==='table'?'#message-tail .markdown-table tbody tr:last-child td:last-child':'#message-tail button .truncate').first();
   await target.waitFor();
   const box=await target.boundingBox();console.log('target',name,kind,box);
   assert(box.y>=0&&box.y<viewport.height,JSON.stringify({name,kind,box}));
   const clip={x:Math.floor(box.x),y:Math.floor(box.y),width:Math.ceil(box.width),height:Math.ceil(box.height)};
   const measure=()=>target.evaluate(el=>{const r=el.getBoundingClientRect(),v=document.querySelector('#messages-container'),p=document.querySelector('#chat-pane');return{x:r.x,y:r.y,width:r.width,height:r.height,scroll:v.scrollTop,total:v.scrollHeight,spacer:v.querySelector('[data-generation-spacer]')?.getBoundingClientRect().height??0,padding:p.style.getPropertyValue('--chat-composer-height')};});
   await page.mouse.move(2,2);await page.waitForTimeout(150);const before=await measure();
   const base=await page.screenshot({clip,path:`logs/tail-${name}-${kind}-before.png`});
   const samples=[];
   for(const fraction of [0.2,0.8,0.4]){
    await target.evaluate(el=>{
     window.__hoverFrames=[];const end=performance.now()+400;
     const sample=()=>{const r=el.getBoundingClientRect(),v=document.querySelector('#messages-container');window.__hoverFrames.push([r.x,r.y,r.width,r.height,v.scrollTop,v.scrollHeight]);if(performance.now()<end)requestAnimationFrame(sample);};sample();
    });
    await page.mouse.move(box.x+box.width*fraction,box.y+box.height/2);await page.waitForTimeout(30);
    const early=compare(base,await page.screenshot({clip}));assert.equal(early.best.dx,0);assert.equal(early.best.dy,0);
    await page.waitForTimeout(400);
    const frames=await page.evaluate(()=>window.__hoverFrames);
    for(const frame of frames)assert.deepEqual(frame,frames[0],'Transient hover shift');
    const state=await measure(),shot=await page.screenshot({clip,path:`logs/tail-${name}-${kind}-hover-${fraction}.png`});
    assert.deepEqual(state,before,'Hover changed layout or scroll');
    const pixels=compare(base,shot);assert.equal(pixels.best.dx,0);assert.equal(pixels.best.dy,0);
    samples.push({state,pixels,early,frames:frames.length});
   }
   const control=page.locator(kind==='table'?'#message-tail .markdown-table + div button':'#message-tail button.absolute').first();
   await control.hover();await page.waitForTimeout(400);assert.deepEqual(await measure(),before,'Control hover changed layout');
   results.push({name,dpr,kind,before,samples,errors});
   console.log(JSON.stringify(results.at(-1)));
  }
  if(!process.env.TAIL_NATIVE)await page.close();
 }
 await fs.writeFile(process.env.TAIL_NATIVE?'logs/chat-tail-native-results.json':'logs/chat-tail-hover-results.json',JSON.stringify(results,null,2));
}finally{await browser.close();if(host)host.kill();await server.close();}
