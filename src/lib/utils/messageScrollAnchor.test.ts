import { describe, expect, it, vi } from 'vitest';
import { getMessageAnchorScrollTop, getMessageScrollAnchor } from './messageScrollAnchor';

describe('message scroll anchor', () => {
	it('uses the user bubble rather than its image attachments', () => {
		const bubble = {} as HTMLElement;
		const message = { querySelector: vi.fn(() => bubble) } as unknown as HTMLElement;
		expect(getMessageScrollAnchor(message)).toBe(bubble);
		expect(message.querySelector).toHaveBeenCalledWith('[data-user-message-scroll-anchor]');
	});

	it('preserves the anchor for text-only, image-only and assistant messages', () => {
		const message = { querySelector: () => null } as unknown as HTMLElement;
		expect(getMessageScrollAnchor(message)).toBe(message);
	});
});

describe('message anchor positioning', () => {
	it('compensates for media that gains height above the user bubble', () => {
		const initial = getMessageAnchorScrollTop(300, 80, 208, 128);
		const afterMediaLoads = getMessageAnchorScrollTop(initial, 80, 408, 128);

		expect(initial).toBe(300);
		expect(afterMediaLoads).toBe(500);
	});

	it('never requests a negative scroll position', () => {
		expect(getMessageAnchorScrollTop(0, 100, 80, 128)).toBe(0);
	});
});
