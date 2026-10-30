import fs from 'node:fs/promises';
import {createServer} from 'vite';
const data=await(await fetch('http://localhost:8080/api/v1/chats/c7e7801e-c017-4961-8d2b-c13848330d2b')).json();
await fs.mkdir('logs/landing-investigation',{recursive:true});
await fs.writeFile('logs/landing-investigation/original.json',JSON.stringify(data,null,2));
const message=data.chat.history.messages['96b0231d-c776-48cb-80bc-62cd80c28eb0'];
const server=await createServer({server:{middlewareMode:true,watch:{ignored:['**/logs/**']}}});
try{
 const {lexChatMarkdown}=await server.ssrLoadModule('/src/lib/utils/marked/chat-lexer.ts');
 const {prepareStreamingMarkdown}=await server.ssrLoadModule('/src/lib/utils/marked/streaming-display.ts');
 for(const pattern of [/<details[^>]*>/g,/<\/details>/g,/`{3,}[^\n]*/g])for(const match of message.content.matchAll(pattern))console.log(match.index,JSON.stringify(match[0]),JSON.stringify(message.content.slice(Math.max(0,match.index-60),match.index+100)));
 for(const live of [false,true]){
  const content=live?prepareStreamingMarkdown(message.content):message.content;
  console.log(JSON.stringify({live,tokens:lexChatMarkdown(content).map(t=>({type:t.type,length:t.raw.length,head:t.raw.slice(0,90),tail:t.raw.slice(-100)}))},null,2));
 }
}finally{await server.close();}
