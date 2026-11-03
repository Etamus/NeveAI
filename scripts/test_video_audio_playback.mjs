import fs from 'node:fs/promises';
import { constants, createReadStream, existsSync } from 'node:fs';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { createServer } from 'vite';
import { chromium } from '../logs/ui-image-26/node_modules/playwright/index.mjs';
import { installMobileOfflineApi } from './fixtures/mobile-offline-api.mjs';

const route = new URL('../src/routes/__video_audio/', import.meta.url);
const fixture = new URL('+page.svelte', route);
const output = 'logs/video-audio-20261102';
let server, browser;
const results = [];
await fs.mkdir(route, { recursive: true });
await fs.copyFile(new URL('./fixtures/video-audio.svelte', import.meta.url), fixture, constants.COPYFILE_EXCL);
try {
 server = await createServer({plugins:[{
  name: 'native-audio-test-media',
  configureServer(vite) {
   vite.middlewares.use(async (req, res, next) => {
    const match = req.url?.match(/^\/__audio_media\/(h3-text|vdn-text|h3-first-frame|vdn-first-last)\.mp4$/);
    if (!match) return next();
    try {
     const path = `${output}/${match[1]}.mp4`, { size } = await fs.stat(path);
     const range = req.headers.range?.match(/^bytes=(\d+)-(\d*)$/);
     const start = range ? Number(range[1]) : 0, end = range?.[2] ? Math.min(Number(range[2]), size - 1) : size - 1;
     if (start >= size || end < start) { res.writeHead(416, {'Content-Range': `bytes */${size}`}); return res.end(); }
     res.writeHead(range ? 206 : 200, {'Content-Type':'video/mp4', 'Accept-Ranges':'bytes',
      'Content-Length':end-start+1, ...(range ? {'Content-Range':`bytes ${start}-${end}/${size}`} : {})});
     createReadStream(path,{start,end}).pipe(res);
    } catch (error) { next(error); }
   });
  }
 }],server:{port:5188,strictPort:true,watch:{ignored:['**/logs/**','**/scripts/**','**/docs/**']}}});
 await server.listen();
 // The bundled headless shell may omit H.264/AAC; use an installed codec-capable browser.
 const brave = 'C:/Program Files/BraveSoftware/Brave-Browser/Application/brave.exe';
 const executablePath = process.env.VIDEO_AUDIO_BROWSER ?? (existsSync(brave) ? brave : undefined);
 browser = await chromium.launch({executablePath,args:['--autoplay-policy=no-user-gesture-required']});
 for (const width of [390,1440]) for (const name of (process.argv.includes('--opening')?['h3-text','h3-first-frame']:['h3-text','vdn-text','h3-first-frame','vdn-first-last'])) {
  const page = await browser.newPage({viewport:{width,height:1000},hasTouch:width<768}), errors = [];
  page.on('pageerror',error=>errors.push(error.message));
  page.on('response',response=>{if(response.url().includes('__audio_media'))console.log('MEDIA',response.status(),response.url(),response.headers()['content-type']);});
  await installMobileOfflineApi(page);
  let releaseMedia;
  if(process.argv.includes('--opening')){
   const gate=new Promise(resolve=>releaseMedia=resolve);
   await page.route('**/__audio_media/**',async route=>{await gate;await route.continue().catch(()=>{});});
  }
  await page.goto(`http://localhost:5188/__video_audio?case=${name}&dark=${width===1440}`,{waitUntil:releaseMedia?'domcontentloaded':'networkidle'});
  const inline = page.locator('.video-player video');
  await inline.waitFor({state:'attached'});
  if(releaseMedia){
   try{
    await page.getByRole('button',{name:'Expandir',exact:true}).click();
    await page.waitForTimeout(200);
    assert.equal(await page.locator('.preview-progress').isVisible(),false,'Controls must await the first frame');
    await page.screenshot({path:`${output}/opening-${name}-${width}.png`});
    await page.keyboard.press('Escape');
    assert.equal(await page.locator('[role="dialog"]').count(),0);
    await page.getByRole('button',{name:'Expandir',exact:true}).click();
    assert.equal(await page.locator('.preview-progress').isVisible(),false);
   }finally{releaseMedia();}
   await page.locator('.preview-progress').waitFor({state:'visible'});
   await page.keyboard.press('Escape');
  }
  await page.waitForFunction(()=>document.querySelector('.video-player video')?.readyState>=1).catch(async error=>{
   console.log('MEDIA STATE',await inline.evaluate(video=>({src:video.src,currentSrc:video.currentSrc,error:video.error?.message,code:video.error?.code,network:video.networkState,ready:video.readyState})),page.url());
   throw error;
  });
  await page.locator('.video-play').click();
  await page.waitForFunction(()=>document.querySelector('.video-player video').currentTime>0.25);
  const audio = await inline.evaluate(async video=>{
   const context = new AudioContext(), source = context.createMediaElementSource(video), analyser = context.createAnalyser();
   source.connect(analyser);analyser.connect(context.destination);await context.resume();
   const samples = new Float32Array(analyser.fftSize);let peak=0;
   for(let i=0;i<10;i++){await new Promise(resolve=>setTimeout(resolve,40));analyser.getFloatTimeDomainData(samples);peak=Math.max(peak,...samples.map(Math.abs));}
   window.__audioContext=context;
   return {peak,duration:video.duration,width:video.videoWidth,height:video.videoHeight,muted:video.muted,decodedBytes:video.webkitAudioDecodedByteCount};
  });
  assert(audio.peak>0.00001,JSON.stringify(audio));assert.equal(audio.muted,false);
  await page.getByRole('button',{name:'Silenciar',exact:true}).click();
  assert.equal(await inline.evaluate(video=>video.muted),true);
  await page.getByRole('button',{name:'Desilenciar',exact:true}).click();
  assert.equal(await inline.evaluate(video=>video.muted),false);
  await page.locator('.video-progress').fill('60');
  await page.locator('.video-progress').dispatchEvent('input');
  await page.waitForFunction(()=>!document.querySelector('.video-player video').seeking);
  await inline.evaluate(video=>{
   window.__originalVideo=video;window.__transitionEvents=[];
   window.__backgroundWheels=0;
   document.querySelector('.video-player').addEventListener('wheel',()=>window.__backgroundWheels++);
   for(const type of ['pause','seeking','emptied','loadstart','waiting'])video.addEventListener(type,()=>window.__transitionEvents.push(type));
  });
  const beforeExpand=await inline.evaluate(video=>video.currentTime);
  const inlineBox=await page.locator('.video-player').boundingBox();
  await page.getByRole('button',{name:'Expandir',exact:true}).click();
  const preview = page.locator('[role="dialog"] video');await preview.waitFor({state:'attached'});
  assert.equal(await preview.evaluate(video=>video===window.__originalVideo),true,'Expansion must retain the exact media element');
  assert.equal(await page.locator('video').count(),1,'Only one decoder/audio source may exist');
  await page.mouse.move(width/2,500);
  await page.mouse.wheel(0,300);
  assert.equal(await page.evaluate(()=>window.__backgroundWheels),0,'Expanded wheel must not reach the chat');
  await page.waitForTimeout(120);
  await page.keyboard.press('Escape');
  await page.waitForTimeout(120);
  assert.deepEqual(await page.evaluate(()=>window.__transitionEvents),[],'Expanding/closing must not pause, seek, buffer or reload');
  assert(await inline.evaluate(video=>video.currentTime)>beforeExpand,'Playback clock must advance through expansion');
  assert.equal(await page.evaluate(()=>window.__audioContext.state),'running');
  const returnedBox=await page.locator('.video-player').boundingBox();
  for(const key of ['x','y','width','height'])assert(Math.abs(inlineBox[key]-returnedBox[key])<1,'Expansion must not alter chat geometry');
  await page.getByRole('button',{name:'Expandir',exact:true}).click();
  assert.equal(await preview.evaluate(video=>video.matches('.video-preview-surface:popover-open video')),true);
  await page.waitForFunction(()=>document.querySelector('[role="dialog"] video')?.currentTime>1);
  assert.equal(await preview.evaluate(video=>video.muted),false);
  await preview.evaluate(video=>video.play());
  await page.waitForTimeout(300);
  assert.equal(await preview.evaluate(video=>video.paused),false);
  if (width===1440) {
   const [download] = await Promise.all([page.waitForEvent('download'),page.locator('.preview-header button').filter({has:page.locator('svg path[d^="M4 17"]')}).click()]);
   const hash = data=>createHash('sha256').update(data).digest('hex');
   assert.equal(hash(await fs.readFile(await download.path())),hash(await fs.readFile(`${output}/${name}.mp4`)));
  }
  await page.screenshot({path:`${output}/player-${name}-${width}.png`});
  // Closing must return the expanded timeline and playback state to the inline player.
  await preview.evaluate(video=>{video.pause();video.currentTime=video.duration*0.35;video.muted=true;});
  await page.waitForFunction(()=>!document.querySelector('[role="dialog"] video').seeking);
  const pausedTime=await preview.evaluate(video=>video.currentTime);
  await page.keyboard.press('Escape');
  assert.equal(await inline.evaluate(video=>video.paused),true);
  assert.equal(await inline.evaluate(video=>video.muted),true);
  assert(Math.abs(await inline.evaluate(video=>video.currentTime)-pausedTime)<0.05);
  await page.getByRole('button',{name:'Expandir',exact:true}).click();
  await page.locator('.preview-progress').waitFor({state:'visible'});
  assert.equal(await preview.evaluate(video=>video.paused),true);
  assert.equal(await preview.evaluate(video=>video.muted),true);
  assert(Math.abs(await preview.evaluate(video=>video.currentTime)-pausedTime)<0.05);
  await preview.evaluate(async video=>{video.currentTime=video.duration*0.2;await video.play();});
  await page.waitForTimeout(200);
  const resumedTime=await preview.evaluate(video=>video.currentTime);
  await page.locator(width<768?'.mobile-modal-back':'.video-preview-close').click();
  await page.waitForFunction(()=>!document.querySelector('.video-player video').paused);
  const returnedTime=await inline.evaluate(video=>video.currentTime);
  assert(returnedTime>=resumedTime-0.05&&returnedTime<resumedTime+0.7,JSON.stringify({resumedTime,returnedTime}));
  await page.getByRole('button',{name:'Expandir',exact:true}).click();
  await page.locator('.preview-progress').waitFor({state:'visible'});
  assert.equal(await inline.evaluate(video=>video===window.__originalVideo&&!video.paused),true,'The original player must keep playing in expansion');
  await preview.evaluate(async video=>{video.currentTime=video.duration-0.1;await video.play();});
  await page.waitForFunction(()=>document.querySelector('[role="dialog"] video').ended);
  const endTime=await preview.evaluate(video=>video.duration);
  await page.keyboard.press('Escape');
  assert.equal(await inline.evaluate(video=>video.paused),true,'Ended video must not restart on return');
  assert(Math.abs(await inline.evaluate(video=>video.currentTime)-endTime)<0.05);
  assert.deepEqual(errors,[]);results.push({width,name,...audio});
  await page.close();console.log('PASS',width,name,JSON.stringify(audio));
 }
 await fs.writeFile(`${output}/playback.json`,JSON.stringify(results,null,2));
} finally {
 await browser?.close();await server?.close();await fs.unlink(fixture);await fs.rmdir(route);
}
