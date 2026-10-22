import { describe, expect, it } from 'vitest';
import { getLastChatUsage, getChatContextWindow, getUsageContextWindow, getUsageTotalTokens, formatUsageTokensPerSecond } from './chatUsage';

describe('context at request start', () => {
	const makeHistory = () => ({currentId: 'pending', messages: {
		previous: {role: 'assistant', done: true, usage: {context_window: 8192, total_tokens: 100, tokens_per_second: 109}},
		pending: {role: 'assistant', done: false, parentId: 'previous', context_window: 32768, usage: undefined as any}
	}});
	it('updates context immediately without replacing completed totals or speed', () => {
		const h = makeHistory();
		expect(getChatContextWindow(h)).toBe(32768);
		expect(getLastChatUsage(h)).toEqual(h.messages.previous.usage);
		expect(getChatContextWindow(JSON.parse(JSON.stringify(h)))).toBe(32768);
	});
	it('prefers the backend measurement when received', () => {
		const h = makeHistory();
		h.messages.pending.usage = {context_window: 16384};
		expect(getChatContextWindow(h)).toBe(16384);
	});
	it('keeps contexts independent of other chats and model selections', () => {
		const a = makeHistory(), b = makeHistory();
		b.messages.pending.context_window = 65536;
		expect(getChatContextWindow(a)).toBe(32768);
		expect(getChatContextWindow(b)).toBe(65536);
	});
	it('works for the first response before any usage exists', () => {
		expect(getChatContextWindow({currentId: 'a', messages: {a: {role: 'assistant', context_window: 32768, done: false}}})).toBe(32768);
	});
	it('never invents a context for missing or circular history', () => {
		expect(getChatContextWindow(null)).toBeNull();
		expect(getChatContextWindow({currentId: 'a', messages: {a: {role: 'assistant', parentId: 'a'}}})).toBeNull();
	});
});

describe('integer tokens per second display', () => {
	it.each([
		[109.153, '109'], [109.096, '109'], [12.75, '13'],
		[0, '0'], [null, '0'], [Infinity, '0']
	])('formats %s as %s', (value, expected) => {
		expect(formatUsageTokensPerSecond(value)).toBe(expected);
	});
});

describe('generation context persisted with token usage', () => {
	it.each([
		[{prompt_n: 27, predicted_n: 39, context_window: 8192}, 66],
		[{prompt_n: 42, predicted_n: 11, context_window: 8192}, 53],
		[{prompt_tokens: 800, completion_tokens: 224}, 1024],
		[{input_tokens: 800, output_tokens: 224}, 1024],
		[{total_tokens: 120, prompt_n: 27, predicted_n: 39}, 120],
		[{total_tokens: 0, prompt_n: 27, predicted_n: 39}, 66],
		[{prompt_n: '27', predicted_n: '39'}, 66],
		[{prompt_tokens: 'invalid', prompt_n: 27, output_tokens: -1, predicted_n: 39}, 66],
		[{prompt_n: 0, predicted_n: 39}, 39],
		[{context_window: 8192}, 0],
		[null, 0]
	])('calculates totals for normalized and raw llama.cpp usage: %j', (usage, total) => {
		expect(getUsageTotalTokens(usage)).toBe(total);
	});
	it('preserves the recorded context across serialization and model changes', () => {
		const history = {currentId: 'b', messages: {
			a: {role: 'assistant', done: true, usage: {total_tokens: 1000, context_window: 8192}},
			b: {role: 'user', parentId: 'a'}
		}};
		const restored = JSON.parse(JSON.stringify(history));
		expect(getUsageContextWindow(getLastChatUsage(restored))).toBe(8192);
	});
	it('follows only the current branch and ignores unfinished responses', () => {
		const history = {currentId: 'b', messages: {
			a: {role: 'assistant', done: true, usage: {context_window: 4096}},
			b: {role: 'assistant', done: false, parentId: 'a', usage: {context_window: 32768}},
			c: {role: 'assistant', done: true, usage: {context_window: 65536}}
		}};
		expect(getUsageContextWindow(getLastChatUsage(history))).toBe(4096);
	});
	it.each([undefined, null, 0, -1, 'invalid', Infinity])('never invents a context for missing or invalid data: %s', (value) => {
		expect(getUsageContextWindow({context_window: value})).toBeNull();
	});
	it('terminates safely with missing or circular history', () => {
		expect(getLastChatUsage(null)).toBeNull();
		expect(getLastChatUsage({currentId: 'a', messages: {a: {parentId: 'a'}}})).toBeNull();
	});
});
