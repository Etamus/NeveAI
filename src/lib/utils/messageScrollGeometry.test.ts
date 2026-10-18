import { afterEach, describe, expect, it, vi } from 'vitest';
import { consumeGenerationSpacerHeight, getMessagesContentHeight, hasHiddenMessageContentBelow } from './messageScrollGeometry';

afterEach(() => {
	vi.unstubAllGlobals();
});

describe('Scroll-to-bottom button visibility', () => {
	const viewport = (messageBottom: number | null) => ({
		getBoundingClientRect: () => ({ bottom: 900 }),
		querySelector: () => messageBottom === null ? null : { getBoundingClientRect: () => ({ bottom: messageBottom }) },
		scrollHeight: 4000,
		scrollTop: 0
	}) as unknown as HTMLElement;
	it.each([200, 600, 700, 704.5])('ignores reserved scrolling when the last message ends at %s', bottom => {
		expect(hasHiddenMessageContentBelow(viewport(bottom), 700)).toBe(false);
	});
	it('shows the button for content hidden by the composer', () => {
		expect(hasHiddenMessageContentBelow(viewport(750), 700)).toBe(true);
	});
	it('shows the button for messages below the viewport even if the composer is absent', () => {
		expect(hasHiddenMessageContentBelow(viewport(1000), 1100)).toBe(true);
	});
	it('reacts to composer expansion without counting its bottom reservation', () => {
		const container = viewport(650);
		expect(hasHiddenMessageContentBelow(container, 700)).toBe(false);
		expect(hasHiddenMessageContentBelow(container, 600)).toBe(true);
	});
	it('does not show a button before messages mount', () => {
		expect(hasHiddenMessageContentBelow(viewport(null), 700)).toBe(false);
	});
});

describe('Gradual generation spacer consumption', () => {
	it.each([[441, 12, 429], [441, 1, 440], [441, 0, 441], [441, -12, 441], [10, 50, 0]])(
		'consumes only the upward distance: %s - %s = %s', (height, distance, expected) => {
			expect(consumeGenerationSpacerHeight(height, distance)).toBe(expected);
		}
	);
	it('consumes the remaining filler progressively even after a short chat reaches the top', () => {
		let height = 441;
		for (let i = 0; i < 36; i++) height = consumeGenerationSpacerHeight(height, 12);
		expect(height).toBe(9);
		expect(consumeGenerationSpacerHeight(height, 12)).toBe(0);
	});
});

function fixture(height: number, viewportHeight: number, spacer: number) {
	const wrapper = { getBoundingClientRect: () => ({ top: 50 }) };
	const content = {
		parentElement: wrapper,
		getBoundingClientRect: () => ({ top: 50, bottom: 50 + height + spacer, height: height + spacer })
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
	it('ignores leading free space when a short completed conversation is bottom-aligned', () => {
		const container = fixture(200, 843, 0);
		const content = container.querySelector('[data-messages-content]')!;
		content.getBoundingClientRect = () => ({ top: 600, bottom: 800, height: 200 }) as DOMRect;
		expect(getMessagesContentHeight(container, 0)).toBe(320);
	});
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
