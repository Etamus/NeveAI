import fs from 'node:fs';
import utils from '../logs/ui-image-26/node_modules/playwright-core/lib/utilsBundle.js';
const {PNG}=utils;
const prefix=process.argv[2]??'hover-burst-baseline-';
const files=fs.readdirSync('logs').filter(n=>n.startsWith(prefix)&&n.endsWith('.png')).sort((a,b)=>fs.statSync('logs/'+b).mtimeMs-fs.statSync('logs/'+a).mtimeMs).slice(0,150).sort((a,b)=>Number(a.slice(prefix.length,-4))-Number(b.slice(prefix.length,-4)));
const boxes=[[14,228,60,20],[14,316,70,20],[194,228,155,42],[194,316,160,42]];
const rows=files.map(file=>{const p=PNG.sync.read(fs.readFileSync('logs/'+file));return{file,values:boxes.map(([x,y,w,h])=>{let sum=0,xx=0,yy=0;for(let j=y;j<y+h;j++)for(let i=x;i<x+w;i++){const at=(j*p.width+i)*4,v=Math.max(0,p.data[at]-120);sum+=v;xx+=v*(i-x);yy+=v*(j-y);}return{x:xx/sum,y:yy/sum};})};});
console.log('frames',rows.length);
if(process.argv.includes('--assert-stable')){
 if(rows.length!==150)throw Error('Expected 150 frames');
 for(let i=0;i<boxes.length;i++)for(const axis of ['x','y']){
  const span=Math.max(...rows.map(r=>r.values[i][axis]))-Math.min(...rows.map(r=>r.values[i][axis]));
  if(!Number.isFinite(span)||span>0.01)throw Error('Text moved '+span+' pixels');
 }
}
console.log(JSON.stringify(boxes.map((b,i)=>({box:b,xRange:Math.max(...rows.map(r=>r.values[i].x))-Math.min(...rows.map(r=>r.values[i].x)),yRange:Math.max(...rows.map(r=>r.values[i].y))-Math.min(...rows.map(r=>r.values[i].y))})),null,2));
fs.writeFileSync('logs/'+prefix+'analysis.json',JSON.stringify(rows,null,2));
