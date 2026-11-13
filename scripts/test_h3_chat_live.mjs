import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import { chromium } from '../logs/ui-image-26/node_modules/playwright/index.mjs';

const base = 'http://127.0.0.1:8080';
const editing = process.argv.includes('--edit');
const name = editing ? 'edit' : 'generate';
const prompt = editing
	? 'Mantenha a caneca azul da imagem 1 e coloque a colher azul da imagem 2 na mesa ao lado dela. Preserve o restante.'
	: 'Uma caneca vermelha sobre uma mesa branca, com uma colher azul ao lado. Fotografia.';
let browser, page;
const ownTasks = new Set();
const errors = [];
try {
	assert.deepEqual((await (await fetch(base + '/api/tasks')).json()).tasks, []);
	const before = await (await fetch(base + '/api/v1/files/generated?kind=image&limit=100')).json();
	const previousIds = new Set(before.map(item => item.id));
	browser = await chromium.launch();
	page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
	page.on('pageerror', error => errors.push(error.message));
	// This validation must not create or modify a saved conversation.
	await page.route('**/api/v1/chats/**', route => route.request().method() === 'GET' ? route.continue() : route.abort());
	await page.route('**/api/chat/completions', async route => {
		const request = route.request().postDataJSON();
		assert(request.chat_id.startsWith('local:'), 'Use a temporary conversation');
		assert.equal(request.features.stable_diffusion_quality, 'minimax_h3_image');
		await route.continue();
	});
	page.on('response', async response => {
		if (response.url().endsWith('/api/chat/completions')) {
			try { const value = await response.json(); if (value.task_id) ownTasks.add(value.task_id); } catch {}
		}
	});
	await page.goto(base, { waitUntil: 'networkidle', timeout: 90000 });
	await page.locator('#chat-input').waitFor({ timeout: 30000 });
	const temporary = page.locator('#temporary-chat-button');
	// Toggling is verified by its URL before any completion is allowed.
	await temporary.click();
	if (!page.url().includes('temporary-chat=true')) await temporary.click();
	assert(page.url().includes('temporary-chat=true'));
	await page.locator('.composer-more-trigger').click();
	await page.getByRole('button', { name: /Criar imagem|Create image/ }).click();
	await page.locator('#image-quality-dropdown-container > button').click();
	await page.getByRole('button', { name: /Neve Image 3/ }).click();
	if (editing) {
		await page.locator('[data-composer-root] input[type=file]').first().setInputFiles(['logs/h3-images/h3-edit-pt.png', 'logs/h3-images/h3-generate-pt.png']);
		await page.waitForFunction(() => [...document.querySelectorAll('.composer-image-thumbnail img, img.composer-image-thumbnail')].filter(image => image.complete && image.naturalWidth > 0).length === 2);
	}
	await page.locator('#chat-input').fill(prompt);
	await page.screenshot({ path: `logs/h3-live-${name}-before.png` });
	const started = Date.now();
	await page.locator('#send-message-button').click();
	const image = page.locator('#messages-container img[src*="/api/v1/files/"]');
	await image.first().waitFor({ state: 'visible', timeout: 300000 });
	await page.waitForFunction(() => [...document.querySelectorAll('#messages-container img')].some(image => image.complete && image.naturalWidth === 2048), null, { timeout: 30000 });
	const after = await (await fetch(base + '/api/v1/files/generated?kind=image&limit=100')).json();
	const created = after.filter(item => !previousIds.has(item.id) && item.meta?.data?.source === 'neve-image-3' && item.meta?.data?.prompt === prompt);
	assert.equal(created.length, 1, 'Exactly one generated image must be in the Library');
	const file = created[0];
	const content = await fetch(base + `/api/v1/files/${file.id}/content`);
	assert.equal(content.status, 200);
	const thumbnail = await fetch(base + `/api/v1/files/${file.id}/thumbnail`);
	assert.equal(thumbnail.status, 200);
	await fs.writeFile(`logs/h3-images/live-chat-${name}.png`, Buffer.from(await content.arrayBuffer()));
	await page.screenshot({ path: `logs/h3-live-${name}-after.png` });
	assert.deepEqual(errors, []);
	const result = { name, references: editing ? 2 : 0, seconds: (Date.now() - started) / 1000, library_registered: true, file_id: file.id, content_status: content.status, thumbnail_status: thumbnail.status, temporary_chat: true, javascript_errors: errors };
	await fs.writeFile(`logs/h3-live-${name}-result.json`, JSON.stringify(result, null, 2));
	// Delete only the exact synthetic sample proven to have been created by this test.
	assert.equal((await fetch(base + `/api/v1/files/${file.id}`, { method: 'DELETE' })).status, 200);
	console.log('PASS', result);
} catch (error) {
	await page?.screenshot({ path: 'logs/h3-live-failed.png' });
	console.error('UI:', await page?.locator('body').innerText());
	throw error;
} finally {
	const active = (await (await fetch(base + '/api/tasks')).json()).tasks;
	for (const id of ownTasks) if (active.includes(id)) await fetch(base + '/api/tasks/stop/' + id, { method: 'POST' });
	await browser?.close();
}
