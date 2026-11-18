import { afterEach, expect, it, vi } from 'vitest';
import { createPortPolling } from './visiblePortPolling';

afterEach(() => { vi.useRealTimers(); });

it('reads the collapsed count once and polls only after an expanded visible request completes', async () => {
	vi.useFakeTimers();
	const reads: Array<(ports: number[]) => void> = [];
	const read = vi.fn(() => new Promise<number[]>(resolve => reads.push(resolve)));
	const show = vi.fn(), loading = vi.fn();
	const poll = createPortPolling(read, show, loading);
	poll.update('a', 'k', false, true);
	reads.shift()!([1]); await vi.advanceTimersByTimeAsync(0);
	await vi.advanceTimersByTimeAsync(15000);
	expect(read).toHaveBeenCalledTimes(1);
	poll.update('a', 'k', true, true);
	await vi.advanceTimersByTimeAsync(15000);
	expect(read).toHaveBeenCalledTimes(2);
	reads.shift()!([2]); await vi.advanceTimersByTimeAsync(5000);
	expect(read).toHaveBeenCalledTimes(3);
	poll.update('a', 'k', true, false);
	reads.shift()!([3]); await vi.advanceTimersByTimeAsync(15000);
	expect(show).toHaveBeenLastCalledWith([2]);
	expect(read).toHaveBeenCalledTimes(3);
	poll.update('a', 'k', false, true, true);
	reads.shift()!([4]); await vi.advanceTimersByTimeAsync(0);
	expect(show).toHaveBeenLastCalledWith([4]);
	poll.stop();
});

it('never shows stale ports after switching away and back or closing before a response', async () => {
	vi.useFakeTimers();
	const reads: Array<(ports: number[]) => void> = [];
	const read = vi.fn(() => new Promise<number[]>(resolve => reads.push(resolve)));
	const show = vi.fn();
	const poll = createPortPolling(read, show, () => {});
	poll.update('a', 'first', false, true);
	reads[0]([11]); await vi.advanceTimersByTimeAsync(0);
	poll.update('a', 'other-key', false, true);
	expect(show).toHaveBeenLastCalledWith([]);
	poll.update('a', 'first', false, true);
	reads[1]([22]); await vi.advanceTimersByTimeAsync(0);
	expect(show).toHaveBeenLastCalledWith([]);
	reads[2]([33]); await vi.advanceTimersByTimeAsync(0);
	expect(show).toHaveBeenLastCalledWith([33]);
	poll.update('b', 'first', true, true);
	poll.stop();
	reads[3]([44]); await vi.advanceTimersByTimeAsync(0);
	expect(show).toHaveBeenLastCalledWith([]);
});
