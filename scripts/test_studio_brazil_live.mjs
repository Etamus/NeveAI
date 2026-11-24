// Opt-in local UI test. The uploaded fixture belongs only to this Studio session.
import assert from 'node:assert/strict';
import {chromium} from '../logs/ui-image-26/node_modules/playwright/index.mjs';
const browser=await chromium.launch({executablePath:process.env.NEVE_TEST_BROWSER});
try {
    const page=await browser.newPage({viewport:{width:1440,height:900},locale:'pt-BR'});
    await page.goto(process.env.NEVE_TEST_ORIGIN || 'http://localhost:8080',{waitUntil:'networkidle'});
    await page.locator('#input-menu-button').click();
    await page.locator('.composer-integrations-menu button').filter({hasText:/Criar v.deo|Create video/i}).first().click();
    await page.getByText('Neve Video 1.5',{exact:true}).first().click();
    await page.getByRole('menuitemradio',{name:'Neve Studio'}).click();
    await page.locator('input[type=file][aria-label]').first().setInputFiles('logs/maker-tools-ui-fixture.mp4');
    await page.getByText('maker-tools-ui-fixture.mp4',{exact:true}).first().waitFor();
    await page.locator('[data-video-mode-edit]').click();
    const tool=page.locator('.edit-tool-card').filter({hasText:/Traduzir legendas|Translate captions/i});
    assert(await tool.isDisabled());
    await page.locator('.edit-caption-label button').click();
    await page.locator('.cue-field').fill('I left my cell phone on the bus.');
    await page.locator('.cue-field').press('Tab');
    await page.locator('.edit-tabs button').first().click();
    await tool.click();
    const dialog=page.locator('.translation-dialog');
    const target=dialog.getByRole('button',{name:/Traduzir para|Translate to/});
    assert.deepEqual(await dialog.locator('.edit-caption-setting > span').evaluateAll(labels=>
        labels.map(el=>getComputedStyle(el).fontSize)),['15px','15px']);
    assert.match((await target.innerText()).trim(),/^(Portugu.s|Portuguese)$/);
    assert(await target.evaluate(e=>e.scrollWidth<=e.clientWidth));
    await dialog.getByRole('button',{name:/^(Cancelar|Cancel)$/}).click();
    await tool.click();
    const pending=page.waitForResponse(r=>r.url().endsWith('/video-edit/translate'));
    await dialog.getByRole('button',{name:/^(Traduzir|Translate)$/}).click();
    const result=await (await pending).json();
    assert.match(result.texts[0],/celular.*nibus/i);
    console.log('Studio: translated in the timeline:',result.texts[0]);
    await page.goto('about:blank');
} finally {await browser.close();}
