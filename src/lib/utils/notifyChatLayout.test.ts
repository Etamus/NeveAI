import { describe, expect, it, vi } from 'vitest';
import { notifyChatLayout } from './notifyChatLayout';

describe('notifyChatLayout', () => {
	it('notifies before an accordion changes, with its animation duration', () => {
		class LayoutEvent extends Event {
			detail: unknown;
			constructor(type: string, options: CustomEventInit) {
				super(type, options);
				this.detail = options.detail;
			}
		}
		vi.stubGlobal('CustomEvent', LayoutEvent);
		try {
			const dispatchEvent = vi.fn();
			notifyChatLayout({ dispatchEvent } as unknown as Element, 300);
			const event = dispatchEvent.mock.calls[0][0];
			expect(event.type).toBe('neve:chat-layout');
			expect(event.bubbles).toBe(true);
			expect(event.detail).toEqual({ duration: 300 });
			notifyChatLayout({ dispatchEvent } as unknown as Element);
			expect(dispatchEvent.mock.calls[1][0].detail.duration).toBe(0);
		} finally {
			vi.unstubAllGlobals();
		}
	});

	it('does nothing after an element has been removed', () => {
		expect(() => notifyChatLayout(null)).not.toThrow();
		expect(() => notifyChatLayout(undefined)).not.toThrow();
	});
});
