import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {chromium} from '../logs/ui-image-26/node_modules/playwright/index.mjs';
import utils from '../logs/ui-image-26/node_modules/playwright-core/lib/utilsBundle.js';
import {installMobileOfflineApi} from './fixtures/mobile-offline-api.mjs';

const {PNG}=utils,phase=process.argv.includes('--before')?'before':'after';
const browser=await chromium.launch(),results=[];
try{
 for(const theme of ['dark','light'])for(const dpr of [1,1.25,1.5,2]){
  const page=await browser.newPage({viewport:{width:1440,height:1000},deviceScaleFactor:dpr});
  await installMobileOfflineApi(page);
  await page.addInitScript(theme=>{localStorage.setItem('neveai.language','pt-BR');localStorage.setItem('theme',theme)},theme);
  await page.goto('http://127.0.0.1:8080',{waitUntil:'networkidle',timeout:90000});
  await page.locator('#thinking-dropdown-container > button').click();await page.waitForTimeout(300);
  const button=page.locator('#reasoning-speed-control'),states=[];
  await button.hover();await page.waitForTimeout(200);
  for(let i=0;i<5;i++){
   if(i){
    await page.evaluate(()=>{
     window.__speedIconFrames=[];
     const sample=()=>{
      const button=document.querySelector('#reasoning-speed-control');
      window.__speedIconFrames.push(['button','svg','path'].map(part=>{
       const r=(part==='button'?button:button.querySelector(part)).getBoundingClientRect();
       return [r.x,r.y,r.width,r.height];
      }));
      if(window.__speedIconFrames.length<16)requestAnimationFrame(sample);
     };sample();
    });
    await button.click();await page.waitForFunction(()=>window.__speedIconFrames.length===16);
    const frames=await page.evaluate(()=>window.__speedIconFrames);
    const initial=['button','svg','path'].map(part=>['x','y','width','height'].map(axis=>states[0][part][axis]));
    for(const frame of frames)assert.deepEqual(frame,initial,'Geometry must not move even during the click');
   }
   await page.waitForTimeout(180);
   const geometry=await button.evaluate(button=>{
    const svg=button.querySelector('svg'),path=svg.querySelector('path');
    const rect=e=>{const r=e.getBoundingClientRect();return{x:r.x,y:r.y,width:r.width,height:r.height}};
    return {button:rect(button),svg:rect(svg),path:rect(path),color:getComputedStyle(button).color,mode:button.dataset.mode};
   });
   const buffer=await button.locator('svg').screenshot({path:`logs/speed-icon-${phase}-${theme}-${dpr}-${i}.png`}),png=PNG.sync.read(buffer);
   const rgb=geometry.color.match(/\d+/g).map(Number),bg=[...png.data.slice(0,3)];
   const diff=rgb.map((v,j)=>v-bg[j]),denom=diff.reduce((s,v)=>s+v*v,0);
   let weight=0,xsum=0,ysum=0,minX=png.width,maxX=-1,minY=png.height,maxY=-1;
   for(let y=0;y<png.height;y++)for(let x=0;x<png.width;x++){
    const p=(y*png.width+x)*4,alpha=Math.max(0,Math.min(1,diff.reduce((s,v,j)=>s+(png.data[p+j]-bg[j])*v,0)/denom));
    if(alpha>.1){weight+=alpha;xsum+=(x+.5)*alpha;ysum+=(y+.5)*alpha;minX=Math.min(minX,x);maxX=Math.max(maxX,x);minY=Math.min(minY,y);maxY=Math.max(maxY,y);}
   }
   states.push({...geometry,ink:{cx:xsum/weight/dpr,cy:ysum/weight/dpr,minX:minX/dpr,maxX:maxX/dpr,minY:minY/dpr,maxY:maxY/dpr}});
  }
  const original=states[0];
  for(const state of states.slice(1))for(const part of ['button','svg','path'])for(const axis of ['x','y','width','height'])assert.equal(state[part][axis],original[part][axis],`${theme}/${dpr}: ${part}.${axis} moved`);
  if(phase==='after'){
   assert.equal(original.button.width,32);assert.equal(original.button.height,32);
   assert.equal(original.svg.width,20);assert.equal(original.svg.height,20);
   for(const state of states.slice(1))assert(Math.abs(state.ink.cx-original.ink.cx)<.2&&Math.abs(state.ink.cy-original.ink.cy)<.2,'Rasterized ink should retain its optical center');
  }
  results.push({theme,dpr,states});console.log('PASS',theme,dpr,JSON.stringify(states.map(s=>s.ink)));
  await page.close();
 }
 await fs.writeFile(`logs/speed-icon-${phase}.json`,JSON.stringify(results,null,2));
}finally{await browser.close()}
