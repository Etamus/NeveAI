import assert from 'node:assert/strict';
import { chromium } from '../logs/ui-image-26/node_modules/playwright/index.mjs';

const base = process.env.NEVE_TEST_ORIGIN ?? 'http://localhost:8080';
const browser = await chromium.launch({args:['--enable-webgl','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await context.newPage();
let resultId;
try {
	const errors = [];
	const profile = process.env.NEVE_3D_TEST_PROFILE ?? 'standard';
	page.on('pageerror', error => errors.push(error.message));
	await page.goto(base + '/?temporary-chat=true', {waitUntil:'networkidle'});
	await page.locator('#input-menu-button').click();
	await page.getByRole('button', {name:/Criar modelo|Create model/}).click();
	await page.locator('[data-model3d-integration]').waitFor();
	if (profile !== 'standard') {
		await page.locator('#mesh-quality-dropdown-container > button').click();
		await page.getByRole('menuitemradio', {name: profile === 'draft' ? /Rascunho|Draft/ : /Alta qualidade|High quality/}).click();
	}
	assert.equal(await page.locator('#send-message-button').isEnabled(), false);
	await page.locator('#input-menu-button').click();
	const attach = page.getByText(/^(Adicionar anexos|Add attachments)$/).last();
	await attach.waitFor();
	const [chooser] = await Promise.all([page.waitForEvent('filechooser'), attach.click()]);
	await chooser.setFiles(process.env.NEVE_3D_TEST_IMAGE ?? 'backend/data/cache/mesh_generation/smoke/reference.png');
	await page.waitForFunction(() => !document.querySelector('#send-message-button')?.disabled, null, {timeout:8000});
	const request = page.waitForRequest(r => r.url().includes('/api/chat/completions') && r.method() === 'POST');
	const start = Date.now();
	await page.locator('#send-message-button').click();
	const payload = (await request).postDataJSON();
	assert.equal(payload.features.model3d_generation, true);
	assert.equal(payload.features.model3d_quality, profile);
	assert.equal(payload.features.stable_diffusion, false);
	const progress = page.getByRole('progressbar', {name:/Criar modelo|Create model/i});
	await progress.waitFor({timeout:120000});
	assert.equal(await page.locator('[data-mesh-result]').count(), 0);
	if (process.env.NEVE_3D_CANCEL_TEST === '1') {
		await page.waitForFunction(async () => (await (await fetch('/llamacpp/media-state')).json()).busy, null, {timeout:120000});
		await page.getByText('Criando modelo', {exact:true}).first().waitFor({timeout:120000});
		await page.locator('#send-message-button[type="button"]').click();
		await page.waitForFunction(async () => {
			const [media, jobs] = await Promise.all(['/llamacpp/media-state','/api/tasks'].map(async url => (await fetch(url)).json()));
			return media.busy === false && Array.isArray(jobs.tasks) && !jobs.tasks.length;
		},null,{timeout:45000});
		assert.equal(await page.locator('[data-mesh-result]').count(), 0);
		assert.equal(await progress.count(), 0);
		assert.deepEqual(errors, []);
		console.log('PASS: cancellation releases the GPU slot and publishes no output');
	} else {
	const result = page.locator('[data-mesh-result]').first();
	await result.waitFor({timeout:600000});
	assert.equal(await progress.count(), 0);
	resultId = await result.getAttribute('data-mesh-result');
	console.log('Generated in', (Date.now() - start) / 1000, 'seconds');
	await result.scrollIntoViewIfNeeded();
	const canvas = result.locator('canvas[aria-label]');
	await canvas.waitFor();
	await page.waitForFunction(() => [...document.querySelectorAll('canvas[aria-label]')].at(-1)?.width > 310);
	await canvas.scrollIntoViewIfNeeded();
	const before = await canvas.screenshot({path:'logs/model3d-chat-preview.png'});
	const foreground = await page.evaluate(async bytes => {
		const bitmap = await createImageBitmap(new Blob([new Uint8Array(bytes)], {type:'image/png'}));
		const canvas = new OffscreenCanvas(bitmap.width, bitmap.height);
		const ctx = canvas.getContext('2d');
		ctx.drawImage(bitmap,0,0);
		const pixels = ctx.getImageData(0,0,bitmap.width,bitmap.height).data;
		const colors = new Set();
		for(let i=0;i<pixels.length;i+=32) colors.add((pixels[i]<<16)|(pixels[i+1]<<8)|pixels[i+2]);
		return colors.size;
	}, [...before]);
	assert(foreground > 25, '3D canvas is not blank');
	const box = await canvas.boundingBox();
	await page.mouse.move(box.x + box.width/2, box.y + box.height/2);
	await page.mouse.down();
	await page.mouse.move(box.x + box.width*.73, box.y + box.height*.55,{steps:8});
	await page.mouse.up();
	assert(!(await canvas.screenshot()).equals(before), 'orbit changes the visible model');
	assert.equal(await page.getByRole('dialog').count(), 0, 'the chat preview is inline');
	for (const format of ['3mf','stl','obj','fbx']) {
		await result.getByRole('button', {name:/Formato|File format/}).click();
		await page.getByRole('menuitemradio', {name:new RegExp('^' + format.toUpperCase())}).click();
		const download = page.waitForEvent('download',{timeout:180000});
		await result.getByRole('button',{name:/^(Baixar|Download)$/}).click();
		assert((await download).suggestedFilename().endsWith('.'+(format==='obj'?'zip':format)));
	}
	await page.setViewportSize({width:390,height:820});
	await page.goto(base+'/library',{waitUntil:'networkidle'});
	await page.locator('button').filter({hasText:/^Tudo$|^All$/}).first().waitFor();
	const item = page.getByRole('button',{name:/^modelo-neve-.*\.glb$/}).first();
	await item.click();
	const mobile = page.locator('[data-mesh-result] canvas');
	await mobile.waitFor();
	await page.waitForFunction(() => document.querySelector('[data-mesh-result] canvas')?.width > 300);
	await mobile.screenshot({path:'logs/model3d-library-mobile.png'});
	assert.deepEqual(errors,[]);
	console.log('PASS: chat, four authenticated downloads, library and interactive 3D view');
	}
} catch (error) {
	console.error((await page.locator('body').innerText()).slice(-3500));
	await page.screenshot({path:'logs/model3d-e2e-failure.png'});
	throw error;
} finally {
	if (resultId) {
		const token = await page.evaluate(() => localStorage.token).catch(() => '');
		await context.request.delete(base + '/api/v1/files/' + resultId,{headers:token?{Authorization:'Bearer '+token}:{}}).catch(()=>{});
	}
	await browser.close();
}
