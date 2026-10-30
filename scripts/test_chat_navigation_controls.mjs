import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
import {createServer} from 'vite';
import {chromium} from '../logs/ui-image-26/node_modules/playwright/index.mjs';
import utils from '../logs/ui-image-26/node_modules/playwright-core/lib/utilsBundle.js';
const {PNG}=utils;

const hook=`
onMount(()=>{
 window.__navigationAudit={snapshot:()=>structuredClone(history),async seed(value){
 cancelGenerationAnchorRAF();releaseGeneratingMessageAnchor();generationBottomSpacerHeight=0;
 generationSpacerScrollLimit=null;generationSpacerScrollAllowance=null;
 selectedModels=['layout-test'];models.set([{id:'layout-test',name:'Test',info:{meta:{capabilities:{}}}}]);
 history=value;autoScroll=false;generating=false;taskIds=[];await tick();window.__resetNavigationWindow?.();await tick();await waitForLayout(4);
 },notify(){toast('Layer audit',{duration:100000});}};
 return()=>delete window.__navigationAudit;
});`;
let server,browser;const results=[];
const previous='path[d="M15.75 19.5 8.25 12l7.5-7.5"]';
const next='path[d="m8.25 4.5 7.5 7.5-7.5 7.5"], path[d="M8.25 4.5l7.5 7.5-7.5 7.5"]';
const branchHistory=(count,tail=0,assistant=false)=>{
 const messages={};let parent=null;
 const add=(id,role,content,p=parent)=>{messages[id]={id,parentId:p,childrenIds:[],role,content,done:true,model:'layout-test',models:['layout-test']};if(p)messages[p].childrenIds.push(id);parent=id;};
 for(let i=0;i<count;i++)add('old-'+i,i%2?'assistant':'user',('Previous stable paragraph. '.repeat(8)+'\n\n').repeat(2));
 if(assistant)add('prompt','user','Question for two responses');
 const common=parent;
 for(const variant of [1,2]){
  add('version-'+variant,assistant?'assistant':'user','Version '+variant,common);
  if(!assistant)add('answer-'+variant,'assistant',('Answer. '.repeat(10)+'\n\n').repeat(12));
  if(variant===1)for(let i=0;i<tail;i++)add('tail-'+i,i%2?'assistant':'user','More history. '.repeat(8));
 }
 messages[parent].usage={total_tokens:1000,context_window:10000};
 return{messages,currentId:parent};
};
try{
 server=await createServer({plugins:[{name:'navigation-test-hook',enforce:'pre',async load(id){
  if(id.endsWith('/src/lib/components/chat/Chat.svelte'))return(await fs.readFile(id,'utf8')).replace('</script>',hook+'\n</script>');
  if(id.endsWith('/src/lib/components/chat/Messages.svelte')){
   const source=await fs.readFile(id,'utf8'),index=source.lastIndexOf('</script>');
   return source.slice(0,index)+`import { onMount as onNavigationAuditMount } from 'svelte'; onNavigationAuditMount(()=>{window.__resetNavigationWindow=()=>{messagesCount=30;buildMessages();};return()=>delete window.__resetNavigationWindow;});`+source.slice(index);
  }
 }}],server:{port:5188,strictPort:true,watch:{ignored:['**/logs/**','**/scripts/**','**/docs/**']}}});await server.listen();
 browser=await chromium.launch({ignoreDefaultArgs:['--hide-scrollbars']});
 for(const [name,viewport] of [['desktop',{width:1440,height:1000}],['narrow',{width:900,height:800}],['mobile',{width:390,height:844}]]){
  const page=await browser.newPage({viewport});page.setDefaultTimeout(60000);const errors=[];page.on('pageerror',e=>{errors.push(e.message);console.log('PAGEERROR',e.message);});
  await page.route('**/api/**',r=>r.request().method()==='GET'||r.request().url().includes('/auths/')?r.continue():r.fulfill({json:{}}));
  await page.goto('http://localhost:5188/c/a0bf5564-5162-457b-af95-65c6d789ebaf',{waitUntil:'domcontentloaded',timeout:90000});
  await page.waitForFunction(()=>window.__navigationAudit&&document.querySelector('#message-0e54b84c-8543-4523-ab0d-210ff4460098'),null,{timeout:90000});await page.evaluate(()=>document.fonts.ready);await page.waitForTimeout(600);
  const real=await page.evaluate(()=>window.__navigationAudit.snapshot());
  const checkSwitch=async(from,to,arrow,label)=>{
   const row=page.locator('#message-'+from);await row.scrollIntoViewIfNeeded();await page.waitForTimeout(350);
   const before=await row.evaluate(e=>e.getBoundingClientRect().top);
   await page.evaluate(({from,to})=>{window.__branchFrames=[];const end=performance.now()+600;const sample=()=>{const e=document.getElementById('message-'+to)??document.getElementById('message-'+from);if(e)window.__branchFrames.push(e.getBoundingClientRect().top);if(performance.now()<end)requestAnimationFrame(sample);};sample();},{from,to});
   await row.locator('button').filter({has:page.locator(arrow)}).first().click();
   const target=page.locator('#message-'+to);await target.waitFor();await page.waitForTimeout(500);
   const after=await target.evaluate(e=>{const v=document.querySelector('#messages-container');return{y:e.getBoundingClientRect().top,scroll:v.scrollTop,max:v.scrollHeight-v.clientHeight};});
   const dy=after.y-before;
   assert(Math.abs(dy)<=0.5||(dy>0&&Math.abs(after.scroll-after.max)<=1)||(dy<0&&after.scroll<=1),`${name} ${label}: unanchored jump ${dy}px`);
   const frames=await page.evaluate(()=>window.__branchFrames);assert(frames.every(y=>y>=Math.min(before,after.y)-1&&y<=Math.max(before,after.y)+1),`${name} ${label}: transient jump ${JSON.stringify(frames)}`);
   results.push({name,label,before,...after,dy});console.log(JSON.stringify(results.at(-1)));
   await page.waitForTimeout(300);assert(Math.abs((await target.evaluate(e=>e.getBoundingClientRect().top))-after.y)<=0.5,'Late branch movement');
  };
  if(!process.env.NAVIGATION_UI_ONLY){
  await checkSwitch('0e54b84c-8543-4523-ab0d-210ff4460098','ecc22940-b077-4eee-8b0f-d6bc3be0165e',previous,'real 2 to 1');
  await checkSwitch('ecc22940-b077-4eee-8b0f-d6bc3be0165e','0e54b84c-8543-4523-ab0d-210ff4460098',next,'real 1 to 2');
  await page.screenshot({path:`logs/navigation-real-${name}.png`});
  for(const count of [8,120])for(const tail of [0,40])for(const assistant of [false,true]){
   await page.evaluate(h=>window.__navigationAudit.seed(h),branchHistory(count,tail,assistant));await page.waitForTimeout(400);
   await checkSwitch('version-2','version-1',previous,`${count} ${tail} ${assistant?'response':'user'} 2 to 1`);
   await checkSwitch('version-1','version-2',next,`${count} ${tail} ${assistant?'response':'user'} 1 to 2`);
  }
  const multi=branchHistory(120,10,true);multi.messages.prompt.models=['layout-test','other'];
  for(const id of ['version-1','version-2'])multi.messages[id].modelIdx=0;
  multi.messages['other-response']={id:'other-response',parentId:'prompt',childrenIds:[],role:'assistant',content:'Other model response',done:true,model:'other',modelIdx:1};
  multi.messages.prompt.childrenIds.push('other-response');
  await page.evaluate(h=>window.__navigationAudit.seed(h),multi);await page.waitForTimeout(400);
  await checkSwitch('version-2','version-1',previous,'multi model 2 to 1');
  await checkSwitch('version-1','version-2',next,'multi model 1 to 2');
  }
  for(const dark of [false,true]){
  await page.evaluate(dark=>document.documentElement.classList.toggle('dark',dark),dark);
  await page.evaluate(h=>window.__navigationAudit.seed(h),real);await page.waitForTimeout(400);
  // Both custom and Sonner notifications retain their coordinates while the menu overlaps.
  await page.evaluate(()=>window.__navigationAudit.notify());await page.waitForTimeout(250);
  const toastPositions=()=>page.locator('[data-neve-toast]').evaluateAll(es=>es.map(e=>({top:e.getBoundingClientRect().top,right:e.getBoundingClientRect().right})));
  const toastBefore=await toastPositions();
  const menu=page.locator('[data-neve-chat-more-menu]');await page.locator('#chat-context-menu-button').click();await menu.waitFor();await page.waitForTimeout(200);
  const layers=await menu.evaluate(e=>{const r=e.getBoundingClientRect();const toasts=[...document.querySelectorAll('[data-neve-toast],[data-sonner-toaster]')].map(t=>({top:t.getBoundingClientRect().top,right:t.getBoundingClientRect().right,z:getComputedStyle(t).zIndex}));return{z:getComputedStyle(e).zIndex,toasts,hit:e.contains(document.elementFromPoint(r.x+r.width/2,r.y+20))};});
  assert(layers.hit,'Toast intercepts menu');assert(layers.toasts.every(t=>Number(t.z)<Number(layers.z)));
  assert.deepEqual(await toastPositions(),toastBefore,'Notification moved');
  await page.screenshot({path:`logs/navigation-menu-${name}-${dark?'dark':'light'}.png`});await page.keyboard.press('Escape');await page.waitForTimeout(250);
  // Percentage is always visible; hover/touch only opens the usage popup.
  const trigger=page.locator('[data-token-usage-trigger]:visible');await trigger.waitFor();
  const percent=trigger.locator('[data-token-usage-percentage]');assert.equal(await percent.evaluate(e=>getComputedStyle(e).opacity),'1');
  const closedWidth=await trigger.evaluate(e=>e.getBoundingClientRect().width);
  if(name==='mobile')await trigger.click();else await trigger.hover();
  const popup=page.locator('[data-token-usage-popup]');await popup.waitFor({state:'visible'});await page.waitForTimeout(200);
  assert((await percent.evaluate(e=>e.getBoundingClientRect().width))>10);assert.equal(await popup.locator('svg').count(),0);
  assert.equal(await trigger.evaluate(e=>e.getBoundingClientRect().width),closedWidth,'Hover changed indicator width');
  await page.screenshot({path:`logs/navigation-tokens-${name}-${dark?'dark':'light'}.png`});
  if(name==='mobile')await trigger.click();else await page.mouse.move(2,2);await popup.waitFor({state:'detached'});await page.waitForTimeout(200);
  assert.equal(await percent.evaluate(e=>getComputedStyle(e).opacity),'1');
  await page.locator('#chat-input').fill('Expanded composer.\n'.repeat(8));await page.waitForTimeout(200);
  if(name==='mobile')await trigger.click();else await trigger.hover();await popup.waitFor({state:'visible'});await page.waitForTimeout(200);
  assert((await percent.evaluate(e=>e.getBoundingClientRect().width))>10);
  if(name==='mobile')await trigger.click();else await page.mouse.move(2,2);await popup.waitFor({state:'detached'});
  await page.locator('#chat-input').fill('');await page.waitForTimeout(200);
  for(const total of [0,1000,10000]){
   const h=branchHistory(8);h.messages[h.currentId].usage={total_tokens:total,context_window:10000};
   await page.evaluate(h=>window.__navigationAudit.seed(h),h);await page.waitForTimeout(200);
   assert.equal(await percent.innerText(),`${(total/100).toFixed(1)}%`);
   assert.equal(await percent.evaluate(e=>getComputedStyle(e).opacity),'1');
  }
  const loading=branchHistory(8);loading.messages[loading.currentId].content='';loading.messages[loading.currentId].done=false;
  await page.evaluate(h=>window.__navigationAudit.seed(h),loading);const loader=page.locator('#message-'+loading.currentId+' .orbiting-spheres');await loader.waitFor();
  const animation=await loader.evaluate(e=>[...e.querySelectorAll('*')].flatMap(n=>n.getAnimations()).map(a=>({duration:a.effect.getTiming().duration,delay:a.effect.getTiming().delay})));
  assert.deepEqual(animation.map(a=>a.duration),[2500,1500,1500]);assert.equal(animation[2].delay,-750);
  const sample=()=>loader.locator('.orbiting-dot').first().evaluate(e=>({t:getComputedStyle(e).transform,o:getComputedStyle(e).opacity}));
  for(const reducedMotion of ['no-preference','reduce']){
   await page.emulateMedia({reducedMotion});
   const one=await sample(),first=PNG.sync.read(await loader.screenshot());await page.waitForTimeout(220);
   const second=PNG.sync.read(await loader.screenshot());assert.notDeepEqual(await sample(),one);
   assert.notDeepEqual(first.data,second.data,`Chat loader pixels did not move: ${reducedMotion}`);
  }
  await page.emulateMedia({reducedMotion:'no-preference'});
  await page.screenshot({path:`logs/navigation-loader-${name}-${dark?'dark':'light'}.png`});
  assert.deepEqual(errors,[]);console.log(JSON.stringify({name,dark,layers,animation,errors}));
  }
  await page.close();
 }
 await fs.writeFile(process.env.NAVIGATION_UI_ONLY?'logs/tokens-orbit-ui-results.json':'logs/navigation-controls-results.json',JSON.stringify(results,null,2));console.log('PASS',results.length,'branch switches, tokens, toasts and loader');
}finally{await browser?.close();await server?.close();}
