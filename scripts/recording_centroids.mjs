import fs from 'node:fs';
import utils from '../logs/ui-image-26/node_modules/playwright-core/lib/utilsBundle.js';
const {PNG}=utils;
const boxes=[[335,114,30,9],[335,150,30,9],[335,193,30,10],[335,232,30,10],[335,281,34,9],[335,310,30,9],[335,341,34,9],[417,200,65,18],[417,234,65,17]];
for(const file of fs.readdirSync('logs').filter(n=>n.startsWith('recording-live-')&&Number(n.slice(15,-4))>=2)){
 const p=PNG.sync.read(fs.readFileSync('logs/'+file));
 const values=boxes.map(([x,y,w,h])=>{let total=0,xx=0,yy=0;for(let j=y;j<y+h;j++)for(let i=x;i<x+w;i++){const k=(j*p.width+i)*4,weight=Math.max(0,p.data[k]-70);total+=weight;xx+=(i-x)*weight;yy+=(j-y)*weight;}return [+(xx/total).toFixed(3),+(yy/total).toFixed(3)];});
 console.log(file,JSON.stringify(values));
}
