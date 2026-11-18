import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import ts from 'typescript';
import {chromium} from '../logs/ui-image-26/node_modules/playwright/index.mjs';
import http from 'node:http';
import {spawn, execFile} from 'node:child_process';
import {promisify} from 'node:util';
const root=process.cwd(), state=JSON.parse(await fs.readFile('.desktop/installed.json','utf8'));
const dir=await fs.mkdtemp(path.join(root,'logs/save-as-'));
const {outputText:code}=ts.transpileModule(await fs.readFile('src/lib/utils/chatFileSave.ts','utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ESNext}});
let reads=0;
const server=http.createServer((req,res)=>{
  if(req.url==='/helper.js'){res.setHeader('Content-Type','text/javascript');res.end(code);return;}
  if(req.url==='/file'){reads++;res.end('fixture');return;}
  res.setHeader('Content-Type','text/html');
  res.end(`<button>save</button><script type="module">import {saveChatFile} from '/helper.js';chrome.webview.postMessage({type:'neve:ready'});document.querySelector('button').onclick=async()=>{await saveChatFile('file.txt',()=>fetch('/file'));document.body.dataset.done='yes'};</script>`);
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
try {
  for(const mode of ['save','repeat','cancel']) {
    const folder=path.join(dir,mode); await fs.mkdir(folder);
    const target=path.join(dir,'save',mode==='repeat'?'repeat.txt':'selected.txt');
    const prior=reads;
    const proc=spawn(path.join(root,'.desktop',state.host),['--root',root,'--runtime',path.join(root,'.desktop',state.runtime),'--profile',path.join(folder,'profile'),'--url','http://127.0.0.1:'+server.address().port],{windowsHide:true,env:{...process.env,NEVE_WEBVIEW2_TEST_MODE:'1',NEVE_WEBVIEW2_DEBUG_PORT:'9237'}});
    let browser;
    try {
      for(let i=0;i<80&&!browser;i++){browser=await chromium.connectOverCDP('http://127.0.0.1:9237',{timeout:400}).catch(()=>null);if(!browser)await new Promise(r=>setTimeout(r,100));}
      const page=browser.contexts()[0].pages()[0];
      // Playwright redirects downloads; exercise the actual WebView2 download manager instead.
      const cdp=await browser.newBrowserCDPSession();
      await cdp.send('Browser.setDownloadBehavior',{behavior:'default'});
      await page.waitForFunction(()=>window.__NEVE_NATIVE_DOWNLOADS__===true && document.querySelector('button')?.onclick);
      await page.getByRole('button',{name:'save'}).click();
      
      await promisify(execFile)('powershell.exe',['-NoProfile','-ExecutionPolicy','Bypass','-File','scripts/test_save_dialog.ps1','-HostPid',String(proc.pid),'-Destination',mode==='repeat'?'repeat.txt':target,'-ExpectedFilter','TXT (*.txt)',...(mode==='cancel'?['-Cancel']:[])],{windowsHide:true,timeout:22000});
      await page.waitForFunction(()=>document.body.dataset.done==='yes',{},{timeout:12000});
      assert.equal(reads,prior+1);
      if(mode!=='cancel') {
        for(let i=0;i<60;i++){if(await fs.readFile(target,'utf8').catch(()=>null)==='fixture')break;await new Promise(r=>setTimeout(r,100));}
        assert.equal(await fs.readFile(target,'utf8'),'fixture');
      } else {await new Promise(r=>setTimeout(r,500));assert.deepEqual(await fs.readdir(path.join(folder,'profile','DownloadStaging')),[]);}
      console.log('PASS native Save As:',mode);
    } finally { await browser?.close().catch(()=>{});proc.kill(); }
  }
} finally {server.close();}
