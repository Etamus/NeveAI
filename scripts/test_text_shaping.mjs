import fs from 'node:fs/promises';
import {constants} from 'node:fs';
import assert from 'node:assert/strict';
import {createServer} from 'vite';
import {chromium} from '../logs/ui-image-26/node_modules/playwright/index.mjs';
const dir=new URL('../src/routes/__shaping_test/',import.meta.url),file=new URL('+page.svelte',dir);
await fs.mkdir(dir,{recursive:true});await fs.copyFile(new URL('./fixtures/streaming-tools.svelte',import.meta.url),file,constants.COPYFILE_EXCL);
let server,browser;const results=[];
try{
 server=await createServer({server:{port:5188,strictPort:true,watch:{ignored:['**/logs/**','**/scripts/**','**/docs/**']}}});await server.listen();
 browser=await chromium.launch();
 for(const [name,viewport] of [['desktop',{width:1440,height:1000}],['narrow',{width:900,height:800}],['mobile',{width:390,height:844}]]){
  const page=await browser.newPage({viewport});page.setDefaultTimeout(60000);const errors=[];page.on('pageerror',e=>{errors.push(e.message);console.log('pageerror',e.message);});
  await page.route('**/__tool_embed',r=>r.fulfill({contentType:'text/html',body:'<!doctype html><html><body>Embedded output</body></html>'}));
  await page.goto('http://localhost:5188/__shaping_test',{waitUntil:'domcontentloaded',timeout:90000});await page.waitForFunction(()=>window.__streamingToolsReady);await page.locator('#stream p').waitFor();await page.evaluate(()=>document.fonts.ready);
  await page.evaluate(()=>document.documentElement.classList.add('dark'));
  if(process.env.SHAPING_CSS)await page.addStyleTag({content:process.env.SHAPING_CSS});
  const send=async(content,done)=>{await page.evaluate(detail=>window.dispatchEvent(new CustomEvent('neve-test-stream',{detail})),{content,done});await page.waitForTimeout(400);await page.evaluate(()=>document.fonts.ready);};
  const measure=()=>page.locator('#stream p').first().evaluate(p=>{
   const walker=document.createTreeWalker(p,NodeFilter.SHOW_TEXT),nodes=[];let node;while(node=walker.nextNode())nodes.push(node);
   const chars=[];for(const node of nodes)for(let i=0;i<node.textContent.length;i++){const char=node.textContent[i];if(/\s/.test(char))continue;const range=document.createRange();range.setStart(node,i);range.setEnd(node,i+1);const r=range.getBoundingClientRect();chars.push({char,x:r.x,y:r.y,w:r.width,h:r.height});}
   const r=p.getBoundingClientRect();return{text:p.textContent,chars,width:r.width,height:r.height,nodes:nodes.length};
  });
  const samples=[
   'Claro. Como voc\u00ea tem me dado a liberdade de escolher o tom, vou te levar para um lugar onde o conhecimento n\u00e3o est\u00e1 em livros, mas em sussurros e na pr\u00f3pria mem\u00f3ria do mundo.',
   'No cora\u00e7\u00e3o de um continente envolto em n\u00e9voa perp\u00e9tua, existia a Biblioteca dos Sussurros. N\u00e3o era constru\u00edda por m\u00e3os humanas, mas sim esculpida entre ra\u00edzes de \u00e1rvores ancestrais e rochas que guardavam a mem\u00f3ria do tempo.',
   'AV To WA typography affinity office efficient difficult. **Bold words and italic** plus *some emphasis* and a [normal link](https://example.com).',
   '\u0627\u0644\u0633\u0644\u0627\u0645 \u0639\u0644\u064a\u0643\u0645 \u0647\u0630\u0627 \u0627\u062e\u062a\u0628\u0627\u0631 \u062a\u0646\u0633\u064a\u0642 \u0627\u0644\u0646\u0635 with English words and punctuation.'
  ];
  for(const scale of [1,1.15,1.3])for(const [index,content] of samples.entries()){
   await page.evaluate(scale=>document.documentElement.style.setProperty('--app-text-scale',scale),scale);
   await send(content,false);const before=await measure();
   if(index===0&&scale===1.15)await page.screenshot({path:`logs/shaping-${name}-before.png`});
   await send(content,true);const after=await measure();assert.equal(after.text,before.text);assert.equal(after.chars.length,before.chars.length);
   const maxX=Math.max(...before.chars.map((c,i)=>Math.abs(c.x-after.chars[i].x))),maxY=Math.max(...before.chars.map((c,i)=>Math.abs(c.y-after.chars[i].y))),maxWidth=Math.max(...before.chars.map((c,i)=>Math.abs(c.w-after.chars[i].w)));
   const result={name,scale,index,maxX,maxY,maxWidth,nodesBefore:before.nodes,nodesAfter:after.nodes};results.push(result);console.log(JSON.stringify(result));
   if(index===0&&scale===1.15)await page.screenshot({path:`logs/shaping-${name}-after.png`});
   if(process.env.SHAPING_ASSERT)assert(maxX===0&&maxY===0&&maxWidth===0,JSON.stringify(result));
  }
  assert.deepEqual(errors,[]);await page.close();
 }
 await fs.writeFile(process.env.SHAPING_RESULT??'logs/text-shaping-results.json',JSON.stringify(results,null,2));
}finally{await browser?.close();await server?.close();await fs.unlink(file);await fs.rmdir(dir);}
