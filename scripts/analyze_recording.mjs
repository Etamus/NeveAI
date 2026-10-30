import fs from 'node:fs';
import utils from '../logs/ui-image-26/node_modules/playwright-core/lib/utilsBundle.js';
const {PNG}=utils;
const files=fs.readdirSync('logs').filter(n=>n.startsWith('recording-live-')&&Number(n.slice(15,-4))>=2);
const base=PNG.sync.read(fs.readFileSync('logs/'+files[0]));
const boxes=[[335,111,315,30],[335,147,315,31],[335,190,315,32],[335,228,315,43],[335,278,315,26],[335,307,315,25],[335,338,315,27]];
for(const file of files){
 const p=PNG.sync.read(fs.readFileSync('logs/'+file));
 const rows=boxes.map(([x,y,w,h])=>{
  const scores=[];
  for(let dy=-2;dy<=2;dy++)for(let dx=-2;dx<=2;dx++){
   let error=0,count=0;for(let yy=y;yy<y+h;yy++)for(let xx=x;xx<x+w;xx++){
    const a=(yy*p.width+xx)*4,b=((yy+dy)*p.width+xx+dx)*4;
    if(base.data[a]>85||p.data[b]>85){error+=Math.abs(base.data[a]-p.data[b]);count++;}
   }scores.push({dx,dy,error:error/Math.max(1,count)});
  }
  scores.sort((a,b)=>a.error-b.error);return {best:scores[0],zero:scores.find(s=>!s.dx&&!s.dy)};
 });
 console.log(file,JSON.stringify(rows));
 const crop=new PNG({width:640,height:560});for(let y=0;y<560;y++)for(let x=0;x<640;x++){const i=((Math.floor(y/2)+92)*p.width+Math.floor(x/2)+330)*4;p.data.copy(crop.data,(y*640+x)*4,i,i+4);}
 fs.writeFileSync('logs/crop-'+file,PNG.sync.write(crop));
}
