import { afterEach, describe, expect, it, vi } from 'vitest';
import { dismissChatDropdowns, onChatDropdownDismiss } from './chatDropdownDismissal';

describe('Chat dropdown dismissal before temporary-mode changes', () => {
	afterEach(() => vi.unstubAllGlobals());

	it('closes dropdown state before finishing its exit and resolves after the exit', async () => {
		vi.stubGlobal('requestAnimationFrame', (callback: () => void) => { callback(); return 1; });
		vi.stubGlobal('window', new EventTarget());
		const order: string[] = [];
		let finish!: () => void;
		const animation = {
			finished: new Promise<void>((resolve) => { finish = resolve; }),
			finish: vi.fn(() => { order.push('finish'); finish(); })
		};
		const panel = { getAnimations: () => [animation] };
		vi.stubGlobal('document', { querySelectorAll: vi.fn(() => [panel]) });
		const unsubscribe = onChatDropdownDismiss(() => order.push('close'));
		await dismissChatDropdowns();
		order.push('mode-change');
		expect(order).toEqual(['close', 'finish', 'mode-change']);
		expect(animation.finish).toHaveBeenCalledOnce();
		unsubscribe();
	});

	it('also works with no open menus or active transitions', async () => {
		vi.stubGlobal('requestAnimationFrame', (callback: () => void) => { callback(); return 1; });
		vi.stubGlobal('window', new EventTarget());
		vi.stubGlobal('document', { querySelectorAll: () => [] });
		const close = vi.fn();
		const unsubscribe = onChatDropdownDismiss(close);
		await dismissChatDropdowns();
		expect(close).toHaveBeenCalledOnce();
		unsubscribe();
	});

	it('does not retain listeners after their component unmounts', async () => {
		vi.stubGlobal('requestAnimationFrame', (callback: () => void) => { callback(); return 1; });
		vi.stubGlobal('window', new EventTarget());
		vi.stubGlobal('document', { querySelectorAll: () => [] });
		const close = vi.fn();
		onChatDropdownDismiss(close)();
		await dismissChatDropdowns();
		expect(close).not.toHaveBeenCalled();
	});
});
