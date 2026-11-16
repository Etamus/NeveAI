import fs from 'node:fs/promises';
import {constants} from 'node:fs';
import assert from 'node:assert/strict';
import {createServer} from 'vite';
import {chromium} from '../logs/ui-image-26/node_modules/playwright/index.mjs';
import sharp from 'sharp';
import {installMobileOfflineApi} from './fixtures/mobile-offline-api.mjs';

const directory=new URL('../src/routes/__editor_scroll_end/',import.meta.url),file=new URL('+page.svelte',directory),output='logs/editor-scroll-end';
let server,browser,page;
const results=[];
const inkCenter=async(locator,firstLine=false)=>{
 const box=await locator.boundingBox(),limit=firstLine?await locator.evaluate(el=>parseFloat(getComputedStyle(el).lineHeight)):box.height;
 const {data,info}=await sharp(await locator.screenshot()).ensureAlpha().raw().toBuffer({resolveWithObject:true});let top=info.height,bottom=-1;
 for(let y=0;y<Math.min(info.height,limit);y++)for(let x=0;x<info.width;x++){const i=(y*info.width+x)*4;if(data[i]>100&&data[i+1]>100&&data[i+2]>100){top=Math.min(top,y);bottom=Math.max(bottom,y);}}
 return box.y+(top+bottom)/2;
};
await fs.mkdir(directory,{recursive:true});await fs.copyFile(new URL('./fixtures/models-grid.svelte',import.meta.url),file,constants.COPYFILE_EXCL);
try{
 await fs.mkdir(output,{recursive:true});
 server=await createServer({cacheDir:'node_modules/.vite-editor-scroll-end',plugins:[{name:'editor-scroll-fixture',configResolved(config){config.server.proxy=undefined;}}],server:{port:5197,strictPort:true,watch:{ignored:['**/logs/**','**/scripts/**']}}});
 await server.listen();browser=await chromium.launch();
 for(const width of [1440,1024,768,390]){
  page=await browser.newPage({viewport:{width,height:1000}});page.setDefaultTimeout(15000);const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await installMobileOfflineApi(page);let local=[],admin=[];
  await page.route('**/llamacpp/models',route=>route.fulfill({json:{models:local}}));
  await page.route('**/api/v1/models/base',route=>route.fulfill({json:admin}));
  await page.route('**/api/models',route=>route.fulfill({json:{data:admin}}));
  await page.goto('http://localhost:5197/__editor_scroll_end',{waitUntil:'networkidle'});
  ({local,admin}=await page.evaluate(()=>({local:window.__gridFixture.local,admin:window.__gridFixture.admin})));
  const originalId='Qwen-Original-Model-Name-With-More-Than-Forty-Characters-Q4_K_M';
  const editableName='Editable model name with a muchWider existing display title for testing';
  admin[0].name=editableName;
  admin[0].id=`local/${originalId}`;local[0].id=`local/${originalId}`;local[0].filename=`${originalId}.gguf`;
  await page.evaluate(({originalId,editableName})=>{window.__gridFixture.admin[0].name=editableName;window.__gridFixture.admin[0].id=`local/${originalId}`;window.__gridFixture.local[0].id=`local/${originalId}`;window.__gridFixture.local[0].filename=`${originalId}.gguf`;document.documentElement.classList.add('dark');return window.__gridFixture.open();},{originalId,editableName});
  await page.locator('[data-model-grid] .unified-model-name').first().click();const editor=page.locator('.unified-model-editor');await editor.waitFor();
  const panel=editor.locator('.model-editor-advanced-params-window');
  await editor.locator('[data-model-editable-name]').waitFor();
  const typography=await editor.evaluate(el=>({root:parseFloat(getComputedStyle(document.documentElement).fontSize),name:parseFloat(getComputedStyle(el.querySelector('[data-model-editable-name]')).fontSize),original:parseFloat(getComputedStyle(el.querySelector('[data-model-original-id]')).fontSize),description:parseFloat(getComputedStyle(el.querySelector('.model-editor-identity textarea')).fontSize)}));
  assert(Math.abs(typography.name-typography.root*1.5625)<.1,'editable name increased to 25px at normal scale');
  assert(Math.abs(typography.original-typography.root*.875)<.1,'original name increased to 14px at normal scale');
  assert.equal(typography.description,16,'description increased to 16px');
  const editableTitle=editor.getByPlaceholder('Model Name',{exact:true});
  await page.waitForFunction(()=>document.querySelector('[data-model-editable-name]')?.value.length>0);
  const assertWholeName=async()=>{
   const value=await editableTitle.inputValue();
   assert(value.length<=30&&editableName.startsWith(value),'display is a whole-character prefix of at most thirty characters, including spaces');
   const fit=await editableTitle.evaluate(el=>{const sizer=el.parentElement.querySelector('[aria-hidden="true"]'),range=document.createRange();range.setStart(sizer.firstChild,0);range.setEnd(sizer.firstChild,el.value.length);return {width:range.getBoundingClientRect().width,available:el.clientWidth,scroll:el.scrollLeft};});
   assert(fit.width+3<=fit.available,'the final visible character fits completely');assert.equal(fit.scroll,0,'unfocused title is never horizontally scrolled');
  };
  await assertWholeName();
  const nameHint=editor.locator('[data-model-name-edit-hint]'),descriptionHint=editor.locator('[data-model-description-edit-hint]'),description=editor.getByRole('textbox',{name:'Description',exact:true});
  await page.mouse.move(0,0);
  assert.equal(await nameHint.evaluate(el=>getComputedStyle(el).opacity),'0','name pencil hidden without hover');
  assert.equal(await descriptionHint.evaluate(el=>getComputedStyle(el).opacity),'0','description pencil hidden without hover');
  const fieldBounds=await editableTitle.boundingBox();
  assert(Math.abs(fieldBounds.x-(await editor.locator('[data-model-original-id]').boundingBox()).x+2)<.1,'only the editable name starts two pixels farther left');
  await editableTitle.hover();assert.equal(await nameHint.evaluate(el=>getComputedStyle(el).opacity),'1','name hover reveals edit pencil');
  assert.deepEqual(await editableTitle.boundingBox(),fieldBounds,'pencil does not move or resize the name field');
  const namePencilBounds=await nameHint.boundingBox();assert(namePencilBounds.x>=fieldBounds.x+fieldBounds.width,'name pencil stays outside editable text');
  await page.screenshot({path:`${output}/${width}-name-pencil.png`});
  const nameInkOffset=(await inkCenter(nameHint.locator('svg')))-(await inkCenter(editableTitle));
  console.log('name pencil ink offset',width,nameInkOffset);assert(Math.abs(nameInkOffset)<1.1,'name pencil optically centered on actual text');
  await description.hover();assert.equal(await descriptionHint.evaluate(el=>getComputedStyle(el).opacity),'1','description hover reveals its pencil');
  assert.equal(await nameHint.evaluate(el=>getComputedStyle(el).opacity),'0','name pencil disappears when pointer leaves');
  await page.screenshot({path:`${output}/${width}-description-pencil.png`});
  const assertDescriptionEnd=async()=>{
   const position=await description.evaluate(el=>{
    const hint=el.parentElement.querySelector('[data-model-description-edit-hint]'),style=getComputedStyle(el),mirror=document.createElement('div');
    Object.assign(mirror.style,{position:'fixed',left:'-10000px',visibility:'hidden',width:`${el.clientWidth-parseFloat(style.paddingLeft)-parseFloat(style.paddingRight)}px`,font:style.font,lineHeight:style.lineHeight,letterSpacing:style.letterSpacing,whiteSpace:style.whiteSpace,wordBreak:style.wordBreak,overflowWrap:style.overflowWrap});
    mirror.textContent=(el.value||el.placeholder)+'\u200b';document.body.append(mirror);const range=document.createRange();range.selectNodeContents(mirror);const lines=[...range.getClientRects()],last=lines.at(-1),lineHeight=parseFloat(style.lineHeight),index=Math.round((last.top-lines[0].top)/lineHeight),box=el.getBoundingClientRect(),h=hint.getBoundingClientRect();
    const x=Math.min(box.x+parseFloat(style.paddingLeft)+last.right-mirror.getBoundingClientRect().left+6,el.parentElement.getBoundingClientRect().right-h.width),y=box.y+parseFloat(style.paddingTop)+lineHeight*(index+.5)-el.scrollTop+2,visible=y-box.y>=h.height/2&&y-box.y<=el.clientHeight-h.height/2+.5;
    mirror.remove();return {x,y,actualX:h.x,actualY:h.y+h.height/2,index,lineHeight,visible,visibility:getComputedStyle(hint).visibility};
   });
   assert.equal(position.visibility,position.visible?'visible':'hidden','end hint is clipped when its line is outside the textarea');
   assert(Math.abs(position.actualX-position.x)<1&&Math.abs(position.actualY-position.y)<1,'pencil tracks the text end after wrapping and scrolling');return position;
  };
  await assertDescriptionEnd();
  const originalDescription=await description.inputValue();
  await description.fill('Curta.');await description.hover();await page.waitForTimeout(80);
  await assertDescriptionEnd();
  await description.fill('Primeira linha.\nFinal.');await description.evaluate(el=>el.scrollTop=0);await page.waitForTimeout(80);
  const twoLines=await assertDescriptionEnd();assert.equal(twoLines.index,1,'pencil moves to the second line rather than staying on the first');assert(twoLines.visible);
  const lastLineGap=await description.evaluate(el=>{const hint=el.parentElement.querySelector('[data-model-description-edit-hint]'),style=getComputedStyle(el),mirror=document.createElement('span');mirror.style.cssText='position:fixed;visibility:hidden;white-space:pre;';mirror.style.font=style.font;mirror.textContent=el.value.split('\n').at(-1);document.body.append(mirror);const width=mirror.getBoundingClientRect().width;mirror.remove();return hint.getBoundingClientRect().left-el.getBoundingClientRect().left-parseFloat(style.paddingLeft)-width;});
  assert(Math.abs(lastLineGap-6)<1,'six-pixel gap is preserved after the last word');
  await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
  await page.screenshot({path:`${output}/${width}-description-last-line-pencil.png`});
  await description.fill('Uma descricao suficientemente longa para quebrar de linha e terminar bem aqui.');await description.evaluate(el=>el.scrollTop=el.scrollHeight);await page.waitForTimeout(80);
  const wrapped=await assertDescriptionEnd();assert(wrapped.index>=1&&wrapped.visible,'pencil follows the final automatically wrapped line');
  await description.evaluate(el=>el.scrollTop=0);await page.waitForTimeout(80);await assertDescriptionEnd();
  await description.fill('Final.\n');await page.waitForTimeout(80);assert.equal((await assertDescriptionEnd()).index,1,'trailing newline places the pencil at the new line end');
  await description.fill(originalDescription);await page.waitForTimeout(80);
  await page.mouse.move(0,0);assert.equal(await descriptionHint.evaluate(el=>getComputedStyle(el).opacity),'0','description pencil disappears on exit');
  if(width===1440)assert.equal(await editableTitle.inputValue(),editableName.slice(0,30),'desktop shows exactly thirty characters, spaces included');
  assert.equal(await editableTitle.getAttribute('maxlength'),'50','editing limit remains unchanged');
  await editableTitle.focus();assert.equal(await editableTitle.inputValue(),editableName.slice(0,50),'focus preserves existing editing logic');
  await page.waitForTimeout(80);
  if(width===1440){
   const focusedFit=await editableTitle.evaluate(el=>{const sizer=el.parentElement.querySelector('[aria-hidden="true"]'),range=document.createRange();range.setStart(sizer.firstChild,0);range.setEnd(sizer.firstChild,31);return {count:sizer.textContent.length,width:range.getBoundingClientRect().width,available:el.clientWidth};});
   assert.equal(focusedFit.count,50,'measurement uses the same text shaping as the editable full name');
   assert(focusedFit.width+3<=focusedFit.available,'the thirty-first character fits entirely while editing');
   await editableTitle.evaluate(el=>{el.setSelectionRange(0,0);el.scrollLeft=0;});
   await page.screenshot({path:`${output}/${width}-focused-extra-character.png`});
   await editableTitle.evaluate(el=>el.style.caretColor='transparent');
   const fullPixels=await sharp(await editableTitle.screenshot()).raw().toBuffer();
   await editableTitle.evaluate(el=>{el.value=el.value.slice(0,31);el.setSelectionRange(0,0);el.scrollLeft=0;});
   const referencePixels=await sharp(await editableTitle.screenshot()).raw().toBuffer();
   const extraPixels=fullPixels.reduce((count,value,index)=>count+(value!==referencePixels[index]?1:0),0);
   console.log('focused extra character pixel difference',width,extraPixels);
   await editableTitle.evaluate((el,value)=>{el.value=value;el.setSelectionRange(0,0);el.scrollLeft=0;},editableName.slice(0,50));
   if(!process.argv.includes('--measure-focus'))assert.equal(extraPixels,0,'rendering a long name matches exactly thirty-one characters, with no piece of character thirty-two');
  }
  await editableTitle.evaluate(el=>{el.scrollLeft=el.scrollWidth;el.blur();});await page.waitForTimeout(80);await assertWholeName();
  if(width===1440)assert.equal(await editableTitle.inputValue(),editableName.slice(0,30),'blur keeps the original thirty-character display');
  assert.equal(await page.evaluate(()=>window.__gridFixture.admin[0].name),editableName,'display clipping never truncates the stored name');
  const originalName=editor.locator('[data-model-original-id]');
  assert.equal(await originalName.inputValue(),originalId.slice(0,40)+'...','original name displays forty characters before ellipsis');
  assert.equal(await originalName.getAttribute('title'),originalId,'complete model ID is preserved');
  assert.equal(await page.evaluate(()=>window.__gridFixture.admin[0].id),`local/${originalId}`,'visual truncation never edits model identity');
  if(width>=768){
   const offsets=await panel.evaluate(el=>{const root=el.querySelector('.advanced-params'),top=root.getBoundingClientRect().top;return [...root.children].filter(row=>row.getBoundingClientRect().height>0).map(row=>row.getBoundingClientRect().top-top);});
   await panel.hover();
   for(let step=1;step<=3;step++){await page.mouse.wheel(0,120);await page.waitForTimeout(80);assert(Math.abs(await panel.evaluate(el=>el.scrollTop)-offsets[step])<1,'wheel advances one complete parameter row');}
   await page.mouse.wheel(0,-120);await page.waitForTimeout(80);assert(Math.abs(await panel.evaluate(el=>el.scrollTop)-offsets[2])<1,'reverse wheel aligns parameter rows');
   const native=await panel.evaluate(el=>{const e=new WheelEvent('wheel',{deltaY:4,cancelable:true,bubbles:true});el.dispatchEvent(e);return !e.defaultPrevented;});assert(native,'fine trackpad input remains native');
   await page.screenshot({path:`${output}/${width}-wheel.png`});
  }
  await panel.evaluate(el=>el.scrollTop=el.scrollHeight);
  const measure=()=>panel.evaluate(el=>{
   const box=el.getBoundingClientRect(),root=el.querySelector('.advanced-params');
   const children=[...root.children].map(child=>{const r=child.getBoundingClientRect();return {tag:child.tagName,text:child.textContent.trim().slice(0,45),height:r.height,y:r.top-box.top,bottom:r.bottom-box.top,margin:getComputedStyle(child).marginTop};});
   return {height:el.clientHeight,max:getComputedStyle(el).maxHeight,scrollHeight:el.scrollHeight,scrollTop:el.scrollTop,children,tail:box.bottom-root.getBoundingClientRect().bottom};
  });
  const closed=await measure();
  await page.screenshot({path:`${output}/${width}-${process.argv.includes('--measure')?'before':'after'}.png`});
  if(!process.argv.includes('--measure')){
   if(width>=768){assert.equal(closed.max,'282px');assert.equal(closed.height,282);}
   const emptyTail=closed.children.filter(row=>!row.text);assert.equal(emptyTail.length,0,'no empty custom-parameter block after closed prompt');
   if(width>=768){const first=closed.children.find(row=>row.text&&row.bottom>0);assert(first.y>=-.5,'first visible row is not clipped at the lower scroll limit');}
   const systemRow=editor.getByText('Prompt do sistema',{exact:true}).locator('..');
   await systemRow.getByRole('button',{name:'Default',exact:true}).click();await editor.locator('[data-model-system-prompt] textarea').waitFor();
   await panel.evaluate(el=>el.scrollTop=el.scrollHeight);const opened=await measure();
   if(width>=768)assert.equal(opened.height,closed.height,'visible list height unchanged on expansion');
   await editor.getByRole('button',{name:'Prompt do sistema',exact:true}).click();await panel.evaluate(el=>el.scrollTop=el.scrollHeight);
   assert.deepEqual(await measure(),closed,'closing restores scroll extent without altering parameters');
  }
  const parameterRows=panel.locator('.advanced-params > .flex:not(.flex-col)');
  await parameterRows.evaluateAll(rows=>rows.forEach(row=>row.querySelector(':scope > button')?.click()));
  const controls=[];
  const savedScale=await page.evaluate(()=>document.documentElement.style.getPropertyValue('--app-text-scale'));
  for(const theme of ['dark','light'])for(const scale of [1,1.15,1.5]){
   await page.evaluate(({theme,scale})=>{document.documentElement.classList.toggle('dark',theme==='dark');document.documentElement.classList.toggle('light',theme==='light');document.documentElement.style.setProperty('--app-text-scale',String(scale));},{theme,scale});
   await page.waitForTimeout(80);await assertWholeName();
   const geometry=await parameterRows.evaluateAll(rows=>rows.map(row=>{
    const r=row.getBoundingClientRect(),input=row.querySelector('input[type="number"]'),c=input.parentElement.getBoundingClientRect(),i=input.getBoundingClientRect(),buttons=[...input.parentElement.querySelectorAll('button')].map(button=>{const b=button.getBoundingClientRect(),svg=button.querySelector('svg').getBoundingClientRect();return {height:b.height,iconY:svg.top+svg.height/2-b.top-b.height/2};});
    return {name:row.querySelector('.inline-tooltip').textContent.trim(),top:r.top,height:r.height,controlHeight:c.height,inputHeight:i.height,inputY:i.top-c.top,controlY:c.top-r.top,clipped:Math.max(0,r.top-c.top,c.bottom-r.bottom),phase:c.top-Math.floor(c.top),buttons};
   }));
   controls.push({theme,scale,geometry});
   if(!process.argv.includes('--measure-controls')){
    assert.equal(geometry.length,10,'all ten numeric controls rendered');
    for(const row of geometry){
     for(const key of ['controlHeight','inputHeight','inputY'])assert(Math.abs(row[key]-geometry[0][key])<.1,`${key} consistent throughout parameters`);
     assert(row.clipped<.1,'numeric controls never exceed row bounds');
     for(const button of row.buttons)assert(Math.abs(button.iconY)<.1,'plus and minus icons stay centered');
     if(width>=768){assert(Math.abs(row.height-geometry[0].height)<.1,'desktop parameter rows have equal heights');assert(Math.abs(row.phase-geometry[0].phase)<.1,'row placement does not accumulate fractional pixel drift');}
    }
   }
   await panel.evaluate(el=>el.scrollTop=el.scrollHeight);
   await page.screenshot({path:`${output}/${width}-${theme}-${scale}-controls-${process.argv.includes('--measure-controls')?'before':'after'}.png`});
  }
  await page.evaluate(scale=>{if(scale)document.documentElement.style.setProperty('--app-text-scale',scale);else document.documentElement.style.removeProperty('--app-text-scale');},savedScale);
  const temperature=parameterRows.first().locator('input[type="number"]');
  await temperature.scrollIntoViewIfNeeded();const oldValue=Number(await temperature.inputValue());
  await parameterRows.first().getByRole('button',{name:'Increase',exact:true}).click();assert(Math.abs(Number(await temperature.inputValue())-oldValue-.05)<.001,'increment still changes the parameter');
  await parameterRows.first().getByRole('button',{name:'Decrease',exact:true}).click();assert.equal(Number(await temperature.inputValue()),oldValue,'decrement restores the value');
  if(width===1440)for(const theme of ['dark','light'])for(const [index,name] of [
   'Neve Cascade 5 1B Qat Q4 0'.padEnd(30,' ')+' WIDER title',
   'Neve Cascade 5 1B Qat Q4 0   Copia (10)'
  ].entries()){
   await page.evaluate(theme=>{document.documentElement.classList.toggle('dark',theme==='dark');document.documentElement.classList.toggle('light',theme==='light');},theme);
   await editableTitle.fill(name);await page.waitForTimeout(80);
   await editableTitle.evaluate(el=>{el.setSelectionRange(0,0);el.scrollLeft=0;});
   const full=await sharp(await editableTitle.screenshot()).raw().toBuffer();
   await editableTitle.evaluate(el=>{el.value=el.value.slice(0,31);el.setSelectionRange(0,0);el.scrollLeft=0;});
   const reference=await sharp(await editableTitle.screenshot()).raw().toBuffer();
   assert(full.equals(reference),`no character thirty-two after a trailing space or in the reported model name (${theme}, ${index})`);
   await editableTitle.evaluate((el,value)=>{el.value=value;el.setSelectionRange(0,0);el.scrollLeft=0;},name);
   await page.screenshot({path:`${output}/${width}-${theme}-focused-boundary-${index}.png`});
  }
  await page.evaluate(()=>window.__gridFixture.close());
  const lockedMeta={managed_by:'neve_download',neve_catalog_id:'locked-fixture'};
  admin[1].meta=lockedMeta;
  await page.reload({waitUntil:'networkidle'});await page.waitForFunction(()=>window.__gridFixture);
  await page.evaluate(meta=>{window.__gridFixture.admin[1].meta=meta;return window.__gridFixture.open();},lockedMeta);
  await page.locator('[data-model-key="gguf:local/Model1"] .unified-model-name').click();
  await page.waitForFunction(()=>document.querySelector('[data-model-editable-name]')?.disabled===true);
  assert.equal(await editor.locator('[data-model-name-edit-hint], [data-model-description-edit-hint]').count(),0,'locked catalog fields never advertise editing');
  assert(await editor.getByRole('textbox',{name:'Description',exact:true}).evaluate(el=>el.readOnly),'catalog description stays readonly');
  assert.deepEqual(errors,[]);results.push({width,closed,controls});await page.close();
 }
 await fs.writeFile(`${output}/${process.argv.includes('--measure-controls')?'controls-before':process.argv.includes('--measure')?'before':'after'}.json`,JSON.stringify(results,null,2));console.log(JSON.stringify(results,null,2));
}catch(error){await page?.screenshot({path:`${output}/failed.png`});throw error;}finally{await browser?.close();await server?.close();await fs.rm(file,{force:true});await fs.rmdir(directory).catch(()=>{});}
