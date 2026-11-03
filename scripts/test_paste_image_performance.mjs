import fs from 'node:fs/promises';
import {existsSync} from 'node:fs';
import {createHash} from 'node:crypto';
import assert from 'node:assert/strict';
import {createServer} from 'vite';
import {chromium} from '../logs/ui-image-26/node_modules/playwright/index.mjs';
import {installMobileOfflineApi} from './fixtures/mobile-offline-api.mjs';
const out='logs/paste-performance';
const hook=`onMount(()=>{window.__pasteAudit={async setup(temporary,compression,mode){files=[];selectedModels=['local/mobile-fixture'];temporaryChatEnabled.set(temporary);settings.update(s=>({...s,imageCompression:compression,imageCompressionSize:{width:1024,height:1024}}));config.update(c=>({...c,file:{...c.file,max_size:128,image_compression:{width:null,height:null}}}));stableDiffusionEnabled=!!mode;stableDiffusionQuality='qwen_image_2s';stableDiffusionModeOptions=imageModeDefaults(typeof mode==='string'?mode:'normal');await tick();},source(){return files[0]?.url;},state(){return files.map(f=>({status:f.status,type:f.type,url:f.url?.slice(0,40),mime:f.content_type}));}};return()=>delete window.__pasteAudit;});`;
let server,browser;const results=[];
try{
 await fs.mkdir(out,{recursive:true});
 const images=new Map();for(const name of ['small.png','large.png','large.jpg'])images.set(name,await fs.readFile(out+'/'+name));
 server=await createServer({plugins:[{name:'paste-audit-hook',enforce:'pre',async load(id){if(id.endsWith('/src/lib/components/chat/MessageInput.svelte'))return(await fs.readFile(id,'utf8')).replace('</script>',hook+'\n</script>');}}],server:{port:5188,strictPort:true,watch:{ignored:['**/logs/**','**/scripts/**','**/docs/**']}}});await server.listen();
 const brave='C:/Program Files/BraveSoftware/Brave-Browser/Application/brave.exe';browser=await chromium.launch({executablePath:existsSync(brave)?brave:undefined});
 const cases=process.env.PASTE_MODES?['restore','outpaint','inpaint','outfit','body'].map(mode=>({name:'large.png',temporary:false,compression:false,mode})):process.env.PASTE_QUICK?[{name:process.env.PASTE_FILE??'large.png',temporary:false,compression:!!process.env.PASTE_COMPRESS,mode:false}]:[
  {name:'small.png',temporary:false,compression:false,mode:false},
  {name:'large.png',temporary:false,compression:false,mode:false},
  {name:'large.jpg',temporary:false,compression:false,mode:false},
  {name:'large.png',temporary:false,compression:false,mode:true},
  {name:'large.png',temporary:true,compression:false,mode:false},
  {name:'large.png',temporary:false,compression:true,mode:false},
  {name:'large.jpg',temporary:false,compression:true,mode:false},
  {name:'small.png',temporary:false,compression:true,mode:false},
  {name:'large.png',temporary:true,compression:true,mode:false}
 ];
 for(const width of process.env.PASTE_QUICK?[1440]:[1440,390])for(const test of cases){
  const page=await browser.newPage({viewport:{width,height:1000}});const errors=[];page.on('pageerror',e=>errors.push(e.message));await installMobileOfflineApi(page);
  const original=images.get(test.name);let uploaded,uploadedType;
  await page.route('**/paste-test-source',r=>r.fulfill({body:original,contentType:test.name.endsWith('.jpg')?'image/jpeg':'image/png'}));
  await page.route('**/api/v1/files/?*',async route=>{if(route.request().method()!=='POST')return route.fallback();const data=await new Response(route.request().postDataBuffer(),{headers:{'content-type':route.request().headers()['content-type']}}).formData();const file=data.get('file');uploaded=Buffer.from(await file.arrayBuffer());uploadedType=file.type;await new Promise(r=>setTimeout(r,40));await route.fulfill({json:{id:'paste-fixture',filename:file.name,meta:{content_type:file.type,size:file.size},data:{}}});});
  await page.route('**/files/paste-fixture/process/status?*',r=>r.fulfill({body:'data: {"status":true}\n\n',contentType:'text/event-stream'}));
  await page.route('**/files/paste-fixture/content',r=>r.fulfill({body:uploaded??original,contentType:uploadedType??'image/png'}));
  await page.goto('http://localhost:5188',{waitUntil:'networkidle',timeout:90000});await page.waitForFunction(()=>window.__pasteAudit);await page.evaluate(v=>window.__pasteAudit.setup(v.temporary,v.compression,v.mode),test);await page.waitForTimeout(100);
  await page.evaluate(async name=>{const blob=await(await fetch('/paste-test-source')).blob();window.__pasteFile=new File([blob],name,{type:blob.type});},test.name);
  await page.evaluate(()=>{for(const [prototype,method] of [[CanvasRenderingContext2D.prototype,'drawImage'],[HTMLCanvasElement.prototype,'toDataURL']]){const original=prototype[method];prototype[method]=function(...args){const start=performance.now();const value=original.apply(this,args);if(window.__pasteMetrics)(window.__pasteMetrics.canvas??=[]).push({method,duration:performance.now()-start});return value;};}});
  await page.evaluate(()=>{window.__pasteMetrics={tasks:[],frames:[],dataReads:0,dataFetches:[],start:performance.now()};const m=window.__pasteMetrics;const read=FileReader.prototype.readAsDataURL;FileReader.prototype.readAsDataURL=function(...args){m.dataReads++;return read.apply(this,args);};const fetchOriginal=window.fetch;window.fetch=function(...args){const start=performance.now();const p=fetchOriginal.apply(this,args);if(typeof args[0]==='string'&&args[0].startsWith('data:'))m.dataFetches.push(performance.now()-start);return p;};window.__pasteObserver=new PerformanceObserver(list=>m.tasks.push(...list.getEntries().map(e=>({duration:e.duration,start:e.startTime}))));window.__pasteObserver.observe({type:'longtask'});let previous=performance.now();const frame=()=>{const now=performance.now();m.frames.push(now-previous);previous=now;if(!m.stopped)requestAnimationFrame(frame);};requestAnimationFrame(frame);const data=new DataTransfer();data.items.add(window.__pasteFile);document.querySelector('#chat-input').dispatchEvent(new ClipboardEvent('paste',{clipboardData:data,bubbles:true,cancelable:true}));});
  await page.waitForFunction(()=>{const f=window.__pasteAudit.state()[0];return f&&(f.status==='uploaded'||f.type==='image'&&f.url?.startsWith('data:'));},{timeout:30000});
  await page.waitForFunction(()=>[...document.querySelectorAll('.attachment-thumbnail img')].some(e=>e.complete&&e.naturalWidth>0&&!e.classList.contains('invisible')),{timeout:30000});await page.waitForTimeout(100);
  const metrics=await page.evaluate(()=>{const m=window.__pasteMetrics;m.stopped=true;window.__pasteObserver.disconnect();return{...m,state:window.__pasteAudit.state(),elapsed:performance.now()-m.start};});
  if(!test.temporary&&!test.compression)assert.equal(createHash('sha256').update(uploaded).digest('hex'),createHash('sha256').update(original).digest('hex'),'Upload bytes changed without compression');
  if(test.compression){const pixels=await page.evaluate(async()=>{
   const original=window.__pasteFile;const image=new Image();const source=URL.createObjectURL(original);image.src=source;await image.decode();const width=Math.min(1024,image.naturalWidth),height=Math.round(width*image.naturalHeight/image.naturalWidth);const expected=document.createElement('canvas');expected.width=width;expected.height=height;expected.getContext('2d').drawImage(image,0,0,width,height);const encoded=await(await fetch(expected.toDataURL(original.type))).blob();URL.revokeObjectURL(source);
   const data=async blob=>{const bitmap=await createImageBitmap(blob);const canvas=document.createElement('canvas');canvas.width=bitmap.width;canvas.height=bitmap.height;canvas.getContext('2d').drawImage(bitmap,0,0);bitmap.close();return{width:canvas.width,height:canvas.height,pixels:canvas.getContext('2d').getImageData(0,0,canvas.width,canvas.height).data};};const actualSource=window.__pasteAudit.state()[0]?.type==='image'?window.__pasteAudit.source():'/api/v1/files/paste-fixture/content';const actual=await data(await(await fetch(actualSource)).blob());const baseline=await data(encoded);let error=0,max=0;for(let i=0;i<actual.pixels.length;i++){const delta=Math.abs(actual.pixels[i]-baseline.pixels[i]);error+=delta;max=Math.max(max,delta);}return{width:actual.width,height:actual.height,mean:error/actual.pixels.length,max};
  });console.log('PIXELS',test.name,JSON.stringify(pixels));assert.deepEqual([pixels.width,pixels.height],test.name==='small.png'?[960,540]:[1024,576]);assert.ok(pixels.mean<0.1,'Compressed pixels differ from native canvas baseline');metrics.pixels=pixels;if(!test.temporary)assert.equal(uploadedType,test.name.endsWith('.jpg')?'image/jpeg':'image/png');if(test.name==='small.png')assert.equal(createHash('sha256').update(uploaded).digest('hex'),createHash('sha256').update(original).digest('hex'));}
  if(process.env.PASTE_ASSERT&&!test.temporary&&!test.compression){assert.equal(metrics.dataReads,0);assert.equal(metrics.dataFetches.length,0);}
  assert.deepEqual(errors,[]);const row={width,...test,bytes:original.length,uploadedBytes:uploaded?.length,metrics};results.push(row);console.log(JSON.stringify(row));await page.screenshot({path:out+'/'+(process.env.PASTE_LABEL??'run')+'-'+width+'-'+test.name+'-'+test.temporary+'-'+test.compression+'-'+test.mode+'.png'});await page.close();
 }
 await fs.writeFile(out+'/'+(process.env.PASTE_LABEL??'run')+'-results.json',JSON.stringify(results,null,2));
}finally{await browser?.close();await server?.close();}
