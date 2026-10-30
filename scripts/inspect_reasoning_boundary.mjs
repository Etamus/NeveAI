import {createServer} from 'vite';
import fs from 'node:fs/promises';
const server=await createServer({server:{middlewareMode:true,watch:{ignored:['**/logs/**']}}});
try{
 const {lexChatMarkdown}=await server.ssrLoadModule('/src/lib/utils/marked/chat-lexer.ts');
 const {prepareStreamingMarkdown}=await server.ssrLoadModule('/src/lib/utils/marked/streaming-display.ts');
 const d='<details type="reasoning" done="false">\n<summary>Pensando...</summary>\n&gt; Thinking Process:\n&gt; **Analyze**\n</details>\n';
 const archived=JSON.parse(await fs.readFile('logs/live-continue-ui-before.json','utf8')).before.content;
 for(const p of ['Existing answer?\n','Existing answer?\n\n','Existing answer?\n`','Existing answer?\n```\n',archived.trim()+'\n']){
  for(const live of [false,true]){
   const text=live?prepareStreamingMarkdown(p+d):(p+d);
   const tokens=lexChatMarkdown(text);
   console.log(JSON.stringify({prefix:p.slice(-100),live,end:text.slice(-200),tokens:tokens.map(t=>({type:t.type,raw:t.raw?.slice(0,200)}))}));
  }
 }
}finally{await server.close();}
