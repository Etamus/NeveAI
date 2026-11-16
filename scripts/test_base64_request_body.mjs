import fs from 'node:fs/promises';
import {createHash} from 'node:crypto';
import assert from 'node:assert/strict';
import {createServer} from 'vite';
import {chromium} from '../logs/ui-image-26/node_modules/playwright/index.mjs';

const image='data:image/png;base64,'+(await fs.readFile('backend/data/uploads/0e335168-40a8-473e-a233-1dd5f1cfb0c6_image.png')).toString('base64');
const file={type:'image',url:image};
const body={messages:[{role:'user',content:[{type:'text',text:'Edit'},{type:'image_url',image_url:{url:image}}]}],files:[file],parent_message:{content:'Edit',files:[file]},features:{stable_diffusion:true},chat_id:'local:benchmark'};
const original=JSON.stringify(body), expected=createHash('sha256').update(original).digest('hex');
const server=await createServer({plugins:[{name:'body-benchmark',configureServer(server){server.middlewares.use(async(req,res,next)=>{
 if(req.url==='/__body-bench'){res.setHeader('Content-Type','text/html');res.end('<script type="module">import {prepareChatRequestBody} from "/src/lib/utils/chatRequestBody.ts";window.prepareChatRequestBody=prepareChatRequestBody;</script>');return;}
 if(req.url==='/__body-echo'){const hash=createHash('sha256');let bytes=0;for await(const chunk of req){hash.update(chunk);bytes+=chunk.length;}res.setHeader('Content-Type','application/json');res.end(JSON.stringify({hash:hash.digest('hex'),bytes}));return;}next();
});}}],server:{port:5194,strictPort:true}});
let browser;
try{
 await server.listen();browser=await chromium.launch();const page=await browser.newPage();
 await page.goto('http://localhost:5194/__body-bench');await page.waitForFunction(()=>window.prepareChatRequestBody);
 await page.evaluate(body=>window.__body=body,body);
 const results=[];
 for(let round=0;round<3;round++)for(const worker of [false,true]){
  const result=await page.evaluate(async worker=>{
   const gaps=[],tasks=[];let previous=performance.now(),id;
   const observer=new PerformanceObserver(list=>tasks.push(...list.getEntries().map(e=>e.duration)));observer.observe({type:'longtask'});
   function frame(now){if(now-previous>40)gaps.push(now-previous);previous=now;id=requestAnimationFrame(frame);}id=requestAnimationFrame(frame);
   await new Promise(r=>setTimeout(r,100));const begin=performance.now();
   const body=worker?await window.prepareChatRequestBody(window.__body):JSON.stringify(window.__body);
   const response=await fetch('/__body-echo',{method:'POST',headers:{'Content-Type':'application/json'},body});
   const echo=await response.json(),ms=performance.now()-begin;
   await new Promise(r=>setTimeout(r,100));cancelAnimationFrame(id);observer.disconnect();
   return {worker,ms,gaps,tasks,echo};
  },worker);
  assert.equal(result.echo.hash,expected);assert.equal(result.echo.bytes,Buffer.byteLength(original));results.push(result);
 }
 await fs.writeFile('logs/base64-request-body-browser.json',JSON.stringify(results,null,2));console.log(JSON.stringify(results));
}finally{await browser?.close();await server.close();}
