import assert from 'node:assert/strict';
import { mkdir } from 'node:fs/promises';
import { createServer } from 'node:http';
import sirv from 'sirv';
import { chromium } from '../logs/ui-image-26/node_modules/playwright/index.mjs';
import { installMobileOfflineApi } from './fixtures/mobile-offline-api.mjs';

const out = process.env.NEVE_SCROLL_OUT ?? 'logs/model-catalog-wheel';
await mkdir(out, { recursive: true });
const browser = await chromium.launch({ executablePath: process.env.NEVE_TEST_BROWSER });
const server = createServer(sirv(process.env.NEVE_BUILD_DIR ?? 'backend/neveai/frontend', { single: true }));
const issues = [];
try {
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  for (const scale of [1, 1.25]) {
    const p = await browser.newPage({ locale: 'pt-BR', viewport: { width: 1280, height: 800 }, deviceScaleFactor: scale });
    p.setDefaultTimeout(6000);
    await installMobileOfflineApi(p);
    await p.addInitScript(() => { localStorage.setItem('token','fixture'); localStorage.setItem('theme','dark'); });
    const items = Array.from({length: 40}, (_, i) => 'Model-' + String(i + 1).padStart(2, '0'));
    const local = items.map((name,i) => ({ id: 'local/'+name, filename: name+'.gguf', file_size: (1+i)*1e9, file_size_human: (1+i)+' GB', is_loaded: false }));
    await p.route(url => url.pathname === '/api/models', r => r.fulfill({json:{data:items.map(name => ({id:'local/'+name,name,owned_by:'llamacpp',info:{meta:{}}}))}}));
    await p.route('**/api/v1/models/model/profile/image?**', r => r.fulfill({path:'static/static/logo.png',contentType:'image/png'}));
    await p.route('**/llamacpp/models', r => r.fulfill({json:{models:local}}));
    await p.route('**/llamacpp/catalog', r => r.fulfill({json:{models:items.slice(0, 12).map(name => ({id:name,repo:'NeveAI/'+name,name}))}}));
    await p.route('**/llamacpp/huggingface/search?**', r => r.fulfill({json:{models:items.map(name=>({id:'Team/'+name})),next_cursor:null}}));
    await p.route('**/llamacpp/huggingface/files?**', r => r.fulfill({json:{models:items.map(name=>({path:name+'.gguf',size:1e9})),encoders:[]}}));
    await p.goto('http://127.0.0.1:'+server.address().port);
    await p.locator('[id^="model-selector-"][id$="-button"]').first().click();
    const menu = p.locator('[data-model-selector-content]');
    const options = menu.getByRole('listbox');
    await options.getByRole('option').last().waitFor({state:'attached'});
    await options.hover();
    const pitch = await options.evaluate(el => el.children[1].offsetTop - el.children[0].offsetTop);
    for (const [delta,index] of [[120,1],[120,2],[-120,1]]) {
      await p.mouse.wheel(0,delta);
      await p.waitForFunction(({index,pitch}) => {
        const el=document.querySelector('[data-model-selector-content] [role=listbox]');
        return el && Math.abs(el.scrollTop-index*pitch)<1;
      }, {index,pitch});
    }
    await options.evaluate(el=>el.scrollTop=el.scrollHeight);
    const edges = await options.evaluate(el=>{
      const view=el.getBoundingClientRect();
      const shown=[...el.children].map(row=>row.getBoundingClientRect()).filter(b=>b.bottom>view.top+1 && b.top<view.bottom-1);
      return [shown.length,shown[0].top-view.top,shown.at(-1).bottom-view.bottom];
    });
    assert.equal(edges[0],4); assert.ok(edges.slice(1).every(offset=>Math.abs(offset)<=1));
    const search = menu.locator('#model-search-input');
    await search.fill('Model-1');
    await p.waitForFunction(()=>document.querySelectorAll('[data-model-selector-row]').length===10);
    for(let i=0;i<5;i++) await search.press('ArrowDown');
    const visible = await options.evaluate(el=>{
      const v=el.getBoundingClientRect(), r=el.querySelector('[data-arrow-selected=true]').getBoundingClientRect();
      return r.top>=v.top-1 && r.bottom<=v.bottom+1;
    });
    assert.ok(visible,'keyboard-selected model is fully visible');
    await search.press('Escape');
    await p.getByRole('button',{name:/^Modelos$/}).first().click();

    async function check(name, scroller, cards, selector, header, steps) {
      const list = p.locator(scroller), first = p.locator(cards).first();
      await first.waitFor();
      await p.evaluate(()=>document.fonts.ready);
      const box = await list.boundingBox();
      await p.mouse.move(box.x+box.width-30,box.y+box.height/2);
      const samples = [], shots = [];
      const assertWholeRows = async () => {
        if (name !== 'list' && name !== 'unified') return;
        const clipped = await list.evaluate(el => {
          const viewport = el.getBoundingClientRect();
          return [...el.querySelectorAll('.unified-model-card')].filter(card => {
            const b = card.getBoundingClientRect();
            return b.bottom > viewport.top + 1 && b.top < viewport.bottom - 1 &&
              (b.top < viewport.top - 1 || b.bottom > viewport.bottom + 1);
          }).map(card => card.innerText);
        });
        assert.deepEqual(clipped, [], name + ': partial card in viewport');
      };
      for(let step=0; step<=steps; step++) {
        if (step) {
          const before = await list.evaluate(el=>el.scrollTop);
          await p.mouse.wheel(0,120);
          await p.waitForFunction(({s,b})=>document.querySelector(s).scrollTop>b,{s:scroller,b:before});
        }
        const g = await list.evaluate((el,{cards,selector,header})=>{
          const top=el.getBoundingClientRect().top, limit=top+(header?el.querySelector('[data-catalog-section-heading]').getBoundingClientRect().height:0);
          const card=[...el.querySelectorAll(cards)].find(c=>c.getBoundingClientRect().top>=limit-1);
          const b=card.getBoundingClientRect(), icon=card.querySelector(selector)?.getBoundingClientRect();
          const label=card.querySelector('.unified-model-name,.catalog-model-name,span.truncate')?.getBoundingClientRect();
          return {kind:card.hasAttribute('data-catalog-model')?'neve':card.hasAttribute('data-hf-repo')?'hf':'row',
            y:b.top-limit, height:b.height, x:b.left-el.getBoundingClientRect().left,
            icon:icon&&[icon.x-b.x,icon.y-limit], label:label&&[label.x-b.x,label.y-limit],scroll:el.scrollTop};
        }, {cards,selector,header});
        samples.push(g);
        await assertWholeRows();
        if ([0,1,2,7].includes(step)) {
          const png=await list.screenshot({path:out+'/'+name+'-'+scale+'-'+step+'.png'});
          if(step===1 || step===2) shots.push(png.toString('base64'));
        }
      }
      // Compare the same screen slot across rows, excluding the changing model ID.
      const changed = await p.evaluate(async ({shots,scale,name})=>{
        const region=name==='catalog'?[0,52,60,60]:name==='files'?[315,18,35,40]:[225,6,140,60];
        const [x,y,w,h]=region.map(v=>Math.round(v*scale));
        const pixels=await Promise.all(shots.map(async png=>{
          const img=new Image();img.src='data:image/png;base64,'+png;await img.decode();
          const cv=document.createElement('canvas');cv.width=w;cv.height=h;
          const ctx=cv.getContext('2d');ctx.drawImage(img,-x,-y);return ctx.getImageData(0,0,w,h).data;
        }));
        return pixels[0].some((v,i)=>v!==pixels[1][i]);
      },{shots,scale,name});
      if(changed) issues.push({name,scale,pixels:'stationary icon region changed'});
      for (const kind of new Set(samples.map(x=>x.kind))) {
        const group=samples.filter(x=>x.kind===kind);
        for(const key of ['y','height','x','icon','label']) {
          const vals=group.map(x=>JSON.stringify(x[key]));
          if(new Set(vals).size>1) issues.push({name,scale,kind,key,values:[...new Set(vals)]});
        }
      }
      {
        const last = await list.evaluate(el=>el.scrollHeight-el.clientHeight);
        for (let i=0; i<60 && await list.evaluate(el=>el.scrollTop)<last-1; i++) {
          const before=await list.evaluate(el=>el.scrollTop);
          await p.mouse.wheel(0,120);
          await p.waitForFunction(({s,b})=>document.querySelector(s).scrollTop>b,{s:scroller,b:before});
        }
        assert.ok(Math.abs(await list.evaluate(el=>el.scrollTop)-last)<=1);
        const lastCard = p.locator(cards).last();
        const bounds = await lastCard.boundingBox();
        assert.ok(bounds.y+bounds.height<=box.y+box.height+1,'last card clipped');
        await assertWholeRows();
        await list.screenshot({path:out+'/'+name+'-'+scale+'-end.png'});
        for(let i=0;i<60;i++){
          const before=await list.evaluate(el=>el.scrollTop);
          if(before<1) break;
          await p.mouse.wheel(0,-120);
          await p.waitForFunction(({s,b})=>document.querySelector(s).scrollTop<b,{s:scroller,b:before});
        }
        assert.equal(await list.evaluate(el=>el.scrollTop),0);
      }
      console.log(name, scale, 'observed row offsets:', [...new Set(samples.map(x=>x.y))]);
    }
    await check('unified','.unified-model-list','[data-model-key]','.model-avatar',false,5);
    const rows = p.locator('[data-model-key]'), firstRow = rows.first();
    const columns = () => p.locator('[data-model-grid]').evaluate(el=>getComputedStyle(el).gridTemplateColumns.split(' ').length);
    const checkGutter=async () => {
      const search=p.locator('.unified-models-shell input:not([type=file])').first();
      for(const [query,overflow] of [['Model-01',false],['',true]]) {
        await search.fill(query);
        await p.waitForFunction(expected=>{
          const list=document.querySelector('.unified-model-list');
          const grid=list?.querySelector('[data-model-grid]');
          if(!grid || (list.scrollHeight>list.clientHeight)!==expected) return false;
          const gap=list.getBoundingClientRect().right-grid.getBoundingClientRect().right;
          return expected?gap>1:Math.abs(gap)<1;
        },overflow);
      }
    };
    assert.equal(await columns(),2);
    assert.equal(await p.evaluate(()=>localStorage.getItem('neveai.models.layout')),null);
    assert.equal(await p.getByRole('button',{name:'Grade',exact:true}).getAttribute('aria-pressed'),'true');
    await checkGutter();
    await p.getByRole('button',{name:'Lista',exact:true}).click();
    assert.equal(await columns(),1);
    await checkGutter();
    const sort = p.getByRole('button',{name:'Ordenar modelos'});
    await sort.click();await p.getByText('Tamanho',{exact:true}).last().click();
    assert.match(await firstRow.innerText(),/Model-40/);
    await check('list','.unified-model-list','[data-model-key]','.model-avatar',false,5);
    await sort.click();await p.getByText('Nome',{exact:true}).last().click();
    assert.match(await firstRow.innerText(),/Model-01/);
    const card = firstRow.locator('.unified-model-card');
    const paint = el => el.evaluate(node => getComputedStyle(node).backgroundColor);
    await p.mouse.move(0,0);
    const idle = await paint(card);
    await card.hover({position:{x:8,y:8}});
    assert.notEqual(await paint(card),idle);
    const del = firstRow.getByRole('button',{name:'Excluir',exact:true});
    const idleDelete = await paint(del);
    await del.hover();
    assert.notEqual(await paint(del),idleDelete);
    for (const [width,height] of [[1000,620],[390,844],[1280,800]]) {
      await p.setViewportSize({width,height});
      await p.locator('.unified-model-list').evaluate(async el=>{
        await new Promise(requestAnimationFrame);
        const rows=[...el.querySelectorAll('[data-model-key]')];
        const step=rows[1].offsetTop-rows[0].offsetTop;
        if (el.clientHeight<rows[0].offsetHeight || !step || el.scrollHeight<=el.clientHeight)
          throw new Error('expected a scrollable list with visible rows');
        for(const offset of [0,el.scrollHeight]){
          el.scrollTop=offset;
          const view=el.getBoundingClientRect();
          for(const row of rows){
            const b=row.getBoundingClientRect();
            if(b.bottom>view.top+1 && b.top<view.bottom-1 && (b.top<view.top-1 || b.bottom>view.bottom+1))
              throw new Error('clipped row at '+innerWidth+'x'+innerHeight);
          }
        }
        el.scrollTop=0;
      });
    }
    await firstRow.getByRole('button',{name:'Excluir',exact:true}).click();
    await p.getByRole('button',{name:'Cancelar',exact:true}).last().click();
    assert.equal(await p.locator('.unified-model-editor').count(),0);
    await firstRow.locator('.unified-model-card').click({position:{x:5,y:6}});
    await p.locator('.unified-model-editor').waitFor();
    const titleScale=await p.locator('[data-model-editable-name]').evaluate(el=>parseFloat(getComputedStyle(el).fontSize)/parseFloat(getComputedStyle(document.documentElement).fontSize));
    assert.ok(Math.abs(titleScale-1.4375)<0.01,'editable title is 1.4375rem');
    await p.mouse.click(4,4);await firstRow.waitFor();assert.equal(await columns(),1);
    await p.locator('.unified-models-shell').screenshot({path:out+'/models-list-'+scale+'.png'});
    await p.getByRole('button',{name:'Grade',exact:true}).click();assert.equal(await columns(),2);
    await p.getByRole('button',{name:/^Baixar modelos$/i}).click();
    await p.locator('[data-hf-repo]').first().waitFor({state:'attached'});
    await check('catalog','[data-download-list]','[data-catalog-model],[data-hf-repo]','img,svg',true,10);
    await p.locator('[data-hf-repo] button').first().click();
    await check('files','[data-hf-model-list]','[data-hf-file]','button svg',false,8);
    await p.close();
  }
  assert.deepEqual(issues,[]);
} finally {
  await browser.close(); server.closeAllConnections(); server.close();
}
