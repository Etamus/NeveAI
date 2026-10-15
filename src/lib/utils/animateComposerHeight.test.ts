import { afterEach, describe, expect, it, vi } from 'vitest';
import { tick } from 'svelte';
import { animateComposerHeight } from './animateComposerHeight';

afterEach(() => { vi.unstubAllGlobals(); });

function setup(ongoing = false, expanded = false, distance = 250) {
	const listeners = new Map<string, (event: unknown) => void>();
	const removeEventListener = vi.fn();
	vi.stubGlobal('document', {
		addEventListener: (type: string, callback: (event: unknown) => void) => listeners.set(type, callback),
		removeEventListener
	});
	let height = 52;
	let reservation = '60px';
	let observeResize: () => void = () => {};
	vi.stubGlobal('ResizeObserver', class {
		constructor(callback: () => void) { observeResize = callback; }
		observe() {}
		disconnect = vi.fn();
	});
	const leaf = { animate: vi.fn() };
	const root = { dataset: { ongoing: String(ongoing) }, getBoundingClientRect: () => ({ height }) };
	const messages = {
		scrollHeight: 1000, clientHeight: 500, scrollTop: 500 - distance,
		querySelectorAll: () => [{ getBoundingClientRect: () => ({ bottom: 300 }) }]
	};
	const pane = {
		querySelector: () => messages,
		style: { getPropertyValue: () => reservation, setProperty: (_key: string, value: string) => { reservation = value; } }
	};
	const node = {
		getBoundingClientRect: () => ({ height, top: 400 }),
		animate: vi.fn(),
		querySelector: () => leaf,
		closest: (selector: string) => selector === '#chat-pane' ? pane : root,
		contains: () => true,
		classList: { add: vi.fn(), remove: vi.fn(), contains: () => expanded }
	} as unknown as HTMLElement;
	return {
		node, leaf, removeEventListener,
		resize: (value: number) => { height = value; },
		interact: (type = 'pointerdown') => listeners.get(type)?.({ target: {} }),
		observe: () => observeResize(),
		reservation: () => reservation
	};
}

const layout = (key: string, context = 'chat-1', conversation = context) => ({ key, context, conversation });

describe('immediate composer layout', () => {
	it.each(['pointerdown', 'keydown', 'paste', 'beforeinput'])('never animates the composer, text or controls after %s', async (event) => {
		const s = setup();
		const action = animateComposerHeight(s.node, layout('compact'));
		await tick();
		s.interact(event);
		for (const [key, height] of [['expanded', 108], ['larger', 200], ['compact', 52]] as const) {
			s.resize(height);
			await action.update(layout(key));
		}
		expect(s.node.animate).not.toHaveBeenCalled();
		expect(s.leaf.animate).not.toHaveBeenCalled();
		expect(s.node.classList.add).not.toHaveBeenCalled();
		action.destroy();
	});

	it.each([true, false])('preserves reading space across model changes (immediate %s)', async (immediate) => {
		const s = setup(true);
		s.resize(108);
		const action = animateComposerHeight(s.node, layout('expanded', 'chat-1:a', 'chat-1'));
		await tick();
		s.observe();
		const before = s.reservation();
		s.interact();
		if (immediate) s.resize(52);
		await action.update(layout(immediate ? 'compact' : 'expanded', 'chat-1:b', 'chat-1'));
		s.resize(52);
		await action.update(layout('compact', 'chat-1:b', 'chat-1'));
		s.observe();
		expect(s.reservation()).toBe(before);
		await action.update(layout('compact', 'chat-2:b', 'chat-2'));
		expect(s.reservation()).toBe('60px');
		action.destroy();
	});

	it.each([true, false])('retains the correct expanded/compact reading gap (expanded %s)', async (expanded) => {
		const s = setup(true, expanded);
		const action = animateComposerHeight(s.node, layout('initial'));
		await tick();
		s.observe();
		expect(s.reservation()).toBe(expanded ? '76px' : '60px');
		action.destroy();
	});

	it.each([0, 250])('reuses bottom breathing room only at the end (distance %s)', async (distance) => {
		const s = setup(true, false, distance);
		const action = animateComposerHeight(s.node, layout('compact'));
		await tick();
		s.interact();
		s.resize(108);
		await action.update(layout('expanded'));
		expect(s.reservation()).toBe(distance === 0 ? '60px' : '116px');
		s.observe();
		expect(s.reservation()).toBe(distance === 0 ? '60px' : '116px');
		s.resize(160);
		s.observe();
		expect(s.reservation()).toBe('168px');
		s.resize(52);
		await action.update(layout('compact'));
		expect(s.reservation()).toBe('168px');
		action.destroy();
	});

	it('ignores stale updates and destroyed components', async () => {
		const s = setup(true);
		const action = animateComposerHeight(s.node, layout('compact'));
		await tick();
		s.interact();
		s.resize(108);
		const first = action.update(layout('expanded'));
		s.resize(52);
		const second = action.update(layout('compact'));
		await Promise.all([first, second]);
		expect(s.reservation()).toBe('60px');
		const last = action.update(layout('expanded'));
		action.destroy();
		await last;
		expect(s.reservation()).toBe('60px');
		expect(s.removeEventListener).toHaveBeenCalledTimes(4);
	});
});
