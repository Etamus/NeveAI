import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { chromium } from '../logs/ui-image-26/node_modules/playwright/index.mjs';

const origin = process.env.NEVE_TEST_ORIGIN || 'http://localhost:8080';
const browser = await chromium.launch({ executablePath: process.env.NEVE_TEST_BROWSER, args: [
	'--use-fake-ui-for-media-stream',
	'--use-fake-device-for-media-stream',
	'--use-file-for-fake-audio-capture=' + resolve('logs/haru-question-0.wav')
] });
try {
	for (const width of [1440, 390, 320]) {
		const locale = width === 320 ? 'en-US' : 'pt-BR';
		const page = await browser.newPage({ viewport: { width, height: 860 }, permissions: ['microphone'] });
		await page.addInitScript(({ theme, locale }) => {
			localStorage.setItem('theme', theme);
			localStorage.setItem('neveai.language', locale);
			const capture = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
			window.dictationTracks = [];
			window.denyDictation = '';
			navigator.mediaDevices.getUserMedia = async options => {
				if (window.denyDictation) throw new DOMException('Microphone unavailable', window.denyDictation);
				await new Promise(resolve => { window.allowDictation = resolve; });
				const stream = await capture(options);
				window.dictationTracks.push(...stream.getTracks());
				return stream;
			};
		}, { theme: width === 390 ? 'light' : 'dark', locale });
		const errors = [];
		page.on('pageerror', error => errors.push(error.message));
		let requests = 0;
		await page.route('**/api/v1/audio/dictation', async route => {
			requests++;
			const form = route.request().postDataBuffer();
			assert(form.length > 1000);
			assert(form.includes('filename="dictation.webm"'));
			await route.fulfill({ json: { text: 'Transcribed <tag> *literally*.' } });
		});
		await page.goto(origin, { waitUntil: 'domcontentloaded' });
		const input = page.locator('#chat-input');
		const dictate = page.getByRole('button', { name: /^(Dictate|Ditar)$/ });
		const panel = page.locator('[data-composer-dictation]');
		const confirm = panel.getByRole('button', { name: /^(Confirm|Confirmar)$/ });
		const cancel = panel.getByRole('button', { name: /^(Cancel|Cancelar)$/ });
		const composer = page.locator('#message-input-container');
		await dictate.waitFor();
		assert(await composer.evaluate(el => el.classList.contains('flex-row')));
		const dictateRect = await dictate.boundingBox();
		const sendRect = await composer.locator('#send-message-button').boundingBox();
		assert.equal((await dictate.locator('svg').boundingBox()).width, 20);
		assert(dictateRect.x + dictateRect.width <= sendRect.x);
		assert(Math.abs(dictateRect.y + dictateRect.height / 2 - sendRect.y - sendRect.height / 2) < 1);
		const checkTracks = () => page.waitForFunction(() =>
			window.dictationTracks.length && window.dictationTracks.every(track => track.readyState === 'ended')
		);
		async function record() {
			const compact = await composer.evaluate(el => el.classList.contains('flex-row'));
			const before = await composer.boundingBox();
			const primary = await composer.locator('#send-message-button').boundingBox();
			await dictate.click();
			await page.waitForFunction(() => typeof window.allowDictation === 'function');
			assert.equal(await panel.count(), 0);
			assert.equal(await composer.evaluate(el => el.inert), false);
			assert.deepEqual(await composer.boundingBox(), before);
			const status = panel.getByRole('status');
			await page.evaluate(() => {
				window.allowDictation();
				delete window.allowDictation;
			});
			await confirm.and(page.locator('button:enabled')).waitFor();
			assert.equal((await status.textContent()).trim(), locale === 'pt-BR' ? 'Ouvindo...' : 'Listening...');
			await page.waitForFunction(() => window.dictationTracks.some(track => track.readyState === 'live'));
			await panel.locator('canvas').waitFor();
			const rect = await composer.boundingBox();
			assert(Math.abs(rect.height - (compact ? before.height : 98)) <= 1);
			assert(await composer.evaluate(el => el.inert));
			const actions = await Promise.all([cancel.boundingBox(), confirm.boundingBox()]);
			assert(actions.every(button => button.x >= rect.x && button.x + button.width <= rect.x + rect.width));
			assert(Math.abs(actions[0].y - actions[1].y) < 1);
			for (const key of (compact ? ['x', 'y', 'width', 'height'] : ['x', 'width', 'height'])) {
				assert(Math.abs(actions[1][key] - primary[key]) < 0.5, `Confirm differs on ${key}: ${JSON.stringify({ primary, confirm: actions[1] })}`);
			}
		}
		await record();
		await cancel.click();
		await panel.waitFor({ state: 'detached' });
		await checkTracks();
		assert.equal(requests, 0);
		assert.equal((await input.innerText()).trim(), '');

		await record();
		await page.waitForTimeout(600);
		assert(await panel.locator('canvas').evaluate(canvas =>
			canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height).data.some(Boolean)
		));
		await page.screenshot({ path: `logs/composer-dictation-compact-${width}.png` });
		await confirm.click();
		await panel.waitFor({ state: 'detached' });
		await checkTracks();
		assert.equal((await input.innerText()).trim(), 'Transcribed <tag> *literally*.');

		await input.fill('First line\nSecond line');
		await page.waitForFunction(() => document.querySelector('#message-input-container').classList.contains('flex-col'));
		await record();
		await page.waitForTimeout(600);
		await page.screenshot({ path: `logs/composer-dictation-expanded-${width}.png` });
		await confirm.click();
		await panel.waitFor({ state: 'detached' });
		await checkTracks();
		assert.match(await input.innerText(), /First line\s+Second line Transcribed <tag> \*literally\*\./);
		assert.equal(requests, 2);
		if (width === 1440) {
			const preview = await readFile(resolve('static/favicon.png'));
			await page.route('**/api/v1/files/**', async route => {
				if (route.request().method() === 'POST') {
					await route.fulfill({ json: { id: 'dictation-layout-fixture', filename: 'fixture.png', meta: { name: 'fixture.png', content_type: 'image/png' }, data: { status: 'completed' } } });
				} else await route.fulfill({ contentType: 'image/png', body: preview });
			});
			await page.locator('.composer-more-trigger').click();
			await page.getByText('Criar imagem', { exact: true }).last().click();
			await page.locator('#image-mode-dropdown-container button').click();
			await page.locator('[data-image-mode="inpaint"]').click();
			const slot = composer.locator('[data-image-slot="base"]');
			await slot.waitFor();
			await composer.locator('.image-swap-slots').locator('..').locator('input[accept="image/*"]').first().setInputFiles(resolve('static/favicon.png'));
			await composer.locator('[data-image-mode-edit]').waitFor();
			assert((await composer.boundingBox()).height > 125);
			await record();
			assert.equal(await slot.isVisible(), false);
			assert.equal(await input.isVisible(), false);
			await page.screenshot({ path: 'logs/composer-dictation-attachment-1440.png' });
			await cancel.click();
			await panel.waitFor({ state: 'detached' });
			await checkTracks();
			await slot.waitFor();
			await composer.locator('#image-mode-dropdown-container button').click();
			await page.locator('[data-image-mode="outpaint"]').click();
			await page.waitForFunction(() => document.querySelector('#chat-input')?.getClientRects().length === 0);
			assert.equal(await dictate.count(), 0);
			await composer.locator('#image-mode-dropdown-container button').click();
			await page.locator('#image-mode-dropdown [role="menuitemradio"]').first().click();
			await input.waitFor();
		}
		const draft = await input.innerText();
		await page.evaluate(() => {
			window.dictationWasMounted = false;
			new MutationObserver(records => {
				if (records.some(record => [...record.addedNodes].some(node =>
					node instanceof Element && (node.matches('[data-composer-dictation]') || node.querySelector('[data-composer-dictation]'))
				))) window.dictationWasMounted = true;
			}).observe(document.body, { subtree: true, childList: true });
		});
		for (const error of ['NotFoundError', 'NotAllowedError']) {
			await page.evaluate(error => { window.denyDictation = error; }, error);
			await dictate.click();
			await page.getByText(/Microphone access was not available|Não foi possível acessar o microfone/).first().waitFor();
			assert.equal(await page.evaluate(() => window.dictationWasMounted), false);
			assert.equal(await input.innerText(), draft);
		}
		assert.deepEqual(errors, []);
		if (process.env.NEVE_DICTATION_LIVE && width === 1440) {
			await page.unroute('**/api/v1/audio/dictation');
			await page.evaluate(() => { window.denyDictation = ''; });
			await input.fill('');
			await record();
			await page.waitForTimeout(4800);
			const reply = page.waitForResponse(r => r.url().endsWith('/api/v1/audio/dictation'));
			await confirm.click();
			assert.equal((await reply).status(), 200);
			await panel.waitFor({ state: 'detached' });
			await checkTracks();
			assert.match(await input.innerText(), /seu nome/i);
			console.log('PASS: browser recording transcribed by the running backend');
		}
		console.log(`PASS: dictation at ${width}px`);
		await page.close();
	}
} finally {
	await browser.close();
}
