import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {constants} from 'node:fs';
import {createServer} from 'vite';
import {installMobileOfflineApi} from './fixtures/mobile-offline-api.mjs';
import {chromium} from '../logs/ui-image-26/node_modules/playwright/index.mjs';

const directory = new URL('../src/routes/__web_query_test/', import.meta.url);
const file = new URL('+page.svelte', directory);
await fs.mkdir(directory, {recursive:true});
await fs.copyFile(new URL('./fixtures/web-query-pills.svelte', import.meta.url), file, constants.COPYFILE_EXCL);
let browser, server;
const results = [];
try {
    server = await createServer({server:{port:5188,strictPort:true,watch:{ignored:['**/logs/**']}}});
    await server.listen();
    browser = await chromium.launch();
    for (const width of [1440,390,320]) {
        const page = await browser.newPage({viewport:{width,height:900}});
        const errors = [];
        page.on('pageerror', error => errors.push(error.message));
        await installMobileOfflineApi(page);
        await page.goto('http://localhost:5188/__web_query_test',{waitUntil:'domcontentloaded',timeout:90000});
        await page.locator('#long .search-query-pill').waitFor();
        await page.evaluate(() => document.fonts.ready);
        for (const theme of ['dark','light']) {
            await page.evaluate(theme => document.documentElement.classList.toggle('dark',theme==='dark'),theme);
            const measures = await page.locator('.search-query-pill').evaluateAll(elements => elements.map(el => ({
                width:el.getBoundingClientRect().width, parent:el.parentElement.clientWidth,
                textWhiteSpace:getComputedStyle(el.querySelector('span')).whiteSpace,
                textOverflow:getComputedStyle(el.querySelector('span')).textOverflow,
                iconWidth:el.querySelector('svg').getBoundingClientRect().width,
                height:el.getBoundingClientRect().height,
                rem:parseFloat(getComputedStyle(document.documentElement).fontSize),
            })));
            for (const item of measures) {
                assert(item.width<=22*item.rem+.5 && item.width<=item.parent, JSON.stringify({width,theme,item}));
                assert.equal(item.textWhiteSpace,'nowrap');
                assert.equal(item.textOverflow,'ellipsis');
                assert(Math.abs(item.iconWidth-.75*item.rem)<.1);
                assert(item.height<40);
            }
            assert(await page.locator('#short .search-query-pill').evaluate(el => el.clientWidth<150));
            assert.equal(await page.evaluate(() => document.documentElement.scrollWidth>innerWidth),false);
            await page.screenshot({path:`logs/web-query-pills-${width}-${theme}.png`});
            results.push({width,theme,measures});
        }
        assert.deepEqual(errors,[]);
        await page.close();
    }
    await fs.writeFile('logs/web-query-pills-results.json',JSON.stringify(results,null,2));
    console.log(JSON.stringify({viewports:results.length,passed:true}));
} finally {
    await browser?.close();
    await server?.close();
    await fs.unlink(file);
    await fs.rmdir(directory);
}
