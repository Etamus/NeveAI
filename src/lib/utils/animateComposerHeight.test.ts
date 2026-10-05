import { afterEach, describe, expect, it, vi } from 'vitest';
import { tick } from 'svelte';
import { animateComposerHeight } from './animateComposerHeight';

afterEach(() => { vi.unstubAllGlobals(); });

function setup(reduced = false) {
	vi.stubGlobal('window', { matchMedia: () => ({ matches: reduced }) });
	const listeners = new Map<string, (event: unknown) => void>();
	vi.stubGlobal('document', {
		addEventListener: (type: string, callback: (event: unknown) => void) => listeners.set(type, callback),
		removeEventListener: vi.fn()
	});
	let height = 52;
	const animation = { cancel: vi.fn(), onfinish: null };
	const node = {
		getBoundingClientRect: () => ({ height }),
		animate: vi.fn(() => animation),
		closest: () => null,
		contains: () => true,
		classList: { add: vi.fn(), remove: vi.fn() }
	} as unknown as HTMLElement;
	return { node, animation, resize: (value: number) => { height = value; }, interact: () => listeners.get('pointerdown')?.({ target: {} }) };
}

const layout = (key: string, context = 'chat-1') => ({ key, context });

describe('composer height animation', () => {
	it.each([true, false])('reserves additional reading space only for expanded ongoing composers (expanded %s)', async (expanded) => {
		const { node } = setup();
		let observeResize: () => void;
		vi.stubGlobal('ResizeObserver', class {
			constructor(callback: () => void) { observeResize = callback; }
			observe() {}
			disconnect() {}
		});
		let reservation = '';
		const root = { dataset: { ongoing: 'true' }, getBoundingClientRect: () => ({ height: 64 }) };
		const pane = { style: { setProperty: (_key: string, value: string) => { reservation = value; } } };
		vi.spyOn(node, 'closest').mockImplementation((selector) => (selector === '#chat-pane' ? pane : root) as unknown as HTMLElement);
		Object.assign(node.classList, { contains: (name: string) => name === 'flex-col' && expanded });
		const action = animateComposerHeight(node, layout('initial'));
		await tick();
		observeResize!();
		expect(reservation).toBe(expanded ? '88px' : '72px');
		action.destroy();
	});
	it('measures the centered editor in its animated row so the placeholder ends in its native position', async () => {
		const { node, resize, interact } = setup();
		resize(108);
		let top = 100;
		const part = { getBoundingClientRect: () => ({ left: 40, top }), animate: vi.fn(() => ({ cancel: vi.fn() })) };
		Object.assign(node, { querySelector: (selector: string) => selector === '#chat-input' ? part : null });
		vi.spyOn(node, 'closest').mockImplementation((selector) => selector === '#chat-pane' ? null : { dataset: { ongoing: 'true' } } as unknown as HTMLElement);
		const action = animateComposerHeight(node, layout('expanded'));
		await tick();
		interact();
		top = 101;
		vi.spyOn(node, 'animate').mockImplementation(() => { top = 130; return { cancel: vi.fn(), onfinish: null } as unknown as Animation; });
		resize(52);
		await action.update(layout('compact'));
		expect(part.animate).toHaveBeenCalledWith([
			{ transform: 'translate(0px, -30px)' }, { transform: 'translate(0px, 0px)' }
		], expect.anything());
		action.destroy();
	});
	it('measures token controls in final layout, not the animated container height in ongoing chats', async () => {
		const { node, resize, interact } = setup();
		resize(108);
		let top = 100;
		const part = { getBoundingClientRect: () => ({ left: 40, top }), animate: vi.fn(() => ({ cancel: vi.fn() })) };
		Object.assign(node, { querySelector: (selector: string) => selector === '[data-token-usage-trigger]' ? part : null });
		vi.spyOn(node, 'closest').mockImplementation((selector) => selector === '#chat-pane' ? null : { dataset: { ongoing: 'true' } } as unknown as HTMLElement);
		const action = animateComposerHeight(node, layout('expanded'));
		await tick();
		interact();
		top = 101;
		vi.spyOn(node, 'animate').mockImplementation(() => { top = 130; return { cancel: vi.fn(), onfinish: null } as unknown as Animation; });
		resize(52);
		await action.update(layout('compact'));
		expect(part.animate).toHaveBeenCalledWith([
			{ transform: 'translate(0px, -1px)' }, { transform: 'translate(0px, 0px)' }
		], expect.anything());
		action.destroy();
	});
	it('keeps compact controls at their previous position during contraction and clears transforms at the end', async () => {
		const { node, animation, resize, interact } = setup();
		resize(108);
		let position = { left: 40, top: 100 };
		const partAnimation = { cancel: vi.fn() };
		const part = { getBoundingClientRect: () => position, animate: vi.fn(() => partAnimation) };
		Object.assign(node, { querySelector: (selector: string) => selector === '#chat-input' ? part : null });
		const action = animateComposerHeight(node, layout('expanded'));
		await tick();
		interact();
		position = { left: 56, top: 130 };
		resize(52);
		await action.update(layout('compact'));
		expect(part.animate).toHaveBeenCalledWith([
			{ transform: 'translate(-16px, -30px)' },
			{ transform: 'translate(0px, 0px)' }
		], expect.objectContaining({ fill: 'both', duration: 260 }));
		(animation.onfinish as unknown as () => void)();
		expect(partAnimation.cancel).toHaveBeenCalledOnce();
		action.destroy();
	});

	it.each([0, 250])('preserves bottom breathing room only when already at the end (distance %s)', async (distance) => {
		const { node, animation, resize, interact } = setup();
		let observeResize: () => void;
		vi.stubGlobal('ResizeObserver', class {
			constructor(callback: () => void) { observeResize = callback; }
			observe() {}
			disconnect() {}
		});
		let reservation = '60px';
		const messages = {
			scrollHeight: 1000, clientHeight: 500, scrollTop: 500 - distance,
			querySelectorAll: () => [{ getBoundingClientRect: () => ({ bottom: 300 }) }]
		};
		const root = { dataset: { ongoing: 'true' }, getBoundingClientRect: () => node.getBoundingClientRect() };
		const pane = {
			querySelector: () => messages,
			style: { getPropertyValue: () => reservation, setProperty: (_key: string, value: string) => { reservation = value; } }
		};
		vi.spyOn(node, 'closest').mockImplementation((selector) => (selector === '#chat-pane' ? pane : root) as unknown as HTMLElement);
		const measure = node.getBoundingClientRect;
		vi.spyOn(node, 'getBoundingClientRect').mockImplementation(() => ({ ...measure(), top: 400 }) as DOMRect);
		const action = animateComposerHeight(node, layout('compact'));
		await tick();
		interact();
		resize(108);
		await action.update(layout('expanded'));
		expect(reservation).toBe(distance === 0 ? '60px' : '116px');
		(animation.onfinish as unknown as () => void)();
		expect(reservation).toBe(distance === 0 ? '60px' : '116px');
		observeResize!();
		expect(reservation).toBe(distance === 0 ? '60px' : '116px');
		resize(160);
		observeResize!();
		expect(reservation).toBe('168px');
		resize(52);
		await action.update(layout('compact'));
		expect(reservation).toBe('168px');
		action.destroy();
	});

	it('animates both expansion and contraction without retaining a fixed height', async () => {
		const { node, animation, resize, interact } = setup();
		const action = animateComposerHeight(node, layout('compact'));
		await tick();
		interact();
		resize(108);
		await action.update(layout('expanded'));
		expect(node.animate).toHaveBeenLastCalledWith([{ height: '52px' }, { height: '108px' }], expect.anything());
		(animation.onfinish as unknown as () => void)();
		resize(52);
		await action.update(layout('compact'));
		expect(node.animate).toHaveBeenLastCalledWith([{ height: '108px' }, { height: '52px' }], expect.anything());
		action.destroy();
		expect(animation.cancel).toHaveBeenCalled();
	});

	it('keeps a short layout transition when Windows disables client-area animations', async () => {
		const { node, resize, interact } = setup(true);
		const action = animateComposerHeight(node, layout('compact'));
		await tick();
		interact();
		resize(108);
		await action.update(layout('expanded'));
		expect(node.animate).toHaveBeenCalledWith(expect.anything(), expect.objectContaining({ duration: 120 }));
		action.destroy();
	});

	it('ignores stale updates and destroyed components', async () => {
		const { node, resize, interact } = setup();
		const action = animateComposerHeight(node, layout('compact'));
		await tick();
		interact();
		resize(108);
		const first = action.update(layout('expanded'));
		resize(52);
		const second = action.update(layout('compact'));
		await Promise.all([first, second]);
		expect(node.animate).not.toHaveBeenCalled();
		const last = action.update(layout('expanded'));
		action.destroy();
		await last;
		expect(node.animate).not.toHaveBeenCalled();
	});

	it('does not animate restored integrations or a different chat', async () => {
		const { node, resize, interact } = setup();
		const action = animateComposerHeight(node, layout('compact'));
		await tick();
		resize(108);
		await action.update(layout('expanded'));
		expect(node.animate).not.toHaveBeenCalled();
		interact();
		resize(52);
		await action.update(layout('compact', 'chat-2'));
		resize(108);
		await action.update(layout('expanded', 'chat-2'));
		expect(node.animate).not.toHaveBeenCalled();
		action.destroy();
	});
});
