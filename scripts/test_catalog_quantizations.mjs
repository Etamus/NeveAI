import assert from 'node:assert/strict';
import {chromium} from '../logs/ui-image-26/node_modules/playwright/index.mjs';
import {installMobileOfflineApi} from './fixtures/mobile-offline-api.mjs';
import {createServer} from 'node:http';
import sirv from 'sirv';

const b=await chromium.launch({executablePath:process.env.NEVE_TEST_BROWSER});
const server=createServer(sirv(process.env.NEVE_BUILD_DIR ?? 'backend/neveai/frontend',{single:true}));
try{
 await new Promise((resolve,reject)=>server.once('error',reject).listen(0,'127.0.0.1',resolve));
 const p=await b.newPage({locale:'pt-BR',viewport:{width:1440,height:900}});p.setDefaultTimeout(7000);
 await installMobileOfflineApi(p);
 await p.addInitScript(()=>localStorage.setItem('token','fixture'));
 const neve='NeveAI/Neve-Sense-2-20B-GGUF',hf='Team/Testing-GGUF';
 const weights=Object.fromEntries([neve,hf].map(repo=>[repo,['Q4.gguf','Q6.gguf'].map(path=>({path,local_filename:repo.replace('/','--')+'--'+path,size:100,installed:true}))]));const deleted=[];
 await p.route('**/llamacpp/models',r=>r.fulfill({json:{models:Object.values(weights).flat().filter(w=>w.installed).map(w=>({id:'local/'+w.local_filename.slice(0,-5),filename:w.local_filename,file_size:w.size,is_loaded:false}))}}));
 await p.route('**/llamacpp/catalog',r=>r.fulfill({json:{models:[{id:'neve-sense',repo:neve,name:'Neve Sense',installed:false}]}}));
 await p.route('**/llamacpp/huggingface/search?**',r=>r.fulfill({json:{models:[{id:hf,downloads:100,likes:1}],next_cursor:null}}));
 await p.route('**/llamacpp/huggingface/files?**',r=>r.fulfill({json:{models:weights[new URL(r.request().url()).searchParams.get('repo')],encoders:[]}}));
 await p.route('**/llamacpp/models/delete',r=>{const body=r.request().postDataJSON();deleted.push(body);Object.values(weights).flat().find(w=>w.local_filename===body.filename).installed=false;return r.fulfill({json:{removed_models:[body.filename],removed_mmproj:[]}})});
 const openHub=async()=>{await p.getByRole('button',{name:/^Modelos$/}).first().click();await p.getByRole('button',{name:/^Baixar modelos$/i}).click();};
 await p.goto('http://127.0.0.1:'+server.address().port);await openHub();
 for (const attr of ['data-catalog-model','data-hf-repo']) await p.locator('['+attr+'] [data-download-status]').filter({hasText:'Instalado'}).waitFor();
 for(const [i,repo] of [neve,hf].entries()){
 const card=i?p.locator('[data-hf-repo]').first():p.locator('[data-catalog-model]').first();
 if(!i)assert.match(await card.innerText(),/Instalado/);
 assert.equal(await card.getByRole('button').count(),1);
 await card.getByRole('button').click();
 const trash=p.locator('[data-delete-hf="Q4.gguf"]');await trash.waitFor();assert.equal(await p.locator('[data-hf-file] [data-download-status]').count(),0);
 await trash.click();await p.getByRole('button',{name:'Cancelar',exact:true}).last().click();await trash.waitFor();assert.equal(deleted.length,i);
 await trash.click();await p.getByRole('button',{name:'Excluir',exact:true}).last().click();
 await p.locator('[data-download-hf="Q4.gguf"]').waitFor();
 assert.equal(await p.locator('[data-delete-hf="Q6.gguf"]').count(),1);
 assert.deepEqual(deleted[i],{filename:weights[repo][0].local_filename,preserve_encoders:true});
 await p.locator('[data-hf-model-header] button').first().click();console.log('OK',repo,deleted[i]);
 }
 await p.reload(); await openHub();
 await p.locator('[data-hf-repo] [data-download-status]').filter({hasText:'Instalado'}).waitFor();
 await p.locator('[data-hf-repo] button').first().click();
 await p.locator('[data-delete-hf="Q6.gguf"]').click();
 await p.getByRole('button',{name:'Excluir',exact:true}).last().click();
 await p.locator('[data-download-hf="Q6.gguf"]').waitFor();
 await p.locator('[data-hf-model-header] button').first().click();
 await p.locator('[data-hf-repo] [data-download-status]').waitFor({state:'hidden'});
 await p.locator('[data-catalog-model] [data-download-status]').filter({hasText:'Instalado'}).waitFor();
}finally{await b.close();server.closeAllConnections();server.close()}
