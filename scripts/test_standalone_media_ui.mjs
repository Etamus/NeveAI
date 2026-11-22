// Production composer with an empty model catalog; intercept generation before using the GPU.
import assert from 'node:assert/strict';
import {chromium} from '../logs/ui-image-26/node_modules/playwright/index.mjs';
const browser=await chromium.launch({executablePath:process.env.NEVE_TEST_BROWSER});
try {
	for(const [feature,label] of [
		['stable_diffusion',/^(Criar imagem|Create (an? )?image)$/i],
		['video_generation',/^(Criar vídeo|Create (a )?video)$/i],
		['model3d_generation',/^(Criar modelo|Create (a )?(3D )?model)$/i],['text',null]
	]){
		const page=await browser.newPage();page.setDefaultTimeout(10000);
		await page.route(/\/api\/models(?:\?|$)/,route=>route.fulfill({json:{data:[]}}));
		let sent;
		await page.route('**/api/chat/completions',route=>{sent=route.request().postDataJSON();return route.fulfill({status:400,json:{detail:'Test complete'}})});
		await page.goto('http://localhost:8080/?temporary-chat=true',{waitUntil:'networkidle'});
		if(label){
			await page.locator('.composer-more-trigger').click();
			await page.locator('.composer-integrations-menu').getByText(label).last().click();
		}
		if(feature==='model3d_generation'){
			const pick=page.waitForEvent('filechooser');
			await page.locator('[data-image-slot="base"]').click();
			await (await pick).setFiles('static/favicon.png');
		}else await page.locator('#chat-input').fill('Teste sem modelo');
		await page.locator('#send-message-button:visible').click();
		if(label){
			for(let i=0;!sent && i<60;i++) await page.waitForTimeout(100);
			assert.equal(sent?.model,'neve-media/'+feature,await page.locator('body').innerText());
			assert.equal(sent.features[feature],true);
			assert(sent.chat_id.startsWith('local:'));
		}else{
			await page.getByText(/^(Modelo não selecionado|Model not selected)$/i).last().waitFor();
			assert.equal(sent,undefined);
		}
		console.log('PASS empty catalog:',feature);await page.close();
	}
}finally{await browser.close();}
