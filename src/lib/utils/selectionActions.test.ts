import { describe, expect, it } from 'vitest';
import { getSelectionActionLabel } from './selectionActions';
import { createOpenAITextStream } from '../apis/streaming';

describe('selection actions', () => {
	it.each([
		['ask', 'Perguntar', 'Ask'], ['ask', 'Ask', 'Ask'],
		['explain', 'Explicar', 'Explain'], ['explain', 'Explain', 'Explain'],
		['ask', 'Custom question', 'Custom question'], ['custom', 'Explicar', 'Explicar']
	])('localizes built-in labels without rewriting custom actions', (id, label, expected) => {
		expect(getSelectionActionLabel({id, label}, key => key)).toBe(expected);
	});
	it('uses the current language for built-in actions', () => {
		expect(getSelectionActionLabel({id:'ask', label:'Ask'}, () => 'Perguntar')).toBe('Perguntar');
	});
	it.each([true, false])('retains fragmented SSE text and completes with or without DONE: %s', async done => {
		const text = 'data: '+JSON.stringify({choices:[{delta:{content:'Hello'}}]})+'\n\n'
			+'data: '+JSON.stringify({choices:[{delta:{content:' world'}}]})+'\n\n'+(done?'data: [DONE]\n\n':'');
		const bytes = new TextEncoder().encode(text);
		const body = new ReadableStream({start(controller){
			for(let offset=0;offset<bytes.length;offset+=3) controller.enqueue(bytes.slice(offset,offset+3));
			controller.close();
		}});
		const updates=[];
		for await (const update of await createOpenAITextStream(body,false)) updates.push(update);
		expect(updates.map(update=>update.value).join('')).toBe('Hello world');
		expect(updates.at(-1)?.done).toBe(true);
	});
	it('surfaces SSE errors instead of reporting a successful response', async () => {
		const body = new ReadableStream({start(controller){controller.enqueue(new TextEncoder().encode('data: {"error":{"message":"Model unavailable"}}\n\n'));controller.close();}});
		const updates=[];
		for await(const update of await createOpenAITextStream(body,false)) updates.push(update);
		expect(updates[0].error.message).toBe('Model unavailable');
	});
});
