import fs from 'node:fs/promises';
import {resolve,sep,extname} from 'node:path';

// Test-only bootstrap: no backend or real user data is accessed.
export async function installMobileOfflineApi(page) {
 const model={id:'local/mobile-fixture',name:'Mobile test model',owned_by:'llamacpp',info:{meta:{}}};
 await page.route('**/api/**',route=>{
  const path=new URL(route.request().url()).pathname;
  let json=[];
  if(path==='/api/config')json={name:'Neve AI',version:'3.0.20',default_models:model.id,features:{auth:false,enable_websocket:false,enable_web_search:true,enable_code_execution:true,enable_image_generation:true,enable_music_generation:true,enable_video_generation:true},file:{max_file_count:10}};
  else if(path.includes('/auths/'))json={id:'mobile-fixture-user',name:'Test user',role:'admin',email:'fixture@example.test',token:'fixture'};
  else if(path==='/api/models'||path==='/api/models/base')json={data:[model]};
  else if(path.includes('/users/user/settings'))json={ui:{models:[model.id]}};
  else if(path.includes('/llamacpp/models'))json={models:[]};
  else if(path.endsWith('/llamacpp/status'))json={server_binary_exists:true};
  else if(path==='/api/version')json={version:'3.0.20'};
  else if(path.includes('/configs/')||path.includes('/version/')||route.request().method()!=='GET')json={};
  return route.fulfill({json});
 });
 await page.route('**/llamacpp/**',route=>{
  const path=new URL(route.request().url()).pathname;
  const json=path.endsWith('/media-state')?{epoch:'offline-fixture',revision:0,busy:false,loaded_models:[]}:path.endsWith('/status')?{server_binary_exists:true}:path.endsWith('/vram')?{available:false}:path.includes('/models')?{models:[]}:{};
  return route.fulfill({json});
 });
 await page.route('**/ws/**',route=>route.fulfill({status:503,body:''}));
 await page.route('**/static/**',async route=>{
  const root=resolve('static'),tail=decodeURIComponent(new URL(route.request().url()).pathname).slice(1);
  for(const candidate of [resolve(root,tail),resolve(root,tail.replace(/^static\//,''))]){
   if(!candidate.startsWith(root+sep))continue;
   try{const body=await fs.readFile(candidate),type={'.png':'image/png','.svg':'image/svg+xml','.webp':'image/webp','.jpg':'image/jpeg','.woff2':'font/woff2','.ico':'image/x-icon'}[extname(candidate)];return route.fulfill({body,contentType:type??'application/octet-stream'});}catch{}
  }
  return route.fulfill({status:404,body:''});
 });
}
