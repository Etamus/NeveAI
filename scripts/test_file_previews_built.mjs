import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import { jsPDF } from 'jspdf';
import JSZip from 'jszip';
import * as XLSX from 'xlsx';
import { chromium } from '../logs/ui-image-26/node_modules/playwright/index.mjs';
import { installMobileOfflineApi } from './fixtures/mobile-offline-api.mjs';

const base = process.env.NEVE_TEST_ORIGIN ?? 'http://localhost:8080';
const cache = 'backend/data/cache/mesh_generation/smoke';
const glb = await fs.readFile(process.env.NEVE_TEST_GLB ?? cache + '/neve-3d_00001_.glb');
function rigFixture() {
	const buffers = [new Float32Array([-1,-1,0,1,-1,0,0,1,0]), new Uint8Array(12), new Float32Array([1,0,0,0,1,0,0,0,1,0,0,0])];
	const bytes = Buffer.concat(buffers.map(a=>Buffer.from(a.buffer)));
	return JSON.stringify({asset:{version:'2.0'},scene:0,scenes:[{nodes:[0,1]}],
		nodes:[{mesh:0,skin:0},{children:[2]},{translation:[0,.8,0]}],skins:[{joints:[1,2]}],
		meshes:[{primitives:[{attributes:{POSITION:0,JOINTS_0:1,WEIGHTS_0:2}}]}],
		accessors:[{bufferView:0,componentType:5126,type:'VEC3',count:3,min:[-1,-1,0],max:[1,1,0]},
			{bufferView:1,componentType:5121,type:'VEC4',count:3},{bufferView:2,componentType:5126,type:'VEC4',count:3}],
		bufferViews:[{buffer:0,byteOffset:0,byteLength:36},{buffer:0,byteOffset:36,byteLength:12},{buffer:0,byteOffset:48,byteLength:48}],
		buffers:[{byteLength:bytes.length,uri:'data:application/octet-stream;base64,'+bytes.toString('base64')}]});
}
const png = await fs.readFile(cache + '/reference.png');
const video = await fs.readFile('logs/video-audio-20261102/vdn-text.mp4');
const text = Array.from({ length: 200 }, (_, i) => 'Preview text, line ' + (i + 1)).join('\n');
const pdf = new jsPDF();
pdf.text('Preview PDF', 20, 20);
for (let i = 2; i <= 32; i++) { pdf.addPage(); pdf.text('Preview page ' + i, 20, 20); }
const workbook = XLSX.utils.book_new();
for (const heading of ['First', 'Second']) {
	XLSX.utils.book_append_sheet(workbook, XLSX.utils.aoa_to_sheet([[heading + ' tab content']]), heading);
}
const slides = new JSZip();
slides.file('ppt/presentation.xml', '<p:presentation xmlns:p="p"><p:sldSz cx="9144000" cy="5143500"/></p:presentation>');
for (const i of [1, 2]) {
	slides.file('ppt/slides/slide' + i + '.xml', '<p:sld xmlns:p="p" xmlns:a="a"><p:spTree><p:sp><p:spPr><a:xfrm><a:off x="190500" y="190500"/><a:ext cx="6000000" cy="1100000"/></a:xfrm></p:spPr><p:txBody><a:p><a:r><a:rPr sz="2400"/><a:t>Preview slide</a:t></a:r></a:p></p:txBody></p:sp></p:spTree></p:sld>');
}
const documents = {
	'pdf-test': Buffer.from(pdf.output('arraybuffer')),
	'xlsx-test': XLSX.write(workbook, { type: 'buffer', bookType: 'xlsx' }),
	'pptx-test': await slides.generateAsync({ type: 'nodebuffer' })
};
const library = [
	{ id: 'mesh-test', filename: 'Model.glb', meta: { content_type: 'model/gltf-binary', size: glb.length, data: { source: 'neve-model3d' } } },
	{ id: 'text-test', filename: 'Notes.txt', meta: { content_type: 'text/plain', size: text.length, data: {} } },
	{ id: 'image-test', filename: 'Picture.png', meta: { content_type: 'image/png', size: png.length, data: {} } },
	{ id: 'pdf-test', filename: 'Preview.pdf', meta: { content_type: 'application/pdf' } },
	{ id: 'xlsx-test', filename: 'Table.xlsx', meta: { content_type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' } },
	{ id: 'pptx-test', filename: 'Slides.pptx', meta: { content_type: 'application/vnd.openxmlformats-officedocument.presentationml.presentation' } }
];
const model = 'local/mobile-fixture';
const history = { currentId: 'mesh-response', messages: {
	'mesh-user': { id: 'mesh-user', role: 'user', content: 'Model this', parentId: null, childrenIds: ['mesh-response'], timestamp: 1700000000 },
	'mesh-response': { id: 'mesh-response', role: 'assistant', content: '', done: true, model, parentId: 'mesh-user', childrenIds: [], timestamp: 1700000001,
		statusHistory: [{ action: 'model3d_generation', description: 'Modelo 3D criado', done: true }],
		files: [{ id: 'mesh-test', name: 'Model.glb', type: 'model3d' }] }
} };
const mediaHistory = { ...history, messages: { ...history.messages, 'mesh-response': {
	...history.messages['mesh-response'], statusHistory: [], files: [
		{ name: 'Picture.png', type: 'image', url: '/api/v1/files/image-test/content' },
		{ name: 'Video.mp4', type: 'video', url: '/api/v1/files/video-test/content' }
	]
} } };
async function checkFullscreenToolbar(page, overlay) {
	await overlay.waitFor();
	const close = overlay.locator('[data-window-close]');
	const [download, dismiss] = await Promise.all([
		overlay.getByRole('button', { name: /^(Download|Baixar)$/ }).first().boundingBox(),
		close.boundingBox()
	]);
	assert(dismiss.x >= download.x + download.width && Math.abs(dismiss.y - download.y) < 1);
	await close.click();
	await overlay.waitFor({ state: 'hidden' });
}
const browser = await chromium.launch({ args: ['--enable-webgl', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
try {
	for (const width of [1440, 390]) {
		const page = await browser.newPage({ viewport: { width, height: width === 390 ? 820 : 900 } });
		const errors = [];
		page.on('pageerror', error => errors.push(error.message));
		await page.addInitScript(() => {
			for (const type of [Map, WeakMap]) if (!type.prototype.getOrInsertComputed) {
				Object.defineProperty(type.prototype, 'getOrInsertComputed', { value(key, compute) {
					if (!this.has(key)) this.set(key, compute(key));
					return this.get(key);
				} });
			}
		});
		await installMobileOfflineApi(page);
		await page.route('**/api/config', route => route.fulfill({ json: {
			name: 'Neve AI', version: '3.0.20', default_models: model,
			features: { auth: false, enable_websocket: false, enable_stable_diffusion: true, enable_model3d_generation: true }
		} }));
		await page.route('**/api/v1/chats/mesh-test', route => route.fulfill({ json: {
			id: 'mesh-test', title: 'Mesh example', user_id: 'mobile-fixture-user', chat: { title: 'Mesh example', history, models: [model] }
		} }));
		await page.route('**/api/v1/chats/media-test', route => route.fulfill({ json: {
			id: 'media-test', title: 'Media example', user_id: 'mobile-fixture-user',
			chat: { title: 'Media example', history: mediaHistory, models: [model] }
		} }));
		await page.route('**/api/tasks/**', route => route.fulfill({ json: { task_ids: [] } }));
		await page.route('**/api/v1/files/generated?*', route => route.fulfill({ json: library }));
		let meshFetches=0;
		await page.route('**/api/v1/files/*/content*', route => {
			const id = new URL(route.request().url()).pathname.split('/').at(-2);
			if (id === 'mesh-test') meshFetches++;
			if (documents[id]) return route.fulfill({ body: documents[id], contentType: library.find(file => file.id === id).meta.content_type });
			if (id === 'video-test') return route.fulfill({ body: video, contentType: 'video/mp4' });
			return route.fulfill(id === 'mesh-test' ? { body: glb, contentType: 'model/gltf-binary' } :
				id === 'image-test' ? { body: png, contentType: 'image/png' } : { body: text, contentType: 'text/plain' });
		});
		await page.goto(base + '/c/mesh-test', { waitUntil: 'networkidle' });
		const status = page.locator('.status-description').filter({ hasText: /Modelo criado|Model created/ });
		await status.waitFor();
		assert.equal(await status.locator('svg').count(), 0);
		const result = page.locator('[data-mesh-result="mesh-test"]');
		assert.equal(await result.locator('[data-mesh-name]').getAttribute('title'), null);
		await result.scrollIntoViewIfNeeded();
		const canvas = result.locator('canvas');
		await page.waitForFunction(() => document.querySelector('[data-mesh-result] canvas')?.width > 310);
		await canvas.scrollIntoViewIfNeeded();
		const before = await canvas.screenshot({ path: 'logs/mesh-inline-' + width + '.png' });
		const colors = await page.evaluate(async bytes => {
			const bitmap = await createImageBitmap(new Blob([new Uint8Array(bytes)], { type: 'image/png' }));
			const surface = new OffscreenCanvas(bitmap.width, bitmap.height);
			const ctx = surface.getContext('2d');
			ctx.drawImage(bitmap, 0, 0);
			const data = ctx.getImageData(0, 0, bitmap.width, bitmap.height).data;
			const colors = new Set();
			for (let i = 0; i < data.length; i += 32) colors.add((data[i] << 16) | (data[i + 1] << 8) | data[i + 2]);
			return colors.size;
		}, [...before]);
		assert(colors > 25, 'Mesh preview must be visibly rendered');
		const view = result.locator('[data-mesh-view]');
		const centerPixels = async () => {
			const {x,y,width:w,height:h}=await canvas.boundingBox();
			return page.screenshot({clip:{x:x+w*.28,y:y+h*.28,width:w*.44,height:h*.44}});
		};
		const frames = [await centerPixels()];
		for (const [i, label] of [/Solid surface|Sólido/, /Wireframe|Malha/, /Surface normals|Normais/, /Textured|Textura/].entries()) {
			await view.click();
			assert.equal(await page.getByRole('menuitemradio', {name:/Skeleton|Esqueleto/}).count(), 0);
			await page.getByRole('menuitemradio', {name:label}).click();
			await page.mouse.move(0,0);
			await canvas.screenshot({path:`logs/mesh-inspect-${width}-${i}.png`});
			const frame = await centerPixels();
			if (i < 3) assert(!frames.some(f=>f.equals(frame)), 'distinct inspection render');
			else assert(frames[0].equals(frame), 'restoring texture restores original render');
			frames.push(frame);
		}
		assert.equal(meshFetches, 1, 'inspection does not reload the file');
		const box = await canvas.boundingBox();
		await page.mouse.move(box.x + box.width * .48, box.y + box.height * .40);
		await page.mouse.down();
		await page.mouse.move(box.x + box.width * .70, box.y + box.height * .40, { steps: 8 });
		await page.mouse.up();
		const rotated = await canvas.screenshot();
		assert(!rotated.equals(before), 'Dragging should rotate the model');
		const scroll = () => page.locator('#messages-container').evaluate(node => node.scrollTop);
		const top = await scroll();
		await canvas.hover();
		await page.mouse.wheel(0, -400);
		assert(!(await canvas.screenshot()).equals(rotated), 'Normal wheel should zoom the model');
		assert.equal(await scroll(), top, 'Zoom should not scroll the chat');
		assert.equal(await page.getByRole('dialog').count(), 0);
		await result.evaluate(n=>n.style.transform='translateY(300vh)');
		await canvas.waitFor({state:'detached'});
		await result.evaluate(n=>n.style.transform='');
		await page.waitForFunction(() => document.querySelector('[data-mesh-result] canvas')?.width > 310);
		assert.equal(meshFetches,1,'Returning to a recent model should not fetch its GLB again');
		const format = result.getByRole('button', { name: /Formato|File format/ });
		const height = result.getByRole('spinbutton');
		assert.equal(await height.inputValue(), '100');
		assert.equal(await height.evaluate(node => getComputedStyle(node.parentElement).borderTopStyle), 'solid');
		await height.fill('10000');
		assert(!(await result.getByRole('button', { name: /^(Baixar|Download)$/ }).isDisabled()));
		assert(await height.evaluate(n => n.scrollWidth <= n.clientWidth + 1));
		await height.fill('10001');
		assert.equal(await height.inputValue(), '10000');
		await height.press('End');
		await height.press('9');
		assert.equal(await height.inputValue(), '10000');
		await height.fill('4');
		assert(await result.getByRole('button', { name: /^(Baixar|Download)$/ }).isDisabled());
		await height.fill('165');
		const flat = result.getByRole('button', { name: /^(stable base|base est.vel):/i });
		assert.match(await flat.innerText(), /original/i);
		await flat.click();
		await page.getByRole('menuitemradio', {name:/^stable base$|^base est.vel$/i}).click();
		await format.click();
		assert.equal(await page.getByRole('menuitemradio').count(), 6);
		assert.equal(await page.getByRole('menuitemradio', { name: 'BLEND', exact: true }).count(), 1);
		assert.equal(await page.getByRole('menuitemradio', { name: 'OBJ', exact: true }).count(), 1);
		await page.getByRole('menuitemradio', { name: 'STL', exact: true }).click();
		const exportRequest = page.waitForRequest(r => r.url().includes('/export/stl?height_mm=165'));
		let releaseExport;
		const barrier = new Promise(resolve => releaseExport = resolve);
		await page.route('**/export/stl?*', async route => { await barrier; await route.fulfill({ body:'fixture', contentType:'model/stl', headers:{'X-Neve-Print-Wall':'thin'} }); });
		const download = page.waitForEvent('download');
		await result.getByRole('button', { name: /^(Baixar|Download)$/ }).click();
		assert.equal(new URL((await exportRequest).url()).searchParams.get('flat_base'), 'true');
		assert(await result.locator('button[aria-busy=true] .orbiting-spheres').isVisible());
		releaseExport();
		assert.equal((await download).suggestedFilename(), 'Model.stl');
		assert.equal(await result.getByRole('status').count(), 0);
		await page.evaluate(() => {
			window.__NEVE_WEBVIEW2__ = true;
			window.__NEVE_NATIVE_DOWNLOADS__ = true;
			window.showSaveFilePicker = () => { throw new Error('unexpected file system picker'); };
		});
		const native = page.waitForEvent('download');
		await result.getByRole('button', { name: /^(Baixar|Download)$/ }).click();
		assert.equal((await native).suggestedFilename(), 'Model.stl');
		assert.equal(await page.getByText(/^(Arquivo salvo|File saved)$/).count(), 0);
		await page.evaluate(() => {delete window.__NEVE_WEBVIEW2__; delete window.__NEVE_NATIVE_DOWNLOADS__; delete window.showSaveFilePicker;});
		await format.click();
		await page.getByRole('menuitemradio', { name: 'GLB', exact: true }).click();
		assert.equal(await height.count(), 0);
		assert.equal(await flat.count(), 0);

		await page.goto(base + '/c/media-test', { waitUntil: 'networkidle' });
		await page.getByRole('button', { name: /visualização da imagem|show image preview/i }).click();
		await checkFullscreenToolbar(page, page.locator('.file-preview-immersive.modal'));
		await page.locator('.video-player').hover();
		await page.getByRole('button', { name: 'Expandir', exact: true }).click();
		await checkFullscreenToolbar(page, page.locator('.video-preview-surface.expanded'));

		await page.goto(base + '/library', { waitUntil: 'networkidle' });
		for (const file of library) {
			let release;
			if (['pdf-test', 'pptx-test'].includes(file.id)) {
				const barrier = new Promise(resolve => { release = resolve; });
				await page.route('**/files/' + file.id + '/content*', async r => {
					await barrier;
					await r.fulfill({ body: documents[file.id], contentType: file.meta.content_type });
				});
			}
			await page.getByRole('button', { name: file.filename, exact: true }).click();
			if (release) {
				const zoom = page.getByRole('dialog').getByRole('button', { name: /Zoom in|Aumentar zoom/i });
				await zoom.click();
				await page.getByRole('dialog').getByText('125%', { exact: true }).waitFor();
				release();
			}
			const dialog = page.getByRole('dialog');
			await dialog.locator('.file-preview-title').filter({ hasText: file.filename }).waitFor();
			const filename = dialog.locator('[data-file-preview-name]');
			assert.equal(await filename.getAttribute('title'), null);
			if (file.meta.size) {
				const name = await filename.boundingBox();
				const size = await dialog.locator('.file-viewer-size').boundingBox();
				assert(Math.abs(name.x - size.x) < 1 && Math.abs(size.y - (name.y + name.height)) <= 4);
			}
			if (file.id === 'mesh-test') {
				await dialog.locator('canvas').waitFor();
				const chooser = dialog.getByRole('button', { name: /Formato|File format/ });
				await chooser.click();
				await dialog.getByRole('menuitemradio', { name: 'FBX', exact: true }).click();
				assert.match(await chooser.innerText(), /FBX/);
			}
			if (file.id === 'image-test') {
				const image = dialog.locator('.file-image-viewport img');
				await image.waitFor();
				const before = await image.boundingBox();
				const x = before.x + before.width / 2, y = before.y + before.height / 2;
				await page.mouse.move(x, y);
				await page.mouse.down();
				await page.mouse.move(x + 20, y + 15, { steps: 4 });
				await page.mouse.up();
				const atFit = await image.boundingBox();
				assert(Math.abs(atFit.x - before.x) < 1 && Math.abs(atFit.y - before.y) < 1, 'Fitted image must not jump on drag');
				await page.mouse.wheel(0, -240);
				await page.waitForFunction(w => document.querySelector('.file-image-target').getBoundingClientRect().width > w, before.width);
				const after = await image.boundingBox();
				assert(Math.abs(after.x + after.width / 2 - x) < 3 && Math.abs(after.y + after.height / 2 - y) < 3, 'Zoom must stay centered at pointer');
			}
			if (file.id === 'pdf-test') {
				const canvas = dialog.locator('canvas[data-page="1"][data-rendered=true]');
				await canvas.waitFor();
				const initial = await canvas.evaluate(n => n.width);
				const zoom = dialog.getByRole('button', { name: 'Zoom in', exact: true });
				for (let i = 0; i < 3; i++) await zoom.click();
				await page.waitForFunction(w => document.querySelector('canvas[data-rendered=true]').width > w, initial);
				const enlarged = await canvas.evaluate(n => n.width);
				await dialog.getByRole('button', { name: 'Reset zoom' }).click();
				await page.waitForTimeout(150);
				assert.equal(await canvas.evaluate(n => n.width), enlarged, 'Reset must not discard sharper raster');
				for (let i=2;i<=32;i+=2) {
					const current=dialog.locator('canvas[data-page="'+i+'"]');
					await current.evaluate(node=>node.scrollIntoView({block:'center'}));
					await page.waitForFunction(i=>document.querySelector('canvas[data-page="'+i+'"]')?.dataset.rendered==='true',i);
				}
				assert.equal(await canvas.count(),0,'Old pages must release raster memory');
				await dialog.locator('canvas[data-page="1"]').evaluate(node=>node.scrollIntoView({block:'start'}));
				await canvas.waitFor();
			}
			if (file.id === 'xlsx-test') {
				await dialog.getByRole('tab', { name: 'Second', exact: true }).click();
				await dialog.getByText('Second tab content', { exact: true }).waitFor();
			}
			if (file.id === 'pptx-test') {
				const nav = dialog.locator('.slide-navigation');
				await nav.getByText('1 / 2').waitFor();
				await dialog.getByRole('button', { name: /Zoom in|Aumentar zoom/i }).click();
				await dialog.getByText('156%', { exact: true }).waitFor();
				for (let i = 0; i < 5; i++) await dialog.getByRole('button', { name: /Zoom in|Aumentar zoom/i }).click();
				await page.waitForFunction(() => document.querySelector('.presentation-preview img')?.naturalWidth > 960);
				const ink = await dialog.locator('.presentation-preview img').evaluate(img => {
					const canvas = document.createElement('canvas');
					canvas.width = 480; canvas.height = 270;
					const ctx = canvas.getContext('2d');
					ctx.drawImage(img, 0, 0, 480, 270);
					return ctx.getImageData(0, 0, 480, 270).data.some((v, i) => i % 4 === 0 && v < 80);
				});
				assert(ink, 'Text must remain present on the sharper slide');
				await nav.getByRole('button').last().click();
				await nav.getByText('2 / 2').waitFor();
			}
			if (file.id === 'text-test') {
				const surface = dialog.locator('.file-preview-surface');
				await surface.getByText(/Preview text, line 200/).waitFor();
				assert(await surface.evaluate(node => {
					node.scrollTop = node.scrollHeight;
					return node.scrollTop > 0 && getComputedStyle(node).borderRadius !== '0px';
				}));
			}
			if (width === 1440 || file.id === 'mesh-test') {
				const close = dialog.locator('button:is([data-window-close],[data-mobile-modal-close])');
				assert.deepEqual(await close.evaluate(node => {
					const button = getComputedStyle(node);
					const rem = parseFloat(getComputedStyle(document.documentElement).fontSize);
					return [button.width, button.height, button.borderRadius, getComputedStyle(node.querySelector('svg')).width]
						.map(value => Math.round(parseFloat(value) / rem * 16));
				}), [32, 32, 6, 16]);
				await close.click();
			} else await page.keyboard.press('Escape');
			await dialog.waitFor({ state: 'hidden' });
		}
		await page.goto(base, { waitUntil: 'networkidle' });
		await page.locator('#input-menu-button').click();
		const menu = await page.getByRole('button', { pressed: false }).allTextContents();
		const modeling = menu.findIndex(text => /Criar modelo|Create model/.test(text));
		const image = menu.findIndex(text => /Criar imagem|Create image/i.test(text));
		assert(modeling >= 0 && image === modeling + 1, 'Modeling must immediately precede image creation');
		await page.getByRole('button', { name: /Criar modelo|Create model/ }).click();
		await page.locator('[data-model3d-integration]').waitFor();
		await page.route('**/files/mesh-test/content*',r=>r.fulfill({body:rigFixture(),contentType:'model/gltf+json'}));
		await page.goto(base+'/c/mesh-test',{waitUntil:'networkidle'});
		await view.scrollIntoViewIfNeeded();
		await view.click();
		await page.getByRole('menuitemradio',{name:/Solid surface|Sólido/}).click();
		await page.mouse.move(0,0);
		const noBones = await centerPixels();
		await view.click();
		await page.getByRole('menuitemradio',{name:/Skeleton|Esqueleto/}).click();
		await page.mouse.move(0,0);
		assert(!(await centerPixels()).equals(noBones), 'real skeleton changes the canvas, not only the control');
		assert.deepEqual(errors, []);
		console.log('PASS', width, 'inline 3D pixels, orbit, viewers and menu', colors);
		await page.close();
	}
} finally {
	await browser.close();
}
