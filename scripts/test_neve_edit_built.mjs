import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { mkdir, mkdtemp, readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { setTimeout as sleep } from 'node:timers/promises';
import { chromium } from '../logs/ui-image-26/node_modules/playwright/index.mjs';

const base = process.env.NEVE_TEST_ORIGIN ?? 'http://localhost:8080';
const native = process.env.NEVE_EDIT_NATIVE === '1';
const mobileOnly = process.env.NEVE_EDIT_TEST_MOBILE === '1';
const speakersOnly=process.env.NEVE_TEST_STUDIO_SPEAKERS==='1';
const largeOnly=process.env.NEVE_TEST_STUDIO_LARGE==='1';
const formatsOnly=process.env.NEVE_TEST_STUDIO_EXPORTS==='1';
const closeOnly=process.env.NEVE_TEST_STUDIO_CLOSE==='1';
const toolsOnly = process.env.NEVE_TEST_MAKER_TOOLS === '1';
let browser, host;
const fixture = resolve(process.env.NEVE_TEST_VIDEO ?? 'videoteste/teste.mp4');
const output = resolve('logs/neve-edit-ui');
await mkdir(output, { recursive: true });
const issues = [], archivedTests=new Set();
async function assertRotation(chevron,action) {
	const samples=chevron.evaluate(el=>new Promise(resolve=>{
		const states=new Set(); const end=performance.now()+430;
		function frame(){const s=getComputedStyle(el);states.add(s.transform+' '+s.rotate);if(performance.now()<end)requestAnimationFrame(frame);else resolve([...states])}
		frame();
	}));
	await action(); const states=await samples; assert(states.length>2,'Chevron jumped without intermediate frames: '+states.join(';'));
}
try {
	if (native) {
		const installed = JSON.parse(await readFile('.desktop/installed.json', 'utf8'));
		const port = 9247;
		host = spawn(resolve('.desktop', installed.host), [
			'--root', process.cwd(), '--runtime', resolve('.desktop', installed.runtime),
			'--profile', await mkdtemp(resolve(output, 'native-profile-')), '--url', base
		], { windowsHide: true, env: { ...process.env, NEVE_WEBVIEW2_TEST_MODE: '1', NEVE_WEBVIEW2_DEBUG_PORT: String(port) } });
		for (let attempt = 0; attempt < 80 && !browser && host.exitCode === null; attempt++) {
			browser = await chromium.connectOverCDP(`http://127.0.0.1:${port}`, { timeout: 400 }).catch(() => null);
			if (!browser) await sleep(200);
		}
		assert(browser, 'WebView2 test window did not start');
	} else browser = await chromium.launch({
		executablePath: process.env.NEVE_TEST_BROWSER,
		args: ['--autoplay-policy=no-user-gesture-required', '--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream']
	});
	for (const width of (native || mobileOnly || toolsOnly || speakersOnly || closeOnly || formatsOnly || largeOnly ? [] : [1440, 320])) {
		const page = await browser.newPage({ viewport: { width, height: 844 }, permissions: ['microphone'] });
		let sendError;
		await page.routeWebSocket('**/api/v1/audio/voice', socket => {
			socket.onMessage(message => {
				if (typeof message === 'string' && message.startsWith('{')) {
					socket.send(JSON.stringify({ type: 'started', sample_rate: 24000 }));
				}
			});
			sendError = () => socket.send(JSON.stringify({
				type: 'error', message: 'Voice mode gives priority to chat and media generation.'
			}));
		});
		await page.addInitScript(() => { localStorage.locale = 'pt-BR'; });
		await page.goto(base, { waitUntil: 'networkidle' });
		await page.getByRole('button', { name: /^(Modo de voz|Voice mode)$/i }).click();
		await page.getByText(/^(Pode falar|Go ahead)\.\.\.$/i).waitFor();
		const close = page.getByRole('button', { name: /^(Encerrar|End voice mode)$/i });
		const before = await close.boundingBox();
		sendError();
		const warning = page.getByText(/^(O modo de voz dá prioridade|Voice mode gives priority)/);
		await warning.waitFor();
		const after = await close.boundingBox();
		const message = await warning.boundingBox();
		assert(Math.abs(before.x - after.x) < 1 && message.y + message.height <= after.y, 'Voice warning displaced the close button');
		await close.click();
		await warning.waitFor({ state: 'hidden' });
		await page.close();
		console.log(`PASS: ${width} voice priority warning and close button`);
	}
	for (const [width, height, theme] of (native ? [[1280, 820, 'dark']] : largeOnly ? [[1440, 950, 'dark']] : mobileOnly ? [[390, 844, 'light']] : [[1440, 950, 'dark'], [390, 844, 'light']])) {
		const context = native ? browser.contexts()[0] : undefined;
		const page = context ? context.pages()[0] ?? await context.waitForEvent('page')
			: await browser.newPage({ viewport: { width, height }, acceptDownloads: true });
		page.on('response',async r=>{if(r.url().endsWith('/video-edit/media')&&r.request().method()==='POST'&&r.ok()){const f=await r.json().catch(()=>null);if(f?.fileId)archivedTests.add(f.fileId);}});
		page.on('pageerror', error => issues.push(error.message));
		await page.addInitScript(currentTheme => {
			const fetch=window.fetch.bind(window);
			window.fetch=async (...args)=>{
				const r=await fetch(...args);
				if(r.ok && args[1]?.method==='POST' && r.url.endsWith('/video-edit/media')) window.__studioTestImport=await r.clone().json();
				return r;
			};
			localStorage.setItem('neveai.language', 'pt-BR');
			localStorage.theme = currentTheme;
		}, theme);
		if (native) {
			await page.waitForFunction(() => window.__NEVE_WEBVIEW2__ === true && !!document.querySelector('[data-composer-root]'));
			await page.reload({ waitUntil: 'networkidle' });
			await page.setViewportSize({ width, height });
		} else await page.goto(base, { waitUntil: 'networkidle' });
		const button = page.getByRole('button', { name: /^(Crie um vídeo|Create a video)$/i });
		if (await button.isVisible()) await button.click();
		else {
			await page.locator('.composer-more-trigger').click();
			await page.locator('.composer-integrations-menu').getByText(/^(Criar vídeo|Create (a )?video)$/i).last().click();
		}
		const picker = page.getByRole('button', { name: /^(Modo de vídeo|Video mode)$/i });
		await picker.waitFor();
		assert.match(await picker.innerText(), /Neve Video 1.5/);
		if (width < 768) {
			const aspect = page.locator('#video-aspect-ratio-dropdown-container button').first();
			assert(await aspect.evaluate(el => {
				const bounds = el.getBoundingClientRect();
				const hit = document.elementFromPoint(bounds.right - 6, bounds.y + bounds.height / 2);
				return el.contains(hit);
			}), 'Aspect-ratio control is clipped on mobile');
		}
		const chevron = picker.locator('svg');
		assert(await chevron.evaluate(el => el.classList.contains('rotate-180')));
		await assertRotation(chevron,()=>picker.click());
		const menu = page.getByRole('menu', { name: /^(Modo de vídeo|Video mode)$/i });
		await menu.waitFor();
		assert.equal(await picker.getAttribute('aria-expanded'), 'true');
		assert.equal(await chevron.evaluate(el => el.classList.contains('rotate-180')), false);
		assert.equal(await menu.getByRole('menuitemradio', { name: 'Neve Video 1.5' }).getAttribute('aria-checked'), 'true');
		if (!native) {
			await page.waitForFunction(() => document.querySelector('[data-composer-dropdown-anchor="video-mode-dropdown-container"]')?.getAnimations().length === 0);
			await page.screenshot({ path: `${output}/selector-${width}-${theme}.png` });
		}
		await assertRotation(chevron,()=>page.keyboard.press('Escape'));
		await menu.waitFor({ state: 'hidden' });
		assert.equal(await picker.getAttribute('aria-expanded'), 'false');
		assert(await chevron.evaluate(el => el.classList.contains('rotate-180')));
		await picker.press('ArrowDown');
		await menu.getByRole('menuitemradio', { name: 'Neve Video 1.5' }).press('ArrowDown');
		await page.keyboard.press('Enter');
		assert.match(await picker.innerText(), /Neve Studio/);assert.equal(await menu.count(),0);
		const slots = page.locator('[data-video-edit-slots]');
		await slots.waitFor();
		assert.equal(await page.locator('#chat-input').isVisible(), false);
		assert.equal(await page.getByRole('button', { name: /^(Ditar|Dictate)$/i }).count(), 0);
		assert.equal(await page.getByRole('button', { name: /^(Modo de voz|Voice mode)$/i }).count(), 0);
		const editor=page.getByRole('region',{name:'Neve Studio',exact:true});
		await slots.locator('[data-video-mode-edit]').click();
		await editor.getByRole('region',{name:/^(Media bin|Biblioteca de mídia)$/i}).waitFor();
		await page.keyboard.press('Escape');await editor.waitFor({state:'hidden'});
		const composerUpload = page.getByLabel(/^(Importar vídeo|Import video)$/i).and(page.locator('input[type=file]'));
		if (width === 1440) {
			if(formatsOnly){
				await composerUpload.setInputFiles(fixture);
				await slots.getByText(/\.mp4$/i).waitFor();
				archivedTests.add(await page.evaluate(()=>window.__studioTestImport.fileId));
				await slots.getByText(/\.mp4$/i).hover();
				await slots.getByRole('button',{name:/^(Remove|Remover)$/i}).click();
				await slots.locator('[data-video-mode-edit]').click();
				await editor.getByRole('region',{name:/^(Media bin|Biblioteca de mídia)$/i}).waitFor();
				assert.equal(await editor.locator('[data-key],[data-video-edit-asset]').count(),0);
				await page.keyboard.press('Escape');await editor.waitFor({state:'hidden'});
			}
			await composerUpload.setInputFiles(resolve('static/favicon.png'));
			await page.getByText(/^(Selecione um arquivo de vídeo|Choose a video file)\.$/i).waitFor();
			assert.equal(await slots.getByText('favicon.png').count(), 0);
		}
		const uploaded=page.waitForResponse(r=>r.url().endsWith('/video-edit/media')&&r.request().method()==='POST',{timeout:180000});
		if(native && largeOnly){
			// The WebView runs on this host. Pass the path directly, not a multi-GB Playwright protocol payload.
			const cdp=await page.context().newCDPSession(page);
			const {root}=await cdp.send('DOM.getDocument');
			const {nodeId}=await cdp.send('DOM.querySelector',{nodeId:root.nodeId,selector:'[data-video-edit-slots]'});
			const {object}=await cdp.send('DOM.resolveNode',{nodeId});
			const {result}=await cdp.send('Runtime.callFunctionOn',{objectId:object.objectId,functionDeclaration:'function(){return this.previousElementSibling}'});
			await cdp.send('DOM.setFileInputFiles',{objectId:result.objectId,files:[fixture]});
			await cdp.detach();
		}else await composerUpload.setInputFiles(fixture);
		assert((await uploaded).ok());await page.waitForFunction(()=>window.__studioTestImport?.fileId);
		const {fileId,width:sourceWidth,height:sourceHeight}=await page.evaluate(()=>window.__studioTestImport);archivedTests.add(fileId);
		await slots.getByText(/\.mp4$/i).waitFor();
		if(largeOnly){
			const urls=[];
			page.on('request',r=>{if(r.url().includes('/segments/'))urls.push(r.url())});
			await slots.locator('[data-video-mode-edit]').click();
			const video=editor.locator('.edit-preview-viewport > video');
			const ready=()=>page.waitForFunction(()=>document.querySelector('.edit-preview-viewport > video')?.readyState>=2,{},{timeout:45000});
			await ready();
			console.log('first frame ready',await video.evaluate(v=>[v.videoWidth,v.videoHeight,v.duration]));
			const play=editor.getByRole('button',{name:/^(Reproduzir|Play)$/i});
			const pause=editor.getByRole('button',{name:/^(Pausar|Pause)$/i});
			await play.click();
			await page.waitForFunction(()=>{const v=document.querySelector('.edit-preview-viewport > video');return v.currentTime>5 && v.webkitAudioDecodedByteCount>0 && v.getVideoPlaybackQuality().totalVideoFrames>10 && Number(document.querySelector('.edit-ruler').getAttribute('aria-valuenow'))>4},{},{timeout:45000});
			if(width>=768){
				let requests=0;
				const toolRoutes=/\/video-edit\/(?:assist|media\/[^/]+\/(?:process|selection))$/;
				await page.route(toolRoutes,route=>{requests++;return route.fulfill({status:422,json:{detail:'Unexpected request'}})});
				await editor.locator('.edit-monitor').evaluate(node=>{
					window.__studioBlockedOverlay=false;
					new MutationObserver(records=>{
						for(const record of records)for(const el of record.addedNodes)
							if(el.nodeType===1 && (el.matches('.edit-monitor-loading')||el.querySelector('.edit-monitor-loading')))window.__studioBlockedOverlay=true;
					}).observe(node,{childList:true,subtree:true});
				});
				const grid=editor.locator('.studio-tool-grid');
				for(const [label,message,optional] of [
					['Interpolar para 60 FPS','Selecione um trecho de até 5 minutos.',true],
					['Isolar voz','Selecione um trecho de até 1 hora.',true],
					['Apagar objeto','Selecione um trecho de até 30 minutos.',true]
				]){
					const tool=grid.getByRole('button',{name:label,exact:true});
					if(optional && !await tool.count())continue;
					await tool.click({timeout:4000});
					await page.getByText(message,{exact:true}).last().waitFor({timeout:4000});
					assert(await video.evaluate(v=>!v.paused));
				}
				assert.equal(requests,0);
				assert.equal(await page.evaluate(()=>window.__studioBlockedOverlay),false);
				await page.unroute(toolRoutes);
				console.log('PASS Portuguese duration guard: no processing request, overlay or pause');
			}
			await pause.click();
			const ruler=editor.locator('.edit-ruler'),box=await ruler.boundingBox();
			await ruler.click({position:{x:Math.floor(box.width*.79),y:5}});
			const t=Number(await ruler.getAttribute('aria-valuenow'));
			assert(t>3600);
			await play.click();await page.waitForFunction(t=>{const v=document.querySelector('.edit-preview-viewport > video');return v.currentTime>t+1 && !v.seeking && Number(document.querySelector('.edit-ruler').getAttribute('aria-valuenow'))>t+.9},t,{timeout:45000});
			assert(urls.length<30);
			console.log('PASS AV across segment and at',t,'seconds;',urls.length,'segment requests');
			const proc=page.waitForRequest(r=>r.url().endsWith('/assist'));
			await editor.getByRole('button',{name:'Transcrever falas',exact:true}).click();
			const op=(await proc).postDataJSON().requestId;
			await page.waitForTimeout(1200);
			const stopped=page.waitForResponse(r=>r.url().endsWith('/operations/'+op)&&r.request().method()==='DELETE');
			await editor.locator('.edit-monitor-loading button').click();
			assert((await stopped).ok());await editor.locator('.edit-monitor-loading').waitFor({state:'hidden'});
			assert.equal(await editor.locator('[data-caption-index]').count(),0);
			const picture=editor.locator('[data-key="video:0"]'),sound=editor.locator('[data-key="audio:0"]');
			await picture.click();await sound.click({modifiers:['Shift']});
			assert.equal(await picture.getAttribute('aria-pressed'),'true');
			assert.equal(await sound.getAttribute('aria-pressed'),'true');
			await page.keyboard.press('s');await page.keyboard.press('Shift');
			assert(await sound.evaluate(el=>getComputedStyle(el).outlineStyle==='none'));
			console.log('PASS long transcription cancelled and Shift selections retained');
			const endEdge=editor.locator('.edit-audio-track [data-trim-edge=end]').first();
			await endEdge.click();
			const endTime=await video.evaluate(v=>v.duration);
			assert(Math.abs(Number(await ruler.getAttribute('aria-valuenow'))-endTime)<.02);
			await editor.locator('.edit-video-track [data-trim-edge=start]').first().click();
			assert.equal(Number(await ruler.getAttribute('aria-valuenow')),0);
			await picture.click();
			await page.route('**/video-edit/assist',route=>route.fulfill({json:{cues:[{text:'Short',start:.32,end:.4}]}}));
			await editor.getByRole('button',{name:'Transcrever falas',exact:true}).click();
			const cue=editor.locator('[data-caption-index="0"]');
			await cue.waitFor({state:'attached'});
			await editor.locator('.edit-video-track [data-trim-edge=start]').first().click();
			const frame=editor.locator('.edit-timeline-frame');
			await frame.dispatchEvent('wheel',{deltaY:-4500,ctrlKey:true,clientX:(await frame.boundingBox()).x});
			await page.waitForFunction(()=>document.querySelector('[data-caption-index="0"]').getBoundingClientRect().width>=55);
			await cue.locator('[data-caption-edge=end]').click();
			assert.equal(Number(await ruler.getAttribute('aria-valuenow')),.4);
			await cue.locator('[data-caption-edge=start]').click();
			assert.equal(Number(await ruler.getAttribute('aria-valuenow')),.32);
			await editor.getByRole('button',{name:/^(Desfazer|Undo)$/}).click();
			console.log('PASS exact timeline edges and editable 80 ms cue on 4h ruler');
			await page.keyboard.press('Escape');await editor.waitFor({state:'hidden'});await page.close();continue;
		}
		const opening = width>=768 ? page.evaluate(()=>new Promise(resolve=>{
			const frames=[];
			function sample(){
				const grid=document.querySelector('.studio-tool-grid');
				if(grid?.clientHeight) frames.push([grid.children.length,grid.clientHeight,grid.firstElementChild.offsetHeight]);
				if(frames.length===10) resolve(frames);else requestAnimationFrame(sample);
			}
			sample();
		})) : null;
		await slots.locator('[data-video-mode-edit]').click();
		const track = editor.getByRole('group', { name: /^(Faixa de vídeo|Video track)$/i });
		assert.equal(await editor.getByRole('button',{name:/^(Tools|Ferramentas)$/i}).getAttribute('aria-pressed'),'true');
		if(opening){
			const frames=await opening;
			assert.equal(new Set(frames.map(f=>JSON.stringify(f))).size,1,'Tool grid moved on opening: '+JSON.stringify(frames));
			const grid=editor.locator('.studio-tool-grid');
			const visible=()=>grid.evaluate(el=>{
				const r=el.getBoundingClientRect(), rows=[];
				for(const [i,card] of Array.from(el.children).entries()){
					const b=card.getBoundingClientRect();
					if(b.bottom<=r.top+.8 || b.top>=r.bottom-.8) continue;
					if(b.top<r.top-1 || b.bottom>r.bottom+1) throw Error('Partial tool row');
					rows.push(i);
				}
				return rows;
			});
			const first=await visible();
			assert(await grid.evaluate(el=>parseFloat(getComputedStyle(el).paddingInlineEnd)>=5));
			if (width===1440) {
				await page.setViewportSize({width:1280,height:720});
				assert.equal((await visible()).length,6,'Expected three complete tool rows at 1280x720');
				await page.setViewportSize({width,height});
			}
			if(first.length<await grid.locator('.edit-tool-card').count()){
				await grid.dispatchEvent('wheel',{deltaY:120});
				assert.equal((await visible())[0],first[0]+2);
				await grid.evaluate(el=>el.scrollTop=el.scrollHeight);
				assert.equal((await visible()).at(-1),await grid.locator('.edit-tool-card').count()-1);
				await grid.evaluate(el=>el.scrollTop=0);
				assert.deepEqual(await visible(),first);
			}
			await editor.locator('.edit-audio-track [data-key]').first().click();
			const color=grid.getByRole('button',{name:/^(Equilibrar cores|Balance color)$/i});
			assert(await color.isDisabled());assert(Number(await color.evaluate(el=>getComputedStyle(el).opacity))<.6);
			await editor.locator('.edit-video-track [data-key]').first().click();
			assert(await color.isEnabled());
		}
		if(formatsOnly){
			const button=editor.getByRole('button',{name:/^(Exportar|Export)$/i});
			const picture=track.getByRole('button').first(),audio=editor.locator('[data-audio-lane="0"] button').first();
			await button.click();
			assert.equal(await editor.getByRole('menuitem',{name:'SRT'}).count(),0);
			for(const name of ['MP4','MP3'])assert(await editor.getByRole('menuitem',{name,exact:true}).isVisible());
			const menuId=await editor.getByRole('menu').getAttribute('id');
			for(const [name,option] of [['MP4','720p'],['MP3','192 kbps']]){
				const trigger=editor.getByRole('menuitem',{name,exact:true});
				await trigger.hover();
				const row=editor.getByRole('menuitem',{name:option,exact:true});
				await sleep(180);assert(!await row.isVisible());
				await trigger.click();
				await row.waitFor({state:'visible',timeout:3000});
				if(name==='MP4'){
					const back=editor.getByRole('menuitem',{name:/^(Voltar|Back)$/});
					assert(await back.locator('svg').count()===1);
					assert(await back.evaluate(el=>el===document.activeElement),'Back should keep pointer highlight');
				}
				assert.equal(await editor.getByRole('menu').count(),1);
				assert.equal(await editor.getByRole('menu').getAttribute('id'),menuId);
				assert(!await trigger.isVisible());
				assert.equal(await editor.getByRole('menuitem',{name:'Original'}).isVisible(),name==='MP4');
				await editor.getByRole('menuitem',{name:/^(Voltar|Back)$/}).click();
			}
			await page.keyboard.press('Escape');await audio.click();await audio.press('Delete');
			await button.click();await editor.getByRole('menuitem',{name:'Original'}).waitFor();assert.equal(await editor.getByRole('menuitem').count(),4);
			const downloaded=page.waitForEvent('download',{timeout:120000});
			await editor.getByRole('menuitem',{name:'Original'}).click();
			const video=await downloaded;
			assert.equal(video.suggestedFilename(),'Neve-Studio.mp4');
			const dims=await page.evaluate(base64=>new Promise((resolve,reject)=>{
				const el=document.createElement('video');el.preload='metadata';
				el.onloadedmetadata=()=>resolve([el.videoWidth,el.videoHeight]);el.onerror=()=>reject(Error('Invalid MP4'));
				el.src='data:video/mp4;base64,'+base64;
			}),(await readFile(await video.path())).toString('base64'));
			assert.deepEqual(dims,[sourceWidth,sourceHeight]);
			await editor.getByRole('button',{name:/^(Undo|Desfazer)$/}).click();
			await picture.click();await picture.press('Delete');await button.click();
			await editor.getByRole('menuitem',{name:'128 kbps'}).waitFor();assert.equal(await editor.getByRole('menuitem').count(),4);
			await page.keyboard.press('Escape');await page.close();console.log('PASS export format menus '+width);continue;
		}
		if(closeOnly){
			archivedTests.add(fileId);
			const close=()=>width<768 ? editor.getByRole('button',{name:/^(Voltar|Back)$/i}).click() : page.keyboard.press('Escape');
			if(width>=768){
				await editor.getByRole('button',{name:/^(Silenciar|Mute audio track)$/i}).click();
				await close();
				await page.getByRole('button',{name:/^(Cancelar|Cancel)$/i,exact:true}).last().click();
				await editor.getByRole('button',{name:/^(Desfazer|Undo)$/i}).click();
				// Hold the response so the timeline is still pristine at both dismissal attempts.
				let release, deletes=0;
				const gate=new Promise(resolve=>release=resolve);
				const counted=r=>{if(r.method()==='DELETE' && r.url().includes('/operations/')) deletes++};
				page.on('request',counted);
				await page.route('**/video-edit/assist',async r=>{await gate;await r.fulfill({json:{grade:{contrast:1,brightness:.02,saturation:1}}});});
				await editor.getByRole('button',{name:/^(Equilibrar cores|Balance color)$/i}).click();
				const discard=page.getByRole('button',{name:/^(Descartar|Discard)$/i,exact:true});
				for(const outside of [false,true]){
					if(outside)await page.mouse.click(4,4);else await editor.locator('[data-mobile-modal-close]').click();
					await discard.waitFor();
					await page.getByRole('button',{name:/^(Cancelar|Cancel)$/i,exact:true}).last().click();
					assert.equal(deletes,0);
					assert(await editor.locator('.edit-monitor-loading').isVisible());
				}
				release();await editor.locator('.edit-monitor-loading').waitFor({state:'hidden'});
				await editor.getByRole('button',{name:/^(Desfazer|Undo)$/i}).click();
				const start=page.waitForRequest(r=>r.url().endsWith('/process'));
				await editor.getByRole('button',{name:/^(Isolar voz|Isolate voice)$/i}).click();
				const id=(await start).postDataJSON().requestId;
				const stopped=page.waitForResponse(r=>r.request().method()==='DELETE' && r.url().endsWith('/operations/'+id));
				await editor.locator('[data-mobile-modal-close]').click();
				await discard.waitFor();
				assert.equal(deletes,0);
				await discard.click();
				assert((await stopped).ok());
				await editor.waitFor({state:'hidden'});
				await page.close();console.log('PASS close cancels running separator');continue;
			}
			await close();await editor.waitFor({state:'hidden'});
			assert.equal(await page.getByRole('button',{name:/^(Descartar|Discard)$/i}).count(),0);
			await page.close();console.log('PASS clean close '+width);continue;
		}
		if(speakersOnly){
			let originalSrt;
			assert.equal(await editor.getByRole('button',{name:/^(Número de falantes|Number of speakers)$/}).count(),0);
			if(width>=768){
				const cc=editor.locator('.edit-caption-label');
				assert(await cc.evaluate(el=>{
					const mid=(el.previousElementSibling.getBoundingClientRect().top+el.getBoundingClientRect().bottom)/2;
					return [...el.children].every(child=>{const r=child.getBoundingClientRect();return Math.abs(r.y+r.height/2-mid)<1});
				}),'Both CC controls must align to the center of their painted region');
				const duration=await editor.locator('.edit-preview-viewport > video').evaluate(v=>v.duration);
				const endpoint='**/video-edit/assist';
				await page.route(endpoint,r=>r.fulfill({json:{cues:[{start:duration-.08,end:duration,text:'End'}]}}));
				await editor.getByRole('button',{name:'Transcrever falas',exact:true}).click();
				const cue=editor.locator('[data-caption-index="0"]');
				await cue.waitFor({state:'attached'});
				const aligned=()=>cue.evaluate(el=>{
					const b=el.getBoundingClientRect(),r=el.firstElementChild.getBoundingClientRect();
					const clip=document.querySelector('.edit-video-track .edit-clip-item').getBoundingClientRect();
					if(Math.abs(clip.right-b.right)>0.6)return false;
					return r.right<=clip.right+.6 && getComputedStyle(el).overflow==='hidden';
				});
				assert(await aligned(),'Final subtitle overflowed its clip');
				const frame=editor.locator('.edit-timeline-frame');
				const w=await cue.evaluate(el=>el.getBoundingClientRect().width);
				await frame.dispatchEvent('wheel',{deltaY:-400,ctrlKey:true,clientX:(await frame.boundingBox()).x});
				await page.waitForFunction(w=>document.querySelector('[data-caption-index="0"]').getBoundingClientRect().width>w,w);
				assert(await aligned(),'Zoom changed the subtitle endpoint');
				await editor.getByRole('button',{name:/^(Desfazer|Undo)$/}).click();
				await page.unroute(endpoint);
				await editor.getByRole('button',{name:/^(Tools|Ferramentas)$/i}).click();
				console.log('PASS final subtitle aligned at both zoom levels; CC controls centered');
			}
			const response=page.waitForResponse(r=>r.url().endsWith('/assist'),{timeout:120000});
			await editor.getByRole('button',{name:/^(Identificar falantes|Identify speakers)$/i}).click();
			const answer=await response; assert.equal(answer.status(),200,await answer.text());
			assert.equal(answer.request().postDataJSON().speakerCount,undefined);
			const cues=(await answer.json()).cues;
			assert.deepEqual(cues.map(c=>c.speaker).filter((v,i,a)=>!i||v!==a[i-1]),[1,2,1,2]);
			const names=editor.getByRole('textbox',{name:/^(Falante|Speaker) [12]$/});
			const before=await editor.locator('.edit-ruler').getAttribute('aria-valuenow');
			const played=page.waitForResponse(r=>r.url().includes('/speaker-sample?'));
			await editor.getByRole('button',{name:/^(Ouvir|Listen)$/}).first().click();
			assert((await played).ok());
			await editor.locator('.edit-speakers').getByRole('button',{name:/^(Parar|Stop)$/}).waitFor({state:'hidden',timeout:10000});
			assert.equal(await editor.locator('.edit-ruler').getAttribute('aria-valuenow'),before);
			assert(await editor.locator('.caption-details').evaluate(el=>{
				const row=el.querySelector('.edit-speakers');
				const input=row.querySelector('input'),label=row.querySelector('span');
				return getComputedStyle(row).borderBottomWidth==='0px' &&
					input.getBoundingClientRect().left-label.getBoundingClientRect().right<=13 &&
					el.scrollHeight<=el.clientHeight+1 && el.offsetWidth===el.clientWidth &&
					Math.abs(row.getBoundingClientRect().right-el.getBoundingClientRect().right)<1;
			}),'Speakers must use the full width when they fit');
			await editor.locator('.edit-speakers span').first().click();assert(!(await names.first().evaluate(el=>document.activeElement===el)));
			assert.match(await names.last().inputValue(),/^(Falante|Speaker) 2$/);
			for(const unit of ['W','i','a\u0301','\u{1F600}']){
				await names.last().fill(unit.repeat(24));
				assert.equal(await names.last().inputValue(),unit.repeat(22));
				await names.last().press('End');
				const fit=await names.last().evaluate(el=>[el.scrollWidth,el.clientWidth,el.scrollLeft,getComputedStyle(el).fontSize]);
				assert(fit[0]<=fit[1]+1 && fit[2]<=1,'Speaker name scrolled: '+unit+' '+JSON.stringify(fit));
			}
			const fullName='1234567890123456789012';
			await names.last().fill(fullName);
			await names.last().evaluate(el=>el.setSelectionRange(5,5));
			await page.keyboard.insertText('xx');assert.equal(await names.last().inputValue(),fullName);
			await names.last().fill(''); await names.last().press('Tab'); assert.equal(await names.last().inputValue(),'');
			await names.first().fill('Ana');await names.first().press('Tab');
			if(width>=768){
				const exportButton=editor.getByRole('button',{name:/^(Exportar|Export)$/i});
				await exportButton.click();
				const starts=await Promise.all(['MP4','MP3','SRT'].map(name=>editor.getByRole('menuitem',{name,exact:true}).evaluate(el=>{
					const range=document.createRange();range.selectNodeContents(el);
					return range.getBoundingClientRect().left;
				})));
				assert(Math.max(...starts)-Math.min(...starts)<1,'Export format labels must start at the same position');
				const srtDownload=page.waitForEvent('download');
				await editor.getByRole('menuitem',{name:'SRT',exact:true}).click();
				const srt=await srtDownload;assert.equal(srt.suggestedFilename(),'Neve-Studio.srt');
				originalSrt=await readFile(await srt.path(),'utf8');
				assert.match(originalSrt,/\d{2}:\d{2}:\d{2},\d{3} --> .*\nAna: /);
				await exportButton.click();await editor.getByRole('menuitem',{name:'MP3',exact:true}).click();
				await editor.getByRole('menuitem',{name:'128 kbps'}).waitFor();
				for(const rate of [128,192,256,320])assert(await editor.getByRole('menuitem',{name:rate+' kbps'}).isVisible());
				const mp3Download=page.waitForEvent('download');
				await editor.getByRole('menuitem',{name:'256 kbps'}).click();assert.equal((await mp3Download).suggestedFilename(),'Neve-Studio.mp3');
			}
			assert.equal(await editor.locator('.edit-cue-time').count(),0);
			assert.equal(await editor.getByRole('button',{name:/^(Legendas|Captions)$/i}).getAttribute('aria-pressed'),'true');
			await editor.locator('[data-caption-index="0"] button').first().press('Enter');
			await editor.locator('.edit-cue-time').first().waitFor();
			if(width>=768){
				await page.setViewportSize({width:1280,height:720});
				const details=editor.locator('.caption-details');
				assert(await details.evaluate(el=>{
					const header=el.previousElementSibling, rect=header.getBoundingClientRect();
					el.scrollTop=el.scrollHeight;
					return el.scrollTop>0 && el.getBoundingClientRect().top>=rect.bottom &&
						header.getBoundingClientRect().top===rect.top && el.parentElement.scrollTop===0 &&
						parseFloat(getComputedStyle(el,'::-webkit-scrollbar-thumb').borderInlineStartWidth)>=6 &&
						el.parentElement.getBoundingClientRect().right-el.getBoundingClientRect().right>=12;
				}),'Caption details should scroll independently below the fixed controls');
				await page.setViewportSize({width,height});
			}
			if(width<768)await editor.getByRole('button',{name:/^(Visualização|Preview)$/i}).click();
			await editor.locator('.edit-preview-caption').waitFor();
			assert.match(await editor.locator('.edit-preview-caption').innerText(),/^Ana: /);
			if(width>=768){
				const video=editor.locator('.edit-preview-viewport > video');
				const text=editor.locator('.edit-cue textarea');
				const original=await text.inputValue();
				await text.fill(original+'!');await text.press('Tab');
				await editor.getByRole('button',{name:/^(Desfazer|Undo)$/}).click();
				await editor.locator('[data-caption-index="1"] button').first().press('Enter');
				const at=Number(await editor.locator('.edit-ruler').getAttribute('aria-valuenow'));
				await video.evaluate(async v=>{v.pause();const err=new Promise(r=>v.addEventListener('error',r,{once:true}));v.src='data:video/mp4,invalid';await err;});
				await editor.getByRole('button',{name:/^(Reproduzir|Play)$/}).click();
				await page.waitForFunction(at=>{const v=document.querySelector('.edit-preview-viewport > video');return !v.paused && !v.error && v.currentTime>at+.25 && v.currentTime<at+4},at);
				await editor.getByRole('button',{name:/^(Pausar|Pause)$/}).click();
				assert.equal(await editor.locator('[data-caption-index]').count(),cues.length);
				console.log('PASS Play recovers errored media at the selected subtitle without losing edits');
			}
			const req=page.waitForRequest(r=>r.url().endsWith('/exports')&&r.method()==='POST');
			const dl=page.waitForEvent('download',{timeout:120000});
			await editor.getByRole('button',{name:/^(Exportar|Export)$/i}).click();
			await editor.getByRole('menuitem',{name:'MP4',exact:true}).press('Enter');
			await editor.getByRole('menuitem',{name:'480p'}).click();
			const exported=(await req).postDataJSON().captions;assert.equal(exported.length,cues.length);
			assert(exported.every((c,i)=>c.speakerName===(cues[i].speaker===1?'Ana':exported.find((_,j)=>cues[j].speaker===2).speakerName)));
			assert.equal(exported.find((_,i)=>cues[i].speaker===2).speakerName,'');
			await (await dl).saveAs(output+'/speakers-'+width+'.mp4');
			if(width>=768){
				for(const lane of ['video','audio']){
					const clip=editor.locator('[data-'+lane+'-lane="0"] button[data-key]').first();
					await clip.click();await clip.press('Delete');
				}
				let mediaRequests=0;
				const watch=req=>{if(/\/video-edit\/(media|exports)\b/.test(req.url()))mediaRequests++};
				page.on('request',watch);
				await editor.getByRole('button',{name:/^(Exportar|Export)$/i}).click();
				assert.equal(await editor.getByRole('menuitem').count(),1);
				const download=page.waitForEvent('download');
				await editor.getByRole('menuitem',{name:'SRT',exact:true}).click();
				assert.equal(await readFile(await (await download).path(),'utf8'),originalSrt);
				assert.equal(mediaRequests,0);
				page.off('request',watch);
				for(let i=0;i<2;i++)await editor.getByRole('button',{name:/^(Desfazer|Undo)$/i}).click();
				console.log('PASS detached SRT without video or audio requests');
			}
			if(width<768) await editor.getByRole('button',{name:/^(Voltar|Back)$/i}).click();else await page.keyboard.press('Escape');
			await editor.waitFor({state:'hidden'});await page.close();console.log('PASS: '+width+' speaker turns, rename, preview and MP4');continue;
		}
		await editor.getByRole('button', { name: /^(Mídia|Media)$/i }).click();
		const asset = editor.locator('[data-video-edit-asset]').first();
		await asset.waitFor();
		assert(await editor.getByRole('button',{name:/^(Undo|Desfazer)$/}).isDisabled());
		assert.equal(await asset.locator('.tabular-nums').count(), 0);
		const sequenceTop=(await editor.locator('.edit-sequence').boundingBox()).y;
		await asset.locator('.truncate').dblclick();assert.equal(await asset.getAttribute('aria-pressed'),'false');
		const scrollbar = editor.getByRole('scrollbar', { name: /^(Rolagem da linha do tempo|Timeline scroll)$/i });
		await scrollbar.waitFor();
		assert.equal(await scrollbar.getAttribute('aria-disabled'), 'true');
		assert.equal(await track.getByRole('button').count(),1);
		if (width < 768) await editor.getByRole('button',{name:/^(Preview|Visualização)$/i}).click();
		const video = editor.locator('.edit-preview-viewport > video');
		await video.waitFor();
		assert(Math.abs((await editor.locator(".edit-sequence").boundingBox()).y-sequenceTop)<1, "Timeline moved after import");
		await editor.locator('svg.edit-wave path').first().waitFor();
		await page.waitForFunction(() => document.querySelector('.edit-monitor video')?.readyState >= 1);
		if (!toolsOnly && width===1440){
			const undo=editor.getByRole('button',{name:/^(Desfazer|Undo)$/i});
			async function pull(sel,dx,dy){const b=await editor.locator(sel).first().boundingBox();await page.mouse.move(b.x+b.width/2,b.y+b.height/2);await page.mouse.down();await page.mouse.move(b.x+b.width/2+dx,b.y+b.height/2+dy,{steps:5});await page.mouse.up();}
			await pull('.edit-video-track .edit-level',0,20);assert(Number(await video.evaluate(el=>getComputedStyle(el).opacity))<.9);await undo.click();
			await pull('.edit-audio-track .edit-level',0,18);
			assert.equal(await editor.getByRole('slider',{name:'Volume A1'}).inputValue(),'100');
			assert(Number(await video.evaluate(el=>el.volume))<.9);assert(await editor.locator('.edit-audio-track .edit-level.lowered').count());
			assert(await editor.locator('.edit-wave').first().evaluate(el=>new DOMMatrix(getComputedStyle(el).transform).d<.9));
			await undo.click();
			const widthOf=async sel=>(await editor.locator(sel).first().boundingBox()).width;
			const full=await widthOf('.edit-video-track .edit-clip-item');
			await pull('.edit-audio-track .edit-trim.edge-end',-38,0);
			assert((await widthOf('.edit-video-track .edit-clip-item'))<full-30);assert(Math.abs(await widthOf('.edit-audio-track .edit-clip-item')-await widthOf('.edit-video-track .edit-clip-item'))<1); await undo.click();
		}
		if (toolsOnly) {
			const original = await video.getAttribute('src');
			let maskRequests=0;page.on('request',r=>{if(r.url().endsWith('/selection'))maskRequests++});
			await video.evaluate(el=>el.dataset.continuity='original');
			const originalRect=await editor.locator('.edit-preview-viewport').boundingBox();
			const tools = editor.getByRole('button', {name: /^(Tools|Ferramentas)$/i});
			for (const [menu,label] of [
				[/^(Erase object|Apagar objeto)$/i,/^(Select what to erase|Clique no que deseja apagar)$/i],


			]) {
				const sample={x:Math.floor(originalRect.x+originalRect.width*.55),y:Math.floor(originalRect.y+originalRect.height*.3),width:32,height:18};
				await video.evaluate(async el=>{if(el.readyState<2||el.seeking) await new Promise(resolve=>el.addEventListener('seeked',resolve,{once:true}));});
				const before=await page.screenshot({clip:sample});
				await tools.click();
				const cards=editor.locator('.studio-tool-grid button');
				await cards.first().waitFor();
				const panel=editor.locator('.studio-tool-grid');
				if(width===1440) {
					await page.setViewportSize({width:1280,height:720});
					await page.waitForFunction(()=>{const p=document.querySelector('.tool-properties'),c=p?.querySelectorAll('.edit-tool-card')[5];return c && c.getBoundingClientRect().bottom<=p.getBoundingClientRect().bottom;});
					await editor.screenshot({path:output+'/six-tools-1280.png'});
					await page.setViewportSize({width,height});
				}
				assert(await cards.nth(5).evaluate(el=>el.getBoundingClientRect().bottom<=el.closest('.edit-properties').getBoundingClientRect().bottom),'Six tools must fit');
				const step=await cards.nth(2).evaluate(el=>el.getBoundingClientRect().top-el.parentElement.firstElementChild.getBoundingClientRect().top);
				await panel.dispatchEvent('wheel',{deltaY:120});
				assert(await panel.evaluate((el,step)=>Math.abs(el.scrollTop-Math.min(el.scrollHeight-el.clientHeight,step))<=1,step));
				await panel.dispatchEvent('wheel',{deltaY:-120});
				await editor.screenshot({path:`${output}/tool-cards-${width}.png`});
				assert.equal(await page.getByRole('menuitem',{name:/slow motion|câmera lenta/i}).count(),0);
				await page.getByRole('button',{name:menu}).click();
				const target = editor.getByRole('button',{name:label});
				await target.waitFor();
				const apply=editor.locator('.edit-monitor').getByRole('button',{name:/^(Apply|Aplicar)$/});
				assert.equal(await apply.count(),0);
				const cancel=editor.locator('.edit-monitor').getByRole('button',{name:/^(Cancel|Cancelar)$/});
				if(width>=768) assert.equal(await editor.locator('.studio-tool-grid button:disabled').count(),await cards.count()-1);
				await cancel.click();
				await tools.click();
				assert.equal(await editor.locator('.studio-tool-grid button:disabled').count(),0);
				await page.getByRole('button',{name:menu}).click();
				await target.waitFor();
				await target.evaluate(async(el,box)=>{
					const frames=[];for(let i=0;i<18;i++){
						await new Promise(requestAnimationFrame);
						const svg=el.querySelector('svg'),r=svg.viewBox.baseVal;
						if(svg.querySelector(':scope > image'))throw Error('Source frame replaced the native preview');
						const mat=svg.getScreenCTM(),a=new DOMPoint(0,0).matrixTransform(mat),b=new DOMPoint(r.width,r.height).matrixTransform(mat);
						frames.push([a.x,a.y,b.x-a.x,b.y-a.y]);
					}
					if(!frames.length || frames.some(f=>f.some((n,i)=>Math.abs(n-[box.x,box.y,box.width,box.height][i])>2)))throw Error('Picker shifted: '+JSON.stringify({box,frames}));
				},originalRect);
				assert(before.equals(await page.screenshot({clip:sample})), 'Unmasked preview pixels changed');
				const ruler=editor.locator('.edit-ruler'); const box=await ruler.boundingBox();
				const clipWidth=(await track.getByRole('button').first().boundingBox()).width;
				for(const x of [.21,.38,.12,.5])await ruler.click({position:{x:Math.floor(clipWidth*x),y:8}});
				assert.equal(await video.getAttribute('data-continuity'),'original');assert.equal(maskRequests,0);
				const response=page.waitForResponse(r=>r.url().endsWith('/selection'));
				await target.click();
				const maskResponse=await response; assert.equal(maskResponse.status(),200,maskResponse.ok()?'':await maskResponse.text());
				await target.locator('[data-maker-mask]').waitFor();
				const hint=await target.locator('../..').getByRole('status').boundingBox(), applyRect=await apply.boundingBox();
				assert(hint.y+hint.height<=applyRect.y || hint.x+hint.width<=applyRect.x);
				const clear=editor.getByRole('button',{name:/^(Limpar|Clear)$/});
				if(width>=768){await clear.hover();await page.getByRole('tooltip').filter({hasText:/^(Limpar|Clear)$/}).waitFor();}
				await editor.getByRole('button',{name:/^(Remove selection|Remover seleção)$/i}).click();
				const pos=await target.evaluate(el => {
					const svg=el.querySelector('svg'), {width,height}=svg.viewBox.baseVal;
					const p=new DOMPoint(width*.24,height*.22).matrixTransform(svg.getScreenCTM()), r=el.getBoundingClientRect();
					return {x:p.x-r.left,y:p.y-r.top};
				});
				await target.click({position:pos});
				await target.locator('[data-maker-mask]').waitFor();
				assert.equal(await target.locator('circle').count(),0);
				await target.locator('../..').getByRole('button',{name:/^(Undo|Desfazer)$/i}).click();
				await target.locator('[data-maker-mask]').waitFor();
				assert.equal(await target.locator('circle').count(),0);
				if(menu.test('Erase object')) await editor.screenshot({path:`${output}/automatic-mask-${width}.png`});
				if (process.env.NEVE_TEST_FULL_CLIP === '1' && width === 1440) {
						const [resp] = await Promise.all([
							page.waitForResponse(r => r.url().endsWith('/process') && r.request().method()==='POST', {timeout:180000}),
							editor.locator('.edit-monitor').getByRole('button',{name:/^(Apply|Aplicar)$/}).click()
						]);
						const params = resp.request().postDataJSON(), result = await resp.json();
						assert.equal(resp.status(),200,JSON.stringify(result));
						assert.equal(params.start,0);
						assert(params.anchor>params.end*.3 && params.anchor<params.end);
						assert(Math.abs(result.duration-params.end)<.09);
						await page.waitForFunction(src => document.querySelector('.edit-preview-viewport > video')?.getAttribute('src') !== src,original);
						assert.equal(await track.getByRole('button').count(),1);
						await editor.getByRole('button',{name:/^(Undo|Desfazer)$/i}).click();
						assert.equal(await video.getAttribute('src'),original);
						continue;
					}
				await ruler.click({position:{x:Math.min(Math.floor(box.width)-1,Math.ceil(clipWidth)+2),y:8}});
				const last=page.waitForResponse(r=>r.url().endsWith('/selection'));
				await target.click();const result=await last;
				assert(result.request().postDataJSON().start<await video.evaluate(el=>el.duration));
				assert.equal(result.status(),200, result.ok()?'':await result.text());
				await editor.getByRole('button',{name:/^(Cancel|Cancelar)$/i}).click();
				assert.equal(await video.getAttribute('src'),original);
			}
			await tools.click();
			const processed = page.waitForResponse(r => r.url().endsWith('/process') && r.request().method()==='POST');
			await page.getByRole('button',{name:/60 FPS/i}).click();
			assert.equal((await processed).status(),200);
			await page.waitForFunction(src => document.querySelector('.edit-preview-viewport > video')?.getAttribute('src') !== src,original);
			await editor.getByRole('button',{name:/^(Undo|Desfazer)$/i}).click();
			assert.equal(await video.getAttribute('src'),original);
			await editor.getByRole('button',{name:/^(Media|Mídia)$/i}).click();
			await editor.screenshot({path:`${output}/clip-tools-${width}.png`});
			assert.equal(await editor.locator('[data-video-edit-asset]').count(),1,'Derived media must not appear in the bin');
			if (width < 768) await editor.getByRole('button',{name:/^(Voltar|Back)$/i}).click();
			else await page.keyboard.press('Escape');
			const cleanup=page.waitForResponse(r=>r.url().endsWith('/discard'));
			await page.getByRole('button',{name:/^(Descartar|Discard)$/i,exact:true}).click();
			assert.equal((await cleanup).status(),200);
			await page.request.delete(base+"/api/v1/files/"+fileId);
			await page.close();
			console.log(`PASS: ${width} subject picker, real 60 FPS, undo`);
			continue;
		}
		await editor.getByRole('button', { name: /^(Reproduzir|Play)$/i }).click();
		await page.waitForFunction(() => document.querySelector('.edit-monitor video')?.currentTime > .2);
		const pause = editor.getByRole('button', { name: /^(Pausar|Pause)$/i });
		assert.equal(await pause.locator('svg rect').count(), 2);
		assert.equal(await pause.locator('svg').getAttribute('fill'), 'currentColor');
		await pause.click();
		const clock = editor.locator('.edit-sequence-time');
		const clockTicks = async () => (await clock.innerText()).split(':').map(Number).reduce((acc,n,i) => acc*(i===1?60:100)+n,0);
		const beforeStep = await clockTicks();
		await editor.getByRole('button',{name:/^(Próximo quadro|Next frame)$/i}).click();
		assert.equal(await clockTicks(),beforeStep+3);
		await editor.getByRole('button',{name:/^(Quadro anterior|Previous frame)$/i}).click();
		assert.equal(await clockTicks(),beforeStep);
		const ruler = editor.getByRole('slider', { name: /^(Posição de reprodução|Playhead)$/i });
		const box = await ruler.boundingBox();
		await page.mouse.click(box.x + box.width * .40, box.y + 10);
		await page.keyboard.press('Control+s');
		assert.equal(await track.getByRole('button').count(), 2);
		if (width >= 768) {
			const second = editor.locator('[data-video-edit-clip="1"]');
			const first = editor.locator('[data-video-edit-clip="0"]');
			const selection = await track.boundingBox();
			await page.mouse.move(selection.x + selection.width * .97, selection.y + 12);
			await page.mouse.down();
			await page.mouse.move(selection.x + selection.width * .32, selection.y + 30, { steps: 8 });
			await page.mouse.up();
			assert.equal(await track.locator('[aria-pressed="true"]').count(), 2);
			await first.click();
			await second.click({ modifiers: ['Control'] });
			assert.equal(await track.locator('[aria-pressed="true"]').count(), 2);
			await page.mouse.click(box.x + box.width * .22, box.y + 10);
			await page.keyboard.press('Control+s');
			assert.equal(await track.getByRole('button').count(), 3);
			await editor.getByRole('button', { name: /^(Desfazer|Undo)$/i }).click();
			const trackBounds = await track.boundingBox();
			const originalWidth = (await first.boundingBox()).width;
			await first.click();await first.dragTo(track, { targetPosition: { x: trackBounds.width * .96, y: 20 } });
			assert((await first.boundingBox()).width > originalWidth, 'Clips did not reorder');
			await editor.getByRole('button', { name: /^(Desfazer|Undo)$/i }).click();
		}
		await editor.getByRole('button', { name: /^(Desfazer|Undo)$/i }).click();
		assert.equal(await track.getByRole('button').count(), 1);
		await editor.getByRole('button', { name: /^(Refazer|Redo)$/i }).click();
		assert.equal(await track.getByRole('button').count(), 2);
		await editor.getByRole('button', { name: /^(Desfazer|Undo)$/i }).click();
		const edge = track.locator('[data-trim-edge="end"]').first();
		const handle = await edge.boundingBox();
		const clipWidth = (await track.getByRole('button').first().boundingBox()).width;
		await page.mouse.move(handle.x + handle.width / 2, handle.y + handle.height / 2);
		await page.mouse.down();
		await page.mouse.move(handle.x - 28, handle.y + handle.height / 2, { steps: 5 });
		await page.mouse.up();
		assert((await track.getByRole('button').first().boundingBox()).width < clipWidth);
		await editor.getByRole('button', { name: /^(Desfazer|Undo)$/i }).click();
		const mute = editor.getByRole('button', { name: /^(Silenciar|Mute audio track)$/i });
		await editor.getByRole('button', { name: /^(Reproduzir|Play)$/i }).click();
		await mute.click();
		assert(await video.evaluate(el => el.muted));
		assert(await editor.getByRole('button',{name:/^(Dessilenciar|Unmute audio track)$/i}).locator('svg').evaluate(el=>[...el.querySelectorAll('path')].some(p=>p.getAttribute('d')==='m16.5 14.5 5-5')));
		assert.equal(await editor.getByRole('slider', {name: 'Volume A1'}).inputValue(), '0');
		const mutedTime = await video.evaluate(el => el.currentTime);
		await page.waitForFunction(time => {
			const video = document.querySelector('.edit-monitor video');
			return !video.paused && video.currentTime > time + .14;
		}, mutedTime);
		await editor.getByRole('button', { name: /^(Dessilenciar|Unmute audio track)$/i }).click();
		assert.equal(await video.evaluate(el => el.muted), false);
		assert.equal(await video.evaluate(el => el.paused), false);
		await pause.click();
		const end = Number(await ruler.getAttribute('aria-valuemax'));
		for (const [selector, fraction] of [['.edit-video-track', .32], ['.edit-audio-track', .54], ['.edit-caption-track', .72], ['.edit-video-track', .97]]) {
			const row = await editor.locator(selector).boundingBox();
			await page.mouse.click(row.x + row.width * fraction, row.y + row.height / 2);
			assert(Math.abs(Number(await ruler.getAttribute('aria-valuenow')) / end - fraction) < .01);
		}
		await page.mouse.click(box.x + box.width * .40, box.y + 10);
		await track.hover();
		await page.keyboard.down('Control');
		await page.mouse.wheel(0, -180);
		await page.keyboard.up('Control');
		await page.waitForFunction(() => document.querySelector('.edit-timeline-scroll').scrollWidth > document.querySelector('.edit-timeline-scroll').clientWidth);
		await scrollbar.press('End');
		assert(await page.locator('#maker-timeline-scroll').evaluate(el => el.scrollLeft > 0));
		assert.equal(await track.getByRole('button').count(), 1);
		const editPrompt = editor.getByRole('textbox', { name: /^(Pedido de edição|Editing request)$/i });
		assert.equal(await editPrompt.count(), 0);
		assert.equal(await editor.getByRole('button', {name: /^(Edições rápidas|Quick edits)$/i}).count(), 0);
		const zoomOut = editor.getByRole('button', {name: /^(Reduzir|Zoom out timeline)$/i});
		if (width >= 768) {
			await zoomOut.hover();
			const tip = page.getByRole('tooltip').filter({hasText: /^(Reduzir|Zoom out timeline)$/i});
			await page.waitForTimeout(250);
			assert.equal(await tip.isVisible(), false);
			await tip.waitFor({timeout: 2500});
		}
		await zoomOut.click();
		const beforeZoom = await editor.locator('.edit-track-grid').evaluate(el => el.offsetWidth);
		await editor.getByRole('button', {name: /^(Ampliar|Zoom in timeline)$/i}).click();
		assert(await editor.locator('.edit-track-grid').evaluate(el => el.offsetWidth) > beforeZoom);
		assert.equal(await editor.getByRole('button', { name: /^(Clipe|Clip)$/i }).count(), 0);
		const volume = editor.getByRole('slider', { name: 'Volume A1' });
		await volume.press('Home');
		assert.equal(await video.evaluate(el => el.volume), 0);
		await volume.press('End');
		assert.equal(await video.evaluate(el => el.volume), 1);
		assert.equal(await editor.getByRole('slider', { name: 'Zoom V1' }).count(), 0);
		assert.equal(await editor.getByRole('button', {name:/^(Resolução|Resolution):/i}).count(), 0);
		assert.equal(await editor.getByRole('switch', { name: /^(Normalizar áudio|Normalize audio)$/i }).count(), 0);
		if (width < 768) await editor.getByRole('button', { name: /^(Visualização|Preview)$/i, exact: true }).click();
		await editor.screenshot({ path: `${output}/workspace-${width}-${theme}.png` });
		if (width === 1440) {
			await scrollbar.press('Home');
			const wideRuler = await ruler.boundingBox();
			await page.mouse.click(wideRuler.x + 65, wideRuler.y + 12);
			assert.equal(await editor.getByRole('button',{name:/^(Legendas|Captions)$/i}).count(),0);
			await editor.getByRole('button',{name:/^(Ferramentas|Tools)$/}).click();
			await editor.getByRole('button', { name: /^(Adicionar legenda|Add caption)$/i }).click();
			const cue = editor.locator('[data-caption-index="0"]').first();
			const cc = cue.locator('button').first();
			const vb=await track.boundingBox(),cb=await cue.boundingBox();
			const visibleTrack=await editor.locator('#maker-timeline-scroll').boundingBox();
			await page.mouse.move(Math.min(cb.x+cb.width+24,visibleTrack.x+visibleTrack.width-20),vb.y+12);await page.mouse.down();
			await page.mouse.move(cb.x+1,cb.y+cb.height/2,{steps:10});await page.mouse.up();
			for(const lane of ['video','audio','caption']) assert(await editor.locator('.edit-'+lane+'-track [aria-pressed=true]').count()>0,'Marquee missed '+lane);
			const selectedParts=()=>editor.locator('.edit-track [aria-pressed=true]').evaluateAll(nodes=>nodes.map(n=>n.dataset.key));
			const selectionBefore=await selectedParts();
			await editor.locator('header h2').click();
			assert.deepEqual(await selectedParts(),selectionBefore);
			await cc.click();
			await cc.press('Delete');
			assert.equal(await cue.count(),0);assert.equal(await track.getByRole('button').count(),1);
			await editor.getByRole('button',{name:/^(Undo|Desfazer)$/i}).click();
			await cc.click();
			const initial = await cue.boundingBox();
			await page.mouse.move(initial.x + initial.width / 2, initial.y + 12);
			await page.mouse.down();
			await page.mouse.move(initial.x + initial.width / 2 + 42, initial.y + 12, {steps: 6});
			await page.mouse.up();
			const moved = await cue.boundingBox();
			assert(Math.abs(moved.x - initial.x - 42) < 2, 'Caption was not moved');
			const edge = await cue.locator('[data-caption-edge="end"]').boundingBox();
			await page.mouse.move(edge.x + edge.width / 2, edge.y + 6);
			await page.mouse.down();
			await page.mouse.move(edge.x + edge.width / 2 + 28, edge.y + 6, {steps: 6});
			await page.mouse.up();
			assert(Math.abs((await cue.boundingBox()).width - moved.width - 28) < 2, 'Caption edge was not resized');
			for (let i = 0; i < 3; i++) await editor.getByRole('button', { name: /^(Desfazer|Undo)$/i }).click();
			await editor.getByRole('button', { name: /^(Mídia|Media)$/i }).click();
			await track.getByRole('button').first().click();
			await editor.getByRole('button',{name:/^(Tools|Ferramentas)$/i}).click();
			const response = page.waitForResponse(r => r.url().endsWith('/assist'));
			await page.getByRole('button',{name:/^(Equilibrar cores|Balance color)$/i}).click();
			assert.equal((await response).status(),200);
			assert.equal(await editor.getByRole('button',{name:/^(Legendas|Captions)$/i}).count(),0);
			await editor.getByRole('button',{name:/^(Ferramentas|Tools)$/}).click();
			await editor.getByRole('button', { name: /^(Adicionar legenda|Add caption)$/i }).click();
			const previewCaption = editor.locator('.edit-preview-caption');
			await previewCaption.waitFor();
			const pos=await previewCaption.boundingBox(), view=await editor.locator('.edit-preview-viewport').boundingBox();
			await page.mouse.move(pos.x+pos.width/2,pos.y+pos.height/2);
			await page.mouse.down();
			await page.mouse.move(view.x+view.width*.1,view.y+view.height*.1,{steps:8});
			await page.mouse.up();
			assert.equal(await previewCaption.getAttribute('data-position'),'top');
			for (const [label, value] of [[/^(Fonte|Font)$/i, 'Georgia'], [/^(Estilo|Style)$/i, /^(Destaque|Caption highlight)$/i]]) {
				const trigger=editor.getByRole('button', {name: label});
				await assertRotation(trigger.locator('svg'),()=>trigger.click());
				if(value==='Georgia') assert.equal(await editor.getByRole('menuitemradio',{name:/^(Segoe UI|Times New Roman|Trebuchet MS)$/}).count(),0);

				await assertRotation(trigger.locator('svg'),async()=>{
					const menu=editor.locator('.studio-caption-menu');
					assert(await menu.evaluate(el=>el.scrollHeight<=el.clientHeight+1));
					await editor.getByRole('menuitemradio', {name: value, exact: true}).click();
					assert.equal(await menu.count(),0);
				});
			}
			const size=editor.getByRole('spinbutton',{name:/^(Tamanho|Font size)$/i});
			await size.fill('24');await size.press('Tab');
			await editor.getByRole('button',{name:'Decrease'}).click();assert.equal(await size.inputValue(),'23');
			await editor.getByRole('button',{name:'Increase'}).click();assert.equal(await size.inputValue(),'24');
			const caption = editor.getByRole('textbox', { name: /^(Legenda|Caption)$/i }).first();
			await caption.waitFor();
			await caption.fill('');
			const capacityHeight=(await caption.boundingBox()).height;
			assert(await caption.evaluate(el=>el.clientHeight>3*parseFloat(getComputedStyle(el).lineHeight)));
			assert.match(await caption.evaluate(el=>getComputedStyle(el).fontFamily),/Segoe UI/);
			for(const partial of ['A','Legenda curta']){
				await caption.fill(partial);
				assert.equal((await caption.boundingBox()).height,capacityHeight,'Ordinary typing must not resize the caption field');
			}
			assert.equal(await editor.locator('.cue-count').count(),0);
			for(const sample of ['W'.repeat(120), 'A '+ 'W'.repeat(118)]){
				await caption.fill(sample);
				await caption.press('Control+Home');await caption.press('End');
				assert(await caption.evaluate((el,sample)=>{
					const s=getComputedStyle(el),ctx=document.createElement('canvas').getContext('2d');
					ctx.font=s.fontSize+' '+s.fontFamily;
					const width=el.clientWidth-parseFloat(s.paddingLeft)-parseFloat(s.paddingRight);
					const line=ctx.measureText(el.value.slice(0,el.selectionEnd)).width;
					return el.value===sample && line>width-2*ctx.measureText('W').width && line<=width+1;
				},sample),'First visual line should use the available width without inserting a newline');
			}
			for(const glyph of ['i','W','e\u0301','👩‍💻']){
				await caption.fill(glyph.repeat(181));
				assert.equal(await caption.inputValue(),glyph.repeat(180));
				assert(await caption.evaluate(el=>{
					const probe=el.cloneNode(false);
					probe.value=el.value;
					probe.style.cssText='height:0;min-height:0;max-height:none;overflow:hidden;visibility:hidden;';
					el.parentElement.append(probe);
					const needed=probe.scrollHeight;probe.remove();
					return el.clientHeight<=needed+1;
				}),'Empty lines reserved after reaching the limit with '+glyph);
				const geometry=await caption.evaluate(el=>[el,el.closest('.caption-details')].map(n=>({
					height:n.clientHeight,scroll:n.scrollHeight,width:n.clientWidth,bottom:n.getBoundingClientRect().bottom
				})));
				const [field,panel]=geometry;
				assert(panel.scroll<=panel.height+1,'Single caption must not scroll its timestamp out of the panel');
				assert(field.scroll<=field.height+1 || Math.abs(field.bottom-panel.bottom)<1,'Unused space or unexpected scrollbar for '+glyph+' '+JSON.stringify(geometry));
			}
			await caption.fill('Linha 1\nLinha 2');assert.equal(await caption.inputValue(),'Linha 1\nLinha 2');
			const twoLines=(await caption.boundingBox()).height;
			await caption.fill('Linha 1\n');assert.equal((await caption.boundingBox()).height,twoLines);
			await caption.fill('Linha 1');assert.equal((await caption.boundingBox()).height,capacityHeight);
			await caption.fill('A'.repeat(178)+'Z');
			await caption.evaluate(el=>el.setSelectionRange(178,178));
			await page.keyboard.insertText('123');
			assert.equal(await caption.inputValue(),'A'.repeat(178)+'1Z');
			assert.equal(await editor.getByRole('button',{name:/^(Adicionar legenda|Add caption)$/i}).count(),1);
			const long='Legenda longa com várias palavras e espaços. '.repeat(5).slice(0,180);
			await caption.fill(long);
			assert(await caption.evaluate(el=>el.scrollHeight<=el.clientHeight+1),'A full caption with spaces should fit the field');
			await caption.press('Tab');
			await editor.locator('.edit-caption-setting > span').first().click();
			assert.equal((await caption.inputValue()).trim(),long.trim());
			assert(await caption.evaluate(el=>{
				const time=el.closest('.edit-cue').querySelector('.edit-cue-time').getBoundingClientRect();
				const box=el.getBoundingClientRect();
				return box.top>=time.bottom+4 && el.scrollHeight<=el.clientHeight+1 &&
					Math.abs(box.left-time.left)<1 && el.scrollWidth<=el.clientWidth+1;
			}));
			await editor.locator('.edit-side').screenshot({path:output+'/caption-textarea.png'});
			const exportCaption='Legenda: '+'e\u0301'.repeat(171);
			await caption.fill(exportCaption);
			assert.equal(await caption.evaluate(el => getComputedStyle(el).outlineStyle),'none');
			await caption.press('Tab');
			const firstCue=editor.locator('[data-caption-index="0"]'), firstBox=await firstCue.boundingBox(), rr=await ruler.boundingBox();
			const xx=firstBox.x-rr.x>110?firstBox.x-90:firstBox.x+firstBox.width+60;
			await page.mouse.click(xx,rr.y+10);
			await editor.locator('.edit-caption-label').getByRole('button',{name:/^(Adicionar legenda|Add caption)$/i}).click();
			assert.equal(await editor.locator('.edit-cue textarea').count(),1);
			await editor.locator('[data-caption-index="1"] button').click(); await previewCaption.waitFor();
			assert.equal(await size.inputValue(),'18');
			assert.equal(await previewCaption.evaluate(el=>el.style.fontFamily),'Arial');
			await editor.getByRole('button',{name:/^(Ferramentas|Tools)$/i}).click();
			assert.equal(await editor.locator('.studio-tool-grid button:enabled').count(),0);
			await track.locator('[data-key]').first().click();
			assert.equal(await editor.getByRole('button',{name:/^(Legendas|Captions)$/i}).count(),0);
			assert.equal(await size.count(),0);
			await editor.locator('[data-caption-index="1"] button').click();
			await editor.getByRole('button',{name:/^(Legendas|Captions)$/i}).click();
			assert.equal(await previewCaption.getAttribute('data-horizontal'),'center');
			await firstCue.locator('button').click(); assert.equal(await previewCaption.getAttribute('data-horizontal'),'left',JSON.stringify(await editor.locator('.edit-sequence-time,.edit-preview-caption,[data-caption-index] button').allTextContents()));
			const secondBox=await editor.locator('[data-caption-index="1"]').boundingBox();
			const lo=Math.min(firstBox.x,secondBox.x), hi=Math.max(firstBox.x+firstBox.width,secondBox.x+secondBox.width);
			await page.mouse.move(lo-4,firstBox.y+4);await page.mouse.down();await page.mouse.move(hi+4,firstBox.y+firstBox.height/2,{steps:8});await page.mouse.up();
			assert.equal(await editor.locator('.edit-caption-track [aria-pressed=true]').count(),2);
			await firstCue.locator('button').click();
			assert.equal(await editor.locator('.edit-caption-track [aria-pressed=true]').count(),1);
			await page.mouse.move(lo-4,firstBox.y+4);await page.mouse.down();await page.mouse.move(hi+4,firstBox.y+firstBox.height/2,{steps:8});await page.mouse.up();
			assert.equal(await editor.locator('.edit-cue textarea').count(),0);
			await size.fill('26');await size.press('Tab');
			await previewCaption.press('ArrowRight');
			
			const exportButton = editor.getByRole('button', { name: /^(Exportar|Export)$/i });
			assert.equal((await exportButton.textContent()).trim(), '');
			assert.equal(await editor.locator('header').getByRole('button', { name: /^(Importar|Import)$/i }).count(), 0);
			await editor.locator('.edit-audio-label').filter({hasText: 'A1'}).getByRole('button', { name: /^(Silenciar|Mute audio track)$/i }).click();
			const request = page.waitForRequest(request => request.url().endsWith('/api/v1/video-edit/exports') && request.method() === 'POST');
			const downloaded=page.waitForEvent('download',{timeout:120000});
			await exportButton.click();
			await editor.getByRole('menuitem',{name:'MP4',exact:true}).click();
			await editor.getByRole('menuitem',{name:'480p',exact:true}).waitFor();
			for (const height of [480,720,1080]) assert(await editor.getByRole('menuitem', {name:`${height}p`,exact:true}).isVisible());
			await editor.getByRole('menuitem', {name:'720p',exact:true}).click();
			const exportSettings = (await request).postDataJSON();
			assert.equal(exportSettings.captions[0].text,exportCaption);
			const progress=editor.getByRole('progressbar');
			await page.waitForFunction(()=>document.querySelector('.edit-export-progress')?.value>=10);
			const pixels=await progress.screenshot();
			assert(await page.evaluate(async data=>{
				const img=new Image();img.src='data:image/png;base64,'+data;await img.decode();
				const canvas=document.createElement('canvas');canvas.width=img.width;canvas.height=img.height;
				const ctx=canvas.getContext('2d');ctx.drawImage(img,0,0);
				const row=ctx.getImageData(0,Math.floor(img.height/2),img.width,1).data;
				return row.some((r,i)=>!(i%4) && row[i+2]>r+40 && row[i+2]>row[i+1]+20);
			},pixels.toString('base64')),'Expected visible blue export progress');
			assert.equal(await progress.evaluate(el=>getComputedStyle(el).borderTopLeftRadius),'3px');
			assert(exportSettings.clips.every(clip => clip.gain === 0));
			assert.equal(exportSettings.height, 720);
			assert.equal(exportSettings.normalize, false);
			assert(exportSettings.captions.every(c=>c.style.size===26));
			assert(exportSettings.clips.some(clip => clip.grade != null));
			assert.equal(exportSettings.captions[0].style.font,'Georgia');assert.equal(exportSettings.captions[1].style.font,undefined);assert.equal(exportSettings.captions.length,2);assert(exportSettings.captions.every(c=>c.horizontal==='center' && c.position==='top'));
			const download=await downloaded;
			assert.equal(download.suggestedFilename(), 'Neve-Studio.mp4');
			await download.saveAs(output + '/exported.mp4');
			const data = await readFile(output + '/exported.mp4');
			assert(data.length > 10000 && data.subarray(4, 8).toString() === 'ftyp');
			await editor.locator('.edit-caption-label').getByRole('button',{name:/^(Adicionar legenda|Add caption)$/i}).click();
		}
		const bounds = await editor.boundingBox();
		assert(bounds.x >= 0 && bounds.x + bounds.width <= width + 1);
		assert(bounds.height <= height + 1);
		for (const control of [editor.getByRole('button', { name: /^(Exportar|Export)$/i }), editor.getByRole('button', { name: /^(Tools|Ferramentas)$/i }), video]) {
			const rect = await control.boundingBox();
			assert(rect.x >= 0 && rect.x + rect.width <= width + 1, 'Editor control overflows the viewport');
		}
		await editor.screenshot({ path: `${output}/editor-${width}-${theme}.png` });
		if (width < 768) await editor.getByRole('button', { name: /^(Voltar|Back)$/i }).click();
		else await page.keyboard.press('Escape');
		await page.getByRole('button',{name:/^(Cancelar|Cancel)$/i,exact:true}).click();
		assert(await video.getAttribute('src'));
		await editor.getByRole('button', { name: /^(Mídia|Media)$/i }).click();
		await editor.locator('[data-video-edit-asset] .truncate').click();
		const binRemove=editor.getByRole('button',{name:/^(Excluir mídia|Delete media)$/i});
		if(width>=768){
			await asset.click(); assert.equal(await binRemove.count(),0);
			const ghost=await asset.evaluate(el=>{const data=new DataTransfer();let node;data.setDragImage=i=>node=i;el.dispatchEvent(new DragEvent('dragstart',{bubbles:true,dataTransfer:data}));return node?.tagName;});
			assert.equal(ghost,'IMG'); assert.equal(await asset.getAttribute('aria-pressed'),'false');
			assert.equal(await asset.evaluate(el=>getComputedStyle(el).cursor),'grabbing');
			await asset.dispatchEvent('dragend');assert.equal(await binRemove.count(),0);
			await asset.click();assert.equal(await asset.getAttribute('aria-pressed'),'true');
		}
		await binRemove.click();assert.equal(await editor.locator('[data-video-edit-asset]').count(),0);
		assert.equal(await editor.locator('.edit-preview-viewport').count(),0);
		assert.equal((await editor.locator('.edit-monitor').innerText()).trim(),'');
		await editor.getByRole('button',{name:/^(Desfazer|Undo)$/i}).click();
		assert.equal(await editor.locator('[data-video-edit-asset]').count(),1);
		const trash=editor.getByRole('button',{name:/^(Excluir mídia|Delete media)$/i});assert.equal(await trash.count(),0);
		const audio=editor.locator('[data-audio-lane="0"] button').first();
		const picture=track.getByRole('button').first(), undo=editor.getByRole('button',{name:/^(Undo|Desfazer)$/});
		await audio.click(); await audio.press('Delete');assert.equal(await audio.count(),0);assert(await picture.isVisible());await undo.click();
		await picture.click();await picture.press('Delete');assert.equal(await picture.count(),0);assert(await audio.isVisible());
		const onlyAudio=editor.locator('.edit-audio-track .edit-clip-item').first();
		const audioWidth=(await onlyAudio.boundingBox()).width;
		const edgeA=onlyAudio.locator('[data-trim-edge=start]');
		await edgeA.scrollIntoViewIfNeeded(); const ah=await edgeA.boundingBox();await page.mouse.move(ah.x+ah.width/2,ah.y+ah.height/2);await page.mouse.down();await page.mouse.move(ah.x+ah.width/2+20,ah.y+ah.height/2,{steps:4});await page.mouse.up();
		assert((await onlyAudio.boundingBox()).width<audioWidth-12);assert.equal(await picture.count(),0);await undo.click();
		await audio.click();await audio.press('Delete');assert.equal(await audio.count(),0);
		assert.equal(await editor.locator('[data-mobile-modal-close]').evaluate(el=>el.matches(':hover,:focus-visible')),false);
		await undo.click();await undo.click();
				if (width === 1440) {
			const dragData = await page.evaluateHandle(() => new DataTransfer());
			const source = editor.locator('[data-video-edit-asset]').first();
			for (const [role, dataLane] of [[/^(Nova faixa de vídeo|New video track)$/i, 'data-video-lane'], [/^(Nova faixa de áudio|New audio track)$/i, 'data-audio-lane']]) {
				const lane = `[${dataLane}="${await editor.locator(`[${dataLane}]`).count()}"]`;
				await source.dispatchEvent('dragstart', { dataTransfer: dragData });
				assert.equal(await trash.isVisible(), false);
				const drop = editor.getByRole('region', { name: role });
				const rect = await drop.boundingBox();
				assert.equal((await drop.textContent()).trim(), '');
				await drop.dispatchEvent('dragover', { dataTransfer: dragData, clientX: rect.x + 1, clientY: rect.y + 3 });
				assert.equal(await drop.evaluate(el => getComputedStyle(el, '::after').height), '2px');
				await drop.dispatchEvent('drop', { dataTransfer: dragData, clientX: rect.x + 1, clientY: rect.y + 3 });
				await editor.locator(lane).waitFor({ state: 'attached' });
			}
			assert(await editor.locator('.edit-timeline').evaluate(el => el.scrollHeight > el.clientHeight));
			const viewport = editor.locator('.edit-timeline');
			const fixedY=(await ruler.boundingBox()).y;
			await viewport.evaluate(el=>el.scrollTop=el.scrollHeight);
			assert.equal((await ruler.boundingBox()).y,fixedY);
			const savedY = await viewport.evaluate(el => { el.scrollTop = 0; return el.scrollTop; });
			const shrink = editor.getByRole('button', {name: /^(Reduzir|Zoom out timeline)$/i});
			for (let i = 0; i < 20 && await shrink.isEnabled(); i++) await shrink.click();
			await editor.locator('.fixed-ruler').hover();
			await page.mouse.wheel(0, 180);
			assert.equal(await viewport.evaluate(el => el.scrollTop), savedY);
			await editor.getByRole('button', {name: /^(Ampliar|Zoom in timeline)$/i}).click();
			await scrollbar.press('Home');
			await editor.locator('.fixed-ruler').hover();
			await page.mouse.wheel(0, 180);
			await page.waitForFunction(() => document.querySelector('#maker-timeline-scroll').scrollLeft > 0);
			assert.equal(await viewport.evaluate(el => el.scrollTop), savedY);
			const r=await viewport.boundingBox(), h=await editor.locator('#maker-timeline-scroll').boundingBox();
			await scrollbar.press('Home');
			await page.mouse.move(h.x+50,r.y+3);await page.mouse.down();await page.mouse.move(h.x+h.width-3,r.y+r.height-4,{steps:12});
			await page.waitForFunction(()=>document.querySelector('#maker-timeline-scroll').scrollLeft>30 && document.querySelector('.edit-timeline').scrollTop>20);
			await page.mouse.move(h.x+2,r.y+2,{steps:5});
			await page.waitForFunction(()=>document.querySelector('#maker-timeline-scroll').scrollLeft===0 && document.querySelector('.edit-timeline').scrollTop===0);
			await page.mouse.up();
			await page.mouse.click(h.x+25,r.y+3);assert.equal(await editor.locator('.edit-track [aria-pressed=true]').count(),0);
			await dragData.dispose();
			let imports = 0;
			await page.route('**/api/v1/video-edit/media', async route => {
				imports++;
				await route.fulfill({ json: { id: 'f900a6c034064b20ab151a12a0d90c51', name: 'arrastado.mp4', duration: 1, width: 320, height: 240, fps: 30, audio: false } });
			});
			const files = await page.evaluateHandle(() => {
				const data = new DataTransfer();
				data.items.add(new File(['video drop fixture'], 'arrastado.mp4', { type: 'video/mp4' }));
				return data;
			});
			await page.locator('#chat-pane').dispatchEvent('dragover', { dataTransfer: files });
			await editor.locator('header').dispatchEvent('dragover', { dataTransfer: files });
			await editor.locator('header').dispatchEvent('drop', { dataTransfer: files });
			await editor.getByText('arrastado.mp4', { exact: true }).waitFor();
			assert.equal(imports, 1);
			const cards = editor.locator('[data-video-edit-asset]');
			assert.equal(await cards.count(), 2);
			await cards.nth(0).locator('.truncate').click();
			await cards.nth(1).locator('.truncate').click();
			assert.equal(await editor.locator('[data-video-edit-asset][aria-pressed=true]').count(),2);
			await trash.click();assert.equal(await cards.count(),0);await undo.click();assert.equal(await cards.count(),2);
			await page.locator('#dropzone').waitFor({ state: 'hidden' });
			await files.dispose();
			await page.unroute('**/api/v1/video-edit/media');
		}
		if (width < 768) await editor.getByRole('button', { name: /^(Voltar|Back)$/i }).click();
		else await page.keyboard.press('Escape');
		const discardRequest = page.waitForResponse(r=>r.url().endsWith('/discard'));
		await page.getByRole('button',{name:/^(Descartar|Discard)$/i,exact:true}).click();
		assert.equal((await discardRequest).status(),200);
		await editor.waitFor({ state:'hidden' });
		assert.equal(await slots.locator('[data-video-mode-edit]').count(),0);
		assert((await page.request.delete(base+'/api/v1/files/'+fileId)).ok());
		if (width===1440) {
			const upload = page.waitForResponse(r=>r.url().endsWith('/video-edit/media')&&r.request().method()==='POST');
			await composerUpload.setInputFiles(fixture);
			const archived=(await (await upload).json()).fileId;
			try {
				assert(archived);
				await slots.locator('[data-video-mode-edit]').click();
				await editor.waitFor();
				const exported=page.waitForEvent('download',{timeout:120000});
				await editor.getByRole('button',{name:/^(Exportar|Export)$/i}).click();await editor.getByRole('menuitem',{name:'MP4',exact:true}).click();await editor.getByRole('menuitem',{name:'480p'}).click();
				await exported;await page.keyboard.press('Escape');await editor.waitFor({state:'hidden'});
				assert.equal(await page.getByRole('button',{name:/^(Descartar|Discard)$/i}).count(),0);
				assert((await page.request.get(base+'/api/v1/files/'+archived)).ok());
			} finally { if(archived) await page.request.delete(base+'/api/v1/files/'+archived); }
		}
		await picker.click();
		await page.getByRole('menuitemradio', { name: 'Neve Video 1.5' }).click();
		assert.match(await picker.innerText(), /Neve Video 1.5/);
		if (width >= 768) {
			await page.locator('#video-resolution-dropdown-container button').click();
			const settings = page.locator('#video-settings-panel');
			await settings.waitFor();
			assert(await settings.evaluate(el => el.getAnimations().length > 0));
			await page.keyboard.press('Escape');
			await settings.waitFor({ state: 'detached' });
		}
		if (!native) await page.close();
		console.log(`PASS: ${native ? 'WebView2' : theme} ${width} import, play, split, undo/redo, modal reopen${width === 1440 ? ', offline color, individual and group caption placement, discard and automatic MP4' : ''}`);
	}
	assert.deepEqual(issues, []);
} finally {
	for(const id of archivedTests)await fetch(base+'/api/v1/files/'+id,{method:'DELETE'}).catch(()=>{});
	await browser?.close();
	host?.kill();
}
