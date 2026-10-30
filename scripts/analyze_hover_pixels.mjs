import fs from 'node:fs';
import utils from '../logs/ui-image-26/node_modules/playwright-core/lib/utilsBundle.js';
const {PNG}=utils;
const prefix=process.argv[2]??'logs/real-hover-baseline';
const base=PNG.sync.read(fs.readFileSync(prefix+'-before.png'));
for(const point of ['0.1-0.1','0.8-0.2','0.2-0.7','0.85-0.85','0.5-0.5']){
 const next=PNG.sync.read(fs.readFileSync(prefix+'-'+point+'.png'));
 const masks=[base,next].map(p=>{const m=new Set();for(let y=45;y<p.height;y++)for(let x=5;x<p.width-5;x++){const i=(y*p.width+x)*4;if(process.argv.includes('--dark')?Math.min(p.data[i],p.data[i+1],p.data[i+2])>180:Math.max(p.data[i],p.data[i+1],p.data[i+2])<130)m.add(y*p.width+x);}return m;});
 const scores=[];for(let dy=-2;dy<=2;dy++)for(let dx=-2;dx<=2;dx++){let common=0;for(const i of masks[0]){const x=i%base.width+dx,y=Math.floor(i/base.width)+dy;if(masks[1].has(y*base.width+x))common++;}scores.push({dx,dy,score:common/Math.max(1,masks[0].size+masks[1].size-common)});}
 scores.sort((a,b)=>b.score-a.score);console.log(point,JSON.stringify({best:scores[0],zero:scores.find(s=>s.dx===0&&s.dy===0)}));
}
