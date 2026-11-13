import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import { chromium } from '../logs/ui-image-26/node_modules/playwright/index.mjs';
import { installMobileOfflineApi } from './fixtures/mobile-offline-api.mjs';

const base = process.env.ARTIFACT_BASE ?? 'http://127.0.0.1:8080';
const content = '```tsx App.tsx\nimport React,{useState} from "react";import {Label} from "./Label";import styles from "./style.module.css";export default function App(){const [count,setCount]=useState(0);return <main className={styles.page}><Label/><button id="built-count" onClick={()=>setCount(count+1)}>Count {count}</button></main>}\n```\n```tsx Label.tsx\nexport function Label(){return <h1>Production TSX</h1>}\n```\n```css style.module.css\n.page h1{color:rgb(12,110,80)}\n```';
const results = [];
const browser = await chromium.launch();
try {
	for (const width of [1440, 390]) {
		const page = await browser.newPage({ viewport: { width, height: 900 } });
		const errors = []; page.on('pageerror', error => errors.push(error.message));
		await installMobileOfflineApi(page);
		await page.route('**/api/config', route => route.fulfill({ json: {
			name: 'Neve AI', version: '3.0.20', default_models: 'local/mobile-fixture',
			features: { auth: false, enable_websocket: false, enable_stable_diffusion: true, enable_code_execution: true },
			file: { max_file_count: 10 }
		} }));
		const history = { currentId: 'production-reply', messages: {
			'production-user': { id: 'production-user', role: 'user', content: 'Create a page', parentId: null, childrenIds: ['production-reply'], timestamp: 1700000000 },
			'production-reply': { id: 'production-reply', role: 'assistant', content, done: true, parentId: 'production-user', childrenIds: [], model: 'local/mobile-fixture', timestamp: 1700000001 }
		} };
		await page.route('**/api/v1/chats/built-artifact', route => route.fulfill({ json: { id: 'built-artifact', title: 'Production test', user_id: 'mobile-fixture-user', chat: { history, models: ['local/mobile-fixture'], title: 'Production test' } } }));
		await page.route('**/api/tasks/**', route => route.fulfill({ json: { task_ids: [] } }));
		const workerRequests = [];
		page.on('request', request => { if (/esbuild.*wasm|artifact-compiler.*\.js/.test(request.url())) workerRequests.push(request.url()); });
		await page.goto(base + '/c/built-artifact', { waitUntil: 'networkidle', timeout: 90000 });
		const preview = page.getByRole('button', { name: /Pré-visualização|Artifact preview/ }).first();
		await preview.waitFor({ timeout: 30000 });
		assert.equal(await page.locator('[data-artifact-preview]').count(), 0);
		assert.equal(workerRequests.length, 0, 'Compiler must not load before an explicit preview');
		await preview.click();
		const frame = page.frameLocator('[data-artifact-preview] iframe');
		await frame.locator('#built-count').waitFor({ timeout: 45000 });
		await frame.locator('#built-count').click();
		assert.equal(await frame.locator('#built-count').innerText(), 'Count 1');
		assert.equal(await frame.locator('h1').innerText(), 'Production TSX');
		assert.equal(await frame.locator('h1').evaluate(node => getComputedStyle(node).color), 'rgb(12, 110, 80)');
		await page.screenshot({ path: `logs/artifacts-built-${width}.png` });
		assert.deepEqual(errors, []);
		results.push({ width, production_preview: true, multi_file_tsx: true, errors, compiler_requests: workerRequests.length });
		await page.goto(base, { waitUntil: 'networkidle', timeout: 90000 });
		await page.locator('.composer-more-trigger').click();
		await page.getByRole('button', { name: /Criar imagem|Create image/ }).click();
		await page.locator('#image-quality-dropdown-container > button').click();
		const image3 = page.getByRole('button', { name: 'Neve Image 3', exact: true });
		assert.equal((await image3.innerText()).trim(), 'Neve Image 3', 'The model option must have no extra subtitle');
		await page.close();
	}
	await fs.writeFile('logs/artifacts-built-results.json', JSON.stringify(results, null, 2));
	console.log('PASS', results);
} finally { await browser.close(); }
