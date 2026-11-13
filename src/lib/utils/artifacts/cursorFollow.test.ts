import { expect, it } from 'vitest';
import { verticalFollowDelta } from './cursorFollow';

it('scrolls only enough to keep the changed point inside the viewport', () => {
	expect(verticalFollowDelta(200, 0, 600)).toBe(0);
	expect(verticalFollowDelta(800, 0, 600)).toBe(232);
	expect(verticalFollowDelta(-40, 0, 600)).toBe(-72);
	expect(verticalFollowDelta(650, 100, 600)).toBe(0);
	expect(verticalFollowDelta(750, 100, 600)).toBe(82);
	expect(verticalFollowDelta(30, 0, 40)).toBe(0);
});
