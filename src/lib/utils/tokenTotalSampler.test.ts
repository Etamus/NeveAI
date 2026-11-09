import { afterEach, describe, expect, it, vi } from 'vitest';
import { createTokenTotalSampler } from './tokenTotalSampler';

afterEach(() => { vi.useRealTimers(); });
describe('sampled token totals', () => {
	it('publishes the latest count every four seconds, not every incoming event', () => {
		vi.useFakeTimers();
		const publish = vi.fn(), sampler = createTokenTotalSampler(publish);
		sampler.update('a', 100, true);
		for (let i = 1; i <= 15; i++) { vi.advanceTimersByTime(250); sampler.update('a', 100+i, true); }
		expect(publish.mock.calls).toEqual([[100]]);
		vi.advanceTimersByTime(250);
		expect(publish.mock.calls).toEqual([[100], [115]]);
		sampler.update('a', 130, true);vi.advanceTimersByTime(4000);
		expect(publish.mock.calls.at(-1)).toEqual([130]);sampler.destroy();
	});
	it('finalization publishes immediately and cancels pending updates', () => {
		vi.useFakeTimers();const publish=vi.fn(), sampler=createTokenTotalSampler(publish);
		sampler.update('a', 100, true);sampler.update('a', 110, true);sampler.update('a', 115, false);
		expect(publish.mock.calls).toEqual([[100],[115]]);vi.advanceTimersByTime(7000);
		expect(publish).toHaveBeenCalledTimes(2);
	});
	it('switching branches or chats never publishes the old pending total', () => {
		vi.useFakeTimers();const publish=vi.fn(), sampler=createTokenTotalSampler(publish);
		sampler.update('a',100,true);sampler.update('a',200,true);sampler.update('b',500,false);
		vi.advanceTimersByTime(7000);expect(publish.mock.calls).toEqual([[100],[500]]);
	});
	it('does not poll identical totals and releases its timer on destruction', () => {
		vi.useFakeTimers();const publish=vi.fn(), sampler=createTokenTotalSampler(publish);
		sampler.update('a',100,true);sampler.update('a',100,true);expect(vi.getTimerCount()).toBe(0);
		sampler.update('a',200,true);sampler.destroy();vi.advanceTimersByTime(7000);
		expect(publish.mock.calls).toEqual([[100]]);
	});
});
