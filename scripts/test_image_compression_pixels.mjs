import fs from 'node:fs/promises';
import { chromium } from '../logs/ui-image-26/node_modules/playwright/index.mjs';
const browser = await chromium.launch({ executablePath: 'C:/Program Files/BraveSoftware/Brave-Browser/Application/brave.exe' });
try {
	const page = await browser.newPage();
	const photo = await fs.readFile('logs/paste-performance/large.jpg');
	await page.route('http://localhost/**', route => route.fulfill(route.request().url().endsWith('/photo') ? { body: photo, contentType: 'image/jpeg' } : { body: '<html></html>', contentType: 'text/html' }));
	await page.goto('http://localhost/');
	console.log(await page.evaluate(async () => {
		const blob = await (await fetch('/photo')).blob();
		const bitmap = await createImageBitmap(blob);
		const image = new Image(); image.src = URL.createObjectURL(blob); await image.decode();
		const results = [];
		const variants = [['image', image, false], ['bitmap', bitmap, false], ['offscreen', bitmap, true], ['offscreen-image', image, true]];
		for (const resizeQuality of ['pixelated', 'low', 'medium', 'high']) variants.push(['resize-'+resizeQuality, await createImageBitmap(blob, {resizeWidth:1024,resizeHeight:576,resizeQuality}), true]);
		for (const premultiplyAlpha of ['none', 'premultiply']) variants.push(['alpha-'+premultiplyAlpha, await createImageBitmap(blob, {premultiplyAlpha}), true]);
		for (const [name, source, offscreen] of variants) {
			const canvas = offscreen ? new OffscreenCanvas(1024, 576) : document.createElement('canvas');
			canvas.width = 1024; canvas.height = 576;
			canvas.getContext('2d').drawImage(source, 0, 0, 1024, 576);
			for (const quality of [undefined, 0.92]) {
				const encoded = offscreen ? await canvas.convertToBlob({ type: 'image/jpeg', quality }) : await (await fetch(canvas.toDataURL('image/jpeg', quality))).blob();
				const decoded = await createImageBitmap(encoded);
				const target = document.createElement('canvas'); target.width = 1024; target.height = 576;
				target.getContext('2d').drawImage(decoded, 0, 0);
				const pixels = target.getContext('2d').getImageData(0, 0, 1024, 576).data;
				const baseline = results[0]?.pixels ?? pixels;
				let error = 0, max = 0;
				for (let i = 0; i < pixels.length; i++) { const delta = Math.abs(pixels[i] - baseline[i]); error += delta; max = Math.max(max, delta); }
				results.push({ name, quality, bytes: encoded.size, pixels, mean: error / pixels.length, max });
				decoded.close();
			}
		}
		bitmap.close(); URL.revokeObjectURL(image.src);
		return results.map(({ pixels, ...result }) => result);
	}));
} finally { await browser.close(); }
