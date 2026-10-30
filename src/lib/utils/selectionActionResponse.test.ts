import {describe, expect, it} from 'vitest';
import {getSelectionActionParams} from './selectionActions';
import {createSelectionActionStream, formatSelectionActionResponse as format} from './selectionActionResponse';
import {createChatMarkdownParser} from './marked/chat-lexer';
import type {Token, Tokens} from 'marked';

const reasoningToken = (tokens: Token[]) => {
	const token = tokens.find(t => t.type === 'details');
	if (!token) throw new Error('Missing reasoning token');
	return token as Tokens.Generic;
};

describe('selection reasoning policy', () => {
	it.each([{id:'local/Qwen3'}, {id:'remote',name:'Ordinary model'}])('disables reasoning without changing chat settings: %o', model => {
		const params={temperature:0.8,reasoning_mode:'reasoning',reasoning_unlimited:true,reasoning_extended:true};
		const before=structuredClone(params);
		expect(getSelectionActionParams(params,model)).toMatchObject({temperature:0.8,reasoning_mode:'quick',no_think:true,reasoning_extended:false,reasoning_unlimited:false});
		expect(params).toEqual(before);
	});
	it.each([{id:'gpt-oss:20b'}, {name:'Neve Sense'}, {info:{meta:{neve_catalog_id:'neve-sense'}}}, {llamacpp:{reasoning_control:'effort'}}])('respects the same effort-only exceptions as chat: %o', model => {
		expect(getSelectionActionParams({no_think:true,reasoning_effort:'high'},model)).toMatchObject({no_think:false,reasoning_mode:'quick',reasoning_effort:'low'});
	});
	it('does not allow custom reasoning overrides to undo the selection policy', () => {
		const params={custom_params:{reasoning_mode:'reasoning',no_think:false,reasoning_effort:'high',temperature:0.7}};
		const before=structuredClone(params);
		expect(getSelectionActionParams(params,{id:'local/Qwen3'})).toMatchObject({no_think:true,custom_params:{temperature:0.7}});
		expect(params).toEqual(before);
		expect(getSelectionActionParams(params,{id:'gpt-oss'}).custom_params).not.toHaveProperty('reasoning_effort');
	});
});

describe('selection reasoning rendering', () => {
	it.each(['think','thinking','thought','analysis','reasoning','reason'])('keeps %s inside a standard reasoning block during and after streaming', tag => {
		const parser=createChatMarkdownParser();
		const streaming=parser(format(`<${tag}>Private thought`));
		expect(streaming.filter(t=>t.type==='details')).toHaveLength(1);
		expect(reasoningToken(streaming).attributes).toMatchObject({type:'reasoning',done:'false'});
		const tokens=parser(format(`<${tag}>Private thought</${tag}>Answer`, '', true));
		expect(reasoningToken(tokens).attributes.done).toBe('true');
		expect(tokens.slice(1).some(t=>t.raw.includes('Private thought'))).toBe(false);
		expect(tokens.some(t=>t.raw.includes('Answer'))).toBe(true);
	});
	it('separates GPT-OSS Harmony analysis and final channels', () => {
		const tokens=createChatMarkdownParser()(format('<|start|>assistant<|channel|>analysis<|message|>Think<|end|><|start|>assistant<|channel|>final<|message|>Answer','',true));
		expect(reasoningToken(tokens).attributes.type).toBe('reasoning');
		expect(reasoningToken(tokens).text).toContain('Think');
		expect(tokens.at(-1)?.raw).toContain('Answer');
		expect(tokens.at(-1)?.raw).not.toContain('Think');
	});
	it('does not transform literal markers in fenced, inline, or indented code', () => {
		for(const content of ['```xml\n<think>literal</think>\n```','`<think>literal</think>`','    <think>literal</think>'])expect(format(content,'',true)).toBe(content);
		expect(format('<think>Code: `</think>` still thought</think>Answer','',true)).toContain('&lt;/think&gt;');
		const content='<think>\nExample:\n```xml\n</think>\n```\nStill thinking\n</think>Answer';
		const tokens=createChatMarkdownParser()(format(content,'',true));
		expect(reasoningToken(tokens).text).toContain('Still thinking');
		expect(tokens.at(-1)?.raw).toContain('Answer');
	});
	it('keeps already-normalized details and tables intact', () => {
		const content='<details type="reasoning" done="true">\n<summary>Thought</summary>\n\n> Thought\n</details>\n\n| A | B |\n| - | - |\n| 1 | 2 |';
		expect(format(content,'',true)).toBe(content);
	});
	it('holds partial opening markers until their meaning is known', () => {
		expect(format('<thi')).toBe('');
		expect(format('<|channel|>anal')).toBe('');
		expect(format('<thi','',true)).toBe('<thi');
	});
	it('escapes untrusted reasoning markup and marks the block complete when the answer begins', () => {
		const tokens=createChatMarkdownParser()(format('Answer','Thought </details><script>alert(1)</script>'));
		expect(reasoningToken(tokens).attributes.done).toBe('true');
		expect(tokens.filter(t=>t.type==='details')).toHaveLength(1);
		expect(tokens.at(-1)?.raw).toContain('Answer');
	});
});

const stream = (events: any[], done = true) => {
	const bytes=new TextEncoder().encode(events.map(e=>'data: '+JSON.stringify(e)+'\n\n').join('')+(done?'data: [DONE]\n\n':''));
	return new ReadableStream<Uint8Array>({start(c){for(let i=0;i<bytes.length;i+=3)c.enqueue(bytes.slice(i,i+3));c.close();}});
};
describe('selection raw SSE', () => {
	it.each(['reasoning_content','reasoning','thinking'])('retains %s separately from answer, even with Unicode byte splits', async key => {
		const updates=[];
		for await(const u of createSelectionActionStream(stream([{choices:[{delta:{[key]:'Raciocínio'}}]},{choices:[{delta:{content:'Resposta'}}]}])))updates.push(u);
		expect(updates.map(u=>u.reasoning).join('')).toBe('Raciocínio');
		expect(updates.map(u=>u.value).join('')).toBe('Resposta');
		expect(updates.at(-1)?.done).toBe(true);
	});
	it('retains reasoning and content sent in the same event and finishes on EOF', async () => {
		const updates=[];for await(const u of createSelectionActionStream(stream([{choices:[{delta:{reasoning_content:'Thought',content:'Answer'}}]}],false)))updates.push(u);
		expect(updates[0]).toMatchObject({reasoning:'Thought',value:'Answer'});expect(updates.at(-1)?.done).toBe(true);
	});
	it('accepts the populated alias when the first reasoning field is empty', async () => {
		const updates=[];for await(const u of createSelectionActionStream(stream([{choices:[{delta:{reasoning_content:'',reasoning:'Thought'}}]}])))updates.push(u);
		expect(updates[0].reasoning).toBe('Thought');
	});
	it('surfaces upstream errors', async () => {
		const run=async()=>{for await(const _ of createSelectionActionStream(stream([{error:{message:'Unavailable'}}]))){};};
		await expect(run()).rejects.toThrow('Unavailable');
	});
	it('cancels the upstream reader when the popup stops consuming', async () => {
		let cancelled=false;
		const body=new ReadableStream<Uint8Array>({start(c){c.enqueue(new TextEncoder().encode('data: {"choices":[{"delta":{"content":"Partial"}}]}\n\n'));},cancel(){cancelled=true;}});
		const iterator=createSelectionActionStream(body);await iterator.next();await iterator.return(undefined);
		expect(cancelled).toBe(true);
	});
});
