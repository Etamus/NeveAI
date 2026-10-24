import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createStreamingMarkdownScheduler } from './streaming-parser';
import { createChatMarkdownParser, lexChatMarkdown } from './chat-lexer';

describe('streaming Markdown scheduling', () => {
	beforeEach(() => {
		vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'performance'] });
	});
	afterEach(() => {
		vi.useRealTimers();
	});

	it('flushes the first content immediately after an empty mount, then batches appends', () => {
		let source = '';
		const seen: string[] = [];
		const scheduler = createStreamingMarkdownScheduler(() => {
			seen.push(source);
		});
		scheduler.update(true, false);
		vi.advanceTimersByTime(1);
		source = 'First';
		scheduler.update(false, true);
		expect(seen).toEqual(['', 'First']);
		expect(vi.getTimerCount()).toBe(0);
		source = 'First response';
		scheduler.update(false, true);
		expect(seen).toEqual(['', 'First']);
		vi.advanceTimersByTime(63);
		expect(seen).toEqual(['', 'First']);
		vi.advanceTimersByTime(1);
		expect(seen).toEqual(['', 'First', 'First response']);
	});

	it('flushes first content again after clearing and cancels pending old content', () => {
		let source = 'Old';
		const seen: string[] = [];
		const scheduler = createStreamingMarkdownScheduler(() => {
			seen.push(source);
		});
		scheduler.update(false, true);
		source = 'Old pending';
		scheduler.update(false, true);
		source = '';
		scheduler.update(true, false);
		source = 'New';
		scheduler.update(false, true);
		expect(seen).toEqual(['Old', '', 'New']);
		expect(vi.getTimerCount()).toBe(0);
		vi.advanceTimersByTime(200);
		expect(seen).toEqual(['Old', '', 'New']);
	});

	it('batches rapid snapshots and parses the latest, even if the stream pauses', () => {
		let source = 'initial';
		const seen: string[] = [];
		const scheduler = createStreamingMarkdownScheduler(() => {
			seen.push(source);
		});
		scheduler.update();
		for (let i = 1; i <= 63; i++) {
			vi.advanceTimersByTime(1);
			source = `snapshot ${i}`;
			scheduler.update();
		}
		expect(seen).toEqual(['initial']);
		vi.advanceTimersByTime(1);
		expect(seen).toEqual(['initial', 'snapshot 63']);
		expect(vi.getTimerCount()).toBe(0);
	});

	it('flushes completion/context changes/clearing immediately and cancels stale work', () => {
		let source = 'old';
		const parse = createChatMarkdownParser();
		let tokens = parse('');
		const callback = vi.fn(() => {
			tokens = parse(source);
		});
		const scheduler = createStreamingMarkdownScheduler(callback);
		scheduler.update();
		source = '```ts\nopen';
		scheduler.update();
		source = '| A |\n| - |\n| final |';
		scheduler.update(true);
		expect(tokens).toEqual(lexChatMarkdown(source));
		expect(vi.getTimerCount()).toBe(0);
		source = '';
		scheduler.update(true);
		expect(tokens).toEqual(lexChatMarkdown(''));
		vi.advanceTimersByTime(1000);
		expect(callback).toHaveBeenCalledTimes(3);
	});

	it('bounds adaptive waiting to 200ms after expensive parsing', () => {
		let now = 0;
		const callback = vi.fn(() => {
			now += 100;
		});
		const scheduler = createStreamingMarkdownScheduler(callback, {
			now: () => now,
			setTimer: (fn, delay) => setTimeout(fn, delay),
			clearTimer: clearTimeout
		});
		scheduler.update();
		scheduler.update();
		vi.advanceTimersByTime(199);
		expect(callback).toHaveBeenCalledTimes(1);
		vi.advanceTimersByTime(1);
		expect(callback).toHaveBeenCalledTimes(2);
	});

	it('limits full parsing to at most 17 calls for 126 updates over one second', () => {
		const callback = vi.fn();
		const scheduler = createStreamingMarkdownScheduler(callback);
		for (let i = 0; i <= 125; i++) {
			scheduler.update();
			vi.advanceTimersByTime(8);
		}
		scheduler.update(true);
		expect(callback.mock.calls.length).toBeLessThanOrEqual(17);
		expect(vi.getTimerCount()).toBe(0);
	});

	it('cancels pending parsing on destroy and ignores subsequent updates', () => {
		const callback = vi.fn();
		const scheduler = createStreamingMarkdownScheduler(callback);
		scheduler.update();
		scheduler.update();
		scheduler.destroy();
		scheduler.update(true);
		vi.runAllTimers();
		expect(callback).toHaveBeenCalledTimes(1);
		expect(vi.getTimerCount()).toBe(0);
	});

	it('renders full-equivalent snapshots through append and mid-stream revisions', () => {
		let source = '';
		const parse = createChatMarkdownParser();
		const scheduler = createStreamingMarkdownScheduler(() => {
			expect(parse(source)).toEqual(lexChatMarkdown(source));
		});
		const final =
			'[link][ref]\n\n| A | B |\n| - | - |\n| $x$ | [1] |\n\n```js\ncode\n```\n\n[ref]: /target';
		for (let i = 0; i <= final.length; i++) {
			source = final.slice(0, i);
			scheduler.update();
			vi.advanceTimersByTime(8);
		}
		source = 'Revision\n\n' + final;
		scheduler.update();
		vi.advanceTimersByTime(64);
		scheduler.update(true);
		expect(parse(source)).toEqual(lexChatMarkdown(source));
		expect(vi.getTimerCount()).toBe(0);
	});
});
