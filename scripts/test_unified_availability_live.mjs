import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {chromium} from '../logs/ui-image-26/node_modules/playwright/index.mjs';

const output='logs/unified-availability-live';
await fs.mkdir(output,{recursive:true});
const browser=await chromium.launch();
let child,finished;const checks=[],errors=[];
try {
 const page=await browser.newPage({viewport:{width:1440,height:1000}});
 page.on('pageerror',error=>errors.push(error.message));
 const loaded=await(await page.request.get('http://localhost:8080/llamacpp/models/loaded')).json();
 if(!loaded.models.length){
  const response=await page.request.post('http://localhost:8080/llamacpp/models/load',{timeout:180000,data:{filename:'Qwen3.5 9B MTP UDQ4_K_XL.gguf',n_gpu_layers:-1,n_ctx:8192,cache_type:'q8_0',context_shift:'off',speculative_decoding:'off',token_prediction:'off'}});
  assert(response.ok(),await response.text());
 }else assert.equal(loaded.models[0].id,'local/Qwen3.5 9B MTP UDQ4_K_XL','Do not replace an unexpected user model');
 await page.goto('http://localhost:8080',{waitUntil:'networkidle',timeout:90000});
 const button=page.getByRole('button',{name:'Models',exact:true});
 const catalog=page.locator('.unified-model-catalog');
 const open=async()=>{
  await button.click();await catalog.waitFor();
  return catalog.evaluate(async element=>{await new Promise(requestAnimationFrame);return {blocked:element.dataset.modelsBlocked,inert:element.inert,loaded:element.querySelectorAll('button[aria-label="Descarregar"]').length};});
 };
 const initial=await open();assert.equal(initial.blocked,'false');
 // Initial application bootstrap may still be receiving its first catalog.
 await catalog.locator('button[aria-label="Descarregar"]').waitFor();
 await page.keyboard.press('Escape');await catalog.waitFor({state:'hidden'});
 let stdout='';
 child=spawn('backend/neveai/venv/Scripts/python.exe',['scripts/test_media_standby_live.py'],{
  cwd:process.cwd(),windowsHide:true,env:{...process.env,NEVE_MEDIA_TEST_OUTPUT:output+'/generations',NEVE_MEDIA_TEST_PAUSE:'2'}
 });
 child.stdout.on('data',data=>{stdout+=data;process.stdout.write(data);});
 child.stderr.on('data',data=>process.stderr.write(data));
 let exited=false;
 finished=new Promise((resolve,reject)=>{child.on('error',reject);child.on('exit',code=>{exited=true;code===0?resolve():reject(new Error('GPU script failed: '+code));});});
 // Attach rejection handling immediately; rethrow after UI monitoring finishes.
 finished.catch(()=>{});
 let seenBusy=false,lastRevision=-1,cycles=0;
 while(!exited){
  const state=await(await page.request.get('http://localhost:8080/llamacpp/media-state')).json();
  if(state.revision!==lastRevision){
   lastRevision=state.revision;
   if(state.busy&&!seenBusy){
    seenBusy=true;
    const visual=await open();
    assert.equal(visual.blocked,'true','First visible frame must already be blocked');
    assert.equal(visual.inert,true);assert.equal(visual.loaded,0);
    await page.screenshot({path:`${output}/busy-${cycles}.png`});checks.push({phase:'busy',revision:state.revision,...visual});
   }else if(!state.busy&&seenBusy){
    seenBusy=false;cycles++;
    // It must update in place, then also reopen with the same correct state.
    await page.waitForFunction(()=>document.querySelector('.unified-model-catalog')?.dataset.modelsBlocked==='false',null,{timeout:2000});
    await page.keyboard.press('Escape');await catalog.waitFor({state:'hidden'});
    const visual=await open();
    assert.equal(visual.blocked,'false');assert.equal(visual.loaded,1);
    await page.screenshot({path:`${output}/restored-${cycles}.png`});checks.push({phase:'restored',revision:state.revision,...visual});
    await page.keyboard.press('Escape');await catalog.waitFor({state:'hidden'});
   }
  }
  await page.waitForTimeout(100);
 }
 await finished;
 assert.equal(cycles,4);assert.deepEqual(errors,[]);
 await fs.writeFile(`${output}/results.json`,JSON.stringify({cycles,checks,errors},null,2));
 await fs.writeFile(`${output}/generation-output.log`,stdout);
 console.log('PASS real modal across '+cycles+' media lifecycles');
}catch(error){
 await browser.contexts()[0]?.pages()[0]?.screenshot({path:`${output}/failure.png`}).catch(()=>{});
 if(finished)await finished.catch(()=>{});
 throw error;
}finally{await browser.close();}
