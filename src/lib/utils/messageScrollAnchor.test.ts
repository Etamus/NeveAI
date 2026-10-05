import { describe, expect, it, vi } from 'vitest';
import { getMessageScrollAnchor } from './messageScrollAnchor';

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
