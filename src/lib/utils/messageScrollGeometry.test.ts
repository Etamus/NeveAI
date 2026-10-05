import { afterEach, describe, expect, it, vi } from 'vitest';
import { getMessagesContentHeight } from './messageScrollGeometry';

afterEach(() => {
	vi.unstubAllGlobals();
});

function fixture(height: number, viewportHeight: number, spacer: number) {
	const wrapper = { getBoundingClientRect: () => ({ top: 50 }) };
	const content = {
		parentElement: wrapper,
		getBoundingClientRect: () => ({ bottom: 50 + height + spacer })
	};
	const container = {
		clientHeight: viewportHeight,
		scrollHeight: Math.max(viewportHeight, height + spacer + 120),
		querySelector: () => content
	};
	vi.stubGlobal('getComputedStyle', (element: unknown) =>
		element === wrapper ? { paddingBottom: '110px' } : { paddingTop: '0px', paddingBottom: '10px' }
	);
	return container as unknown as HTMLElement;
}

describe('Natural message height without viewport filler', () => {
	it.each([0, 100, 300, 600])('measures short content with a %s px spacer', (spacer) => {
		expect(getMessagesContentHeight(fixture(400, 843, spacer), spacer)).toBe(520);
	});
	it('reserves enough height at the first overflow without clamping the target', () => {
		const viewport = 843,
			target = 172;
		const natural = getMessagesContentHeight(fixture(400, viewport, 300), 300);
		const requiredSpacer = Math.ceil(target + viewport - natural);
		expect(natural + requiredSpacer - viewport).toBe(target);
		// The same calculation remains stable after the spacer has been applied.
		expect(getMessagesContentHeight(fixture(400, viewport, requiredSpacer), requiredSpacer)).toBe(
			natural
		);
	});
	it('measures content taller than the viewport', () => {
		expect(getMessagesContentHeight(fixture(1600, 843, 250), 250)).toBe(1720);
	});
	it('retains fractional heights and handles zero content', () => {
		expect(getMessagesContentHeight(fixture(0.5, 843, 250), 250)).toBe(120.5);
	});
	it('falls back safely before the message list mounts', () => {
		const container = { scrollHeight: 100, querySelector: () => null } as unknown as HTMLElement;
		expect(getMessagesContentHeight(container, 200)).toBe(0);
	});
});
