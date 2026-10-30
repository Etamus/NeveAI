import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
import {constants} from 'node:fs';
import {createServer} from 'vite';
import {chromium} from '../logs/ui-image-26/node_modules/playwright/index.mjs';
const dir=new URL('../src/routes/__monotonic_test/',import.meta.url),file=new URL('+page.svelte',dir);
await fs.mkdir(dir,{recursive:true});await fs.copyFile(new URL('./fixtures/streaming-tools.svelte',import.meta.url),file,constants.COPYFILE_EXCL);
let server,browser;const results=[];
try{
 server=await createServer({server:{port:5188,strictPort:true,watch:{ignored:['**/logs/**']}}});await server.listen();
 browser=await chromium.launch();const page=await browser.newPage({viewport:{width:1000,height:900}});
 await page.route('**/__tool_embed',r=>r.fulfill({contentType:'text/html',body:'<!doctype html><body>Output</body>'}));
 await page.goto('http://localhost:5188/__monotonic_test',{waitUntil:'networkidle'});await page.waitForFunction(()=>window.__streamingToolsReady);
 const cases=[
  'The first words and **bold text** continue normally.',
  'The first words and *italic text* continue normally.',
  'The first words and `inline code` continue normally.',
  'The first words and [a linked label](https://example.com) continue normally.',
  'An introduction.\n\n1. First numbered item\n2. Another **formatted** item\n\nFollowing paragraph.',
  'An introduction.\n\n| Name | Value |\n| --- | --- |\n| First | Second |\n\nFollowing paragraph.',
  'Text with ~~deleted words~~ followed by normal words.',
  'Counting 109 items and 234 values without changing the numbers.',
 ];
 for(const content of cases){
  await page.evaluate(()=>window.dispatchEvent(new CustomEvent('neve-test-stream',{detail:{content:'',done:true}})));await page.waitForTimeout(100);
  const frames=await page.evaluate(async content=>{
   const frames=[];let previous='';const root=document.querySelector('#stream');
   for(let i=1;i<=content.length;i++){
    window.dispatchEvent(new CustomEvent('neve-test-stream',{detail:{content:content.slice(0,i),done:false}}));
    await new Promise(r=>setTimeout(r,85));
    const text=root.textContent??'';let prefix=0;while(prefix<previous.length&&previous[prefix]===text[prefix])prefix++;
    const oldHighlights=[];
    for(const name of CSS.highlights.keys())for(const range of CSS.highlights.get(name)){
     if(!root.contains(range.startContainer))continue;
     const before=document.createRange();before.selectNodeContents(root);before.setEnd(range.startContainer,range.startOffset);
     const start=before.toString().length;
     if(start<prefix)oldHighlights.push({start,end:start+range.toString().length,text:range.toString()});
    }
    frames.push({i,text,previous,prefix,oldHighlights});previous=text;
   }
   window.dispatchEvent(new CustomEvent('neve-test-stream',{detail:{content,done:true}}));return frames;
  },content);
  results.push({content,frames,refades:frames.filter(f=>f.oldHighlights.length),retreats:frames.filter(f=>{const letters=s=>s.replace(content.includes('1. First')?/[^\p{L}]/gu:/[^\p{L}\p{N}]/gu,'');return !letters(f.text).startsWith(letters(f.previous));})});
 }
 await fs.writeFile(process.env.MONOTONIC_RESULT??'logs/landing-investigation/monotonic-before.json',JSON.stringify(results,null,2));
 console.log(JSON.stringify(results.map(({content,refades,retreats})=>({content,refades,retreats})),null,2));
 if(process.env.MONOTONIC_ASSERT){assert(results.every(r=>!r.refades.length),'Already-visible text was made transparent again');assert(results.every(r=>!r.retreats.length),'Visible words retreated during append-only streaming');}
}finally{await browser?.close();await server?.close();await fs.unlink(file);await fs.rmdir(dir);}
