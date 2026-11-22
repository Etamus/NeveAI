// Read-only playback probe: use the playlist of an already imported local test video.
import assert from 'node:assert/strict';
import { chromium } from '../logs/ui-image-26/node_modules/playwright/index.mjs';
import { build } from 'esbuild-wasm';

const [playlist,startArg='0'] = process.argv.slice(2);
const target = +startArg;
const origin = new URL(playlist).origin;
const bundle=await build({stdin:{contents:"export * from './src/lib/utils/studioPreview.ts'",resolveDir:process.cwd()},bundle:true,write:false,format:'iife',globalName:'Preview'});
const browser=await chromium.launch({executablePath:process.env.NEVE_TEST_BROWSER,args:['--autoplay-policy=no-user-gesture-required']});
try {
    const page=await browser.newPage();
    page.on('console',m=>{if(m.type()==='error')console.error(m.text())});
    await page.route(origin+'/studio-playback-test',r=>r.fulfill({contentType:'text/html',body:'<video muted></video>'}));
    await page.goto(origin+'/studio-playback-test');
    await page.addScriptTag({content:bundle.outputFiles[0].text});
    await page.evaluate(url=>{
        const v=document.querySelector('video');
        window.control=Preview.studioPreview(v,url);
        window.failure=()=>v.error && [v.error.code,v.error.message];
    },playlist);
    await page.waitForFunction(()=>document.querySelector('video').readyState>=2,null,{timeout:45000});
    const state=()=>page.evaluate(()=>{const v=document.querySelector('video');return {ready:v.readyState,at:v.currentTime,native:!v.currentSrc.startsWith('blob:'),error:failure()}});
    console.log('initial',await state());
    const duration=await page.locator('video').evaluate(v=>v.duration);
    for(const seek of [target, duration*.83, duration*.22, target+1.1, target-2, target+.35]){
        await page.locator('video').evaluate((v,t)=>{v.pause();v.currentTime=Math.max(0,t)},seek);
        await page.waitForTimeout(70);
    }
    const run=async(at)=>{
        await page.evaluate(()=>{document.querySelector('video').play().catch(e=>console.error(e.message))});
        try {await page.waitForFunction(at=>{const v=document.querySelector('video');return !v.paused && v.currentTime>at+.5 && v.currentTime<at+10},at,{timeout:20000});}
        catch(e){console.log('stalled',await state());throw e;}
    };
    await run(target+.35);
    console.log('after seeks',await state());
    if(process.env.NEVE_TEST_RECOVERY){
        // Force a media decoder failure, then exercise the same explicit retry as the transport.
        await page.locator('video').evaluate(async v=>{v.pause();const failed=new Promise(r=>v.addEventListener('error',r,{once:true}));v.src='data:video/mp4,invalid';await failed;});
        const at=target+2;
        assert(await page.evaluate(at=>Preview.retryStudioPreview(document.querySelector('video'),at),at));
        await page.waitForFunction(()=>document.querySelector('video').readyState>=2,null,{timeout:45000});
        await run(at);
        console.log('recovered',await state());
    }
}finally{await browser.close();}

