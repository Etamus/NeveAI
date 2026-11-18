import assert from 'node:assert/strict';
import {chromium} from '../logs/ui-image-26/node_modules/playwright/index.mjs';
import {installMobileOfflineApi} from './fixtures/mobile-offline-api.mjs';

const browser = await chromium.launch();
try {
	const page = await browser.newPage({viewport:{width:1440,height:900}});
	await installMobileOfflineApi(page);
	const rows = Array.from({length:60}, (_,i) => ({id:'end-'+i,title:'End test '+i,updated_at:1700000000-i,created_at:1700000000-i}));
	let release;
	const gate = new Promise(resolve => release = resolve);
	await page.route('**/api/v1/chats/?*', async route => {
		const p = Number(new URL(route.request().url()).searchParams.get('page') || 1);
		if (p > 1) await gate;
		await route.fulfill({json:p > 1 ? [] : rows});
	});
	await page.goto(process.env.NEVE_TEST_ORIGIN || 'http://localhost:8080');
	const list = page.locator('.sidebar-scroll-fade');
	await list.getByText('End test 59',{exact:true}).waitFor({state:'attached'});
	const measured = () => list.evaluate(el => [el.scrollTop,el.scrollHeight]);
	const empty = page.waitForResponse(r => /\/chats\/\?.*page=2/.test(r.url()));
	await list.evaluate(el => {el.scrollTop = el.scrollHeight;});
	const before = await measured();
	assert(before[0] > 0);
	release();
	await empty;
	await page.waitForTimeout(350);
	assert.deepEqual(await measured(),before);
	console.log('PASS: scrollTop and scrollHeight unchanged after empty last page', before);
} finally { await browser.close(); }
