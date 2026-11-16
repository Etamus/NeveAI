import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
import {chromium} from '../logs/ui-image-26/node_modules/playwright/index.mjs';

const browser=await chromium.launch();
const results=[];
async function geometry(locator){return locator.evaluate(svg=>{
 const box=svg.getBBox(),matrix=svg.getScreenCTM();
 const first=new DOMPoint(box.x,box.y).matrixTransform(matrix),last=new DOMPoint(box.x+box.width,box.y+box.height).matrixTransform(matrix);
 const button=svg.closest('button').getBoundingClientRect(),rect=svg.getBoundingClientRect(),css=getComputedStyle(svg);
 return {width:last.x-first.x,height:last.y-first.y,paintedWidth:last.x-first.x+(css.stroke==='none'?0:parseFloat(css.strokeWidth)*Math.hypot(matrix.a,matrix.b)),color:css.color,fill:css.fill,stroke:css.stroke,strokeWidth:css.strokeWidth,
  buttonOffset:{x:(first.x+last.x-button.left-button.right)/2,y:(first.y+last.y-button.top-button.bottom)/2},
  viewportOffset:{x:(first.x+last.x-rect.left-rect.right)/2,y:(first.y+last.y-rect.top-rect.bottom)/2}};
});}
try{
 for(const mobile of [false,true])for(const theme of ['dark','light']){
  const context=await browser.newContext({viewport:mobile?{width:390,height:844}:{width:1440,height:1000},deviceScaleFactor:mobile?2:1,colorScheme:theme});
  const page=await context.newPage(),errors=[];page.on('pageerror',error=>errors.push(error.message));
  await page.addInitScript(theme=>localStorage.setItem('theme',theme),theme);
  await page.route('**/api/v1/users/user/settings/update',route=>route.fulfill({json:route.request().postDataJSON()}));
  await page.goto('http://127.0.0.1:8080/?temporary-chat=true',{waitUntil:'networkidle'});
  const model=page.getByRole('button',{name:'Models',exact:true}).locator('svg');
  await model.waitFor();
  const modelGeometry=await geometry(model);
  console.log('MODELS',mobile,theme,modelGeometry);
  const adjacentGeometry=await geometry(page.locator('#temporary-chat-button svg'));
  assert(Math.abs(modelGeometry.buttonOffset.x)<.75 && Math.abs(modelGeometry.buttonOffset.y)<.75,'Models icon must be centered');
  assert(Math.abs(modelGeometry.paintedWidth-adjacentGeometry.paintedWidth)<1.5,'Models glyph must match adjacent glyph dimensions');
  assert.equal(modelGeometry.color,adjacentGeometry.color);
  await page.locator('.chat-navbar-actions').screenshot({path:`logs/requested-icons-${mobile?'mobile':'desktop'}-${theme}-navbar.png`});
  await page.locator('#input-menu-button').click();
  const learn=page.getByText('Aprender',{exact:true}).locator('xpath=ancestor::button[1]');
  const learnGeometry=await geometry(learn.locator('svg').first());
  const web=page.getByText('Busca na web',{exact:true}).locator('xpath=ancestor::button[1]');
  const webGeometry=await geometry(web.locator('svg').first());
  assert.equal(learnGeometry.color,webGeometry.color);
  assert.equal(learnGeometry.strokeWidth,webGeometry.strokeWidth);
  assert(Math.abs(learnGeometry.width-webGeometry.width)<2,'Learn glyph should match menu icon scale');
  await page.screenshot({path:`logs/requested-icons-${mobile?'mobile':'desktop'}-${theme}-menu.png`});
  await learn.click();
  await page.locator('#message-input-container').screenshot({path:`logs/requested-icons-${mobile?'mobile':'desktop'}-${theme}-chip.png`});
  assert.deepEqual(errors,[]);
  results.push({mobile,theme,model:modelGeometry,learn:learnGeometry,web:webGeometry,errors});
  await context.close();
 }
 await fs.writeFile('logs/requested-icons-results.json',JSON.stringify(results,null,2));console.log(JSON.stringify(results));
}finally{await browser.close();}
