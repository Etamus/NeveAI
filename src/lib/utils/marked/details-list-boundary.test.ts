import {describe,expect,it} from 'vitest';
import {lexChatMarkdown} from './chat-lexer';
import {prepareStreamingMarkdown} from './streaming-display';

const reasoning='<details type="reasoning" done="false">\n<summary>Thinking</summary>\n&gt; Private thought\n</details>\n';
describe('Structured details after list endings',()=>{
 it.each(['1. Last numbered item.\n','- Last bullet item.\n','1. **Text:** An example `<h1>Title</h1>`.\n','> A quote.\n'])('interrupts %s',prefix=>{
  for(const source of [prefix+reasoning,prepareStreamingMarkdown(prefix+reasoning)]){
   const tokens=lexChatMarkdown(source);
   expect(tokens.filter(t=>t.type==='details')).toHaveLength(1);
   expect(tokens.filter(t=>t.type!=='details').some(t=>t.raw.includes('Private thought'))).toBe(false);
  }
 });
 it.each(['```html\n','~~~html\n'])('keeps structured examples literal inside %s',fence=>{
  const tokens=lexChatMarkdown(fence+reasoning+'\n'+fence.slice(0,3));
  expect(tokens.filter(t=>t.type==='details')).toHaveLength(0);
  expect(tokens[0].type).toBe('code');
  expect(tokens[0].raw).toContain(reasoning);
 });
 it.each(['reasoning','tool_calls','code_interpreter'])('separates %s from completed lists',type=>{
  const tokens=lexChatMarkdown('1. Complete.\n'+reasoning.replace('reasoning',type));
  expect(tokens.filter(t=>t.type==='details')).toHaveLength(1);
 });
});
