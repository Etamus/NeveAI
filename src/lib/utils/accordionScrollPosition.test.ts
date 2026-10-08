import { describe, expect, it } from 'vitest';
import { getAccordionScrollPosition, type AccordionScrollState } from './accordionScrollPosition';

const state: AccordionScrollState = {
	startTop: 500, startMax: 500, targetTop: null, followBottom: true, revealLimit: 300
};

describe('accordion scroll position', () => {
	it('reveals a short block at the bottom', () => {
		expect(getAccordionScrollPosition(state, 615, 1)).toEqual({ top: 615, spacer: 0 });
	});
	it('limits a large reveal so the header remains in the viewport', () => {
		expect(getAccordionScrollPosition(state, 2500, 1)).toEqual({ top: 800, spacer: 0 });
	});
	it('does not follow the bottom when reading earlier messages', () => {
		expect(getAccordionScrollPosition({ ...state, startTop: 200, followBottom: false }, 900, 1)).toEqual({ top: 200, spacer: 0 });
	});
	it('returns to the pre-expansion position after reading to the end', () => {
		expect(getAccordionScrollPosition({ ...state, startTop: 1800, targetTop: 500 }, 500, 1)).toEqual({ top: 500, spacer: 0 });
	});
	it('clamps to the natural bottom when collapsing without a saved position', () => {
		expect(getAccordionScrollPosition({ ...state, startTop: 900, followBottom: false }, 500, 1)).toEqual({ top: 500, spacer: 0 });
	});
	it('supports collapse only during animation and never leaves scrollable compensation', () => {
		const closing = { ...state, startTop: 900, startMax: 900, targetTop: null, followBottom: false };
		const frames = [0, .25, .5, .75, 1].map(p => getAccordionScrollPosition(closing, 500, p));
		expect(frames[0].spacer).toBe(400);
		expect(frames.at(-1)).toEqual({ top: 500, spacer: 0 });
		for (let i = 1; i < frames.length; i++) expect(frames[i].top).toBeLessThanOrEqual(frames[i - 1].top);
	});
	it('follows each rendered expansion frame without delaying the scroll a second time', () => {
		for (const [height, progress] of [[510, .05], [560, .2], [610, .5], [615, 1]]) {
			expect(getAccordionScrollPosition(state, height, progress)).toEqual({ top: height, spacer: 0 });
		}
	});
	it('keeps the answer below stationary throughout a rendered collapse', () => {
		const closing = { ...state, startTop: 900, startMax: 900, targetTop: 500, followBottom: false };
		for (const [height, progress] of [[900, 0], [800, .25], [700, .5], [600, .75], [500, 1]]) {
			expect(getAccordionScrollPosition(closing, height, progress)).toEqual({ top: height, spacer: 0 });
		}
	});
	it('keeps short conversations at zero when they do not overflow', () => {
		expect(getAccordionScrollPosition({ ...state, startTop: 0, startMax: 0 }, 0, 1)).toEqual({ top: 0, spacer: 0 });
	});
	it('retains fractional growth without clamping to a fractional native maximum', () => {
		const opening = { ...state, startTop: 501, startMax: 500.6 };
		expect(getAccordionScrollPosition(opening, 580.7, .3).top).toBe(581);
		const closing = { ...state, startTop: 601, startMax: 600.9, targetTop: 501, followBottom: false };
		expect(getAccordionScrollPosition(closing, 580.7, .3).top).toBeCloseTo(580.8);
		expect(getAccordionScrollPosition(closing, 500.6, 1)).toEqual({ top: 501, spacer: 0 });
	});
});
