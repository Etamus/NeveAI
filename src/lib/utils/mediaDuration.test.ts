import { describe, expect, it } from 'vitest';
import { mediaDuration } from './mediaDuration';

describe('media duration', () => {
	it('uses finite metadata when available', () => {
		expect(mediaDuration({ duration: 42, buffered: { length: 0 } as TimeRanges })).toBe(42);
	});
	it('uses buffered duration for WebM without finite duration metadata', () => {
		expect(mediaDuration({ duration: Infinity, buffered: { length: 1, start: () => 0, end: () => 3.5 } })).toBe(3.5);
	});
	it('does not expose non-finite seeking targets', () => {
		expect(mediaDuration({ duration: NaN, buffered: { length: 0 } as TimeRanges })).toBe(0);
		expect(mediaDuration({ duration: Infinity, buffered: { length: 1, start: () => 0, end: () => Infinity } })).toBe(0);
	});
});
