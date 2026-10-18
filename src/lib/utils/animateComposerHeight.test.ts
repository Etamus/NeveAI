import { afterEach, describe, expect, it, vi } from 'vitest';
import { tick } from 'svelte';
import { animateComposerHeight, COMPOSER_READING_GAP, SYNC_COMPOSER_LAYOUT } from './animateComposerHeight';

afterEach(() => { vi.unstubAllGlobals(); });
const layout = (key: string, conversation = 'chat-1', model = 'a') => ({ key, context: `${conversation}:${model}`, conversation });

function setup({ height = 52, contentHeight = 900, distance = 0, ongoing = true, padding = height + 24, spacer = 0, virtualized = false } = {}) {
	let viewportHeight = 500;
	let width = 600;
	let top = 0;
	let reservation = padding;
	let tailHeight = 24;
	const writes: number[] = [];
	const documentListeners = new Map<string, EventListener>();
	const removeListener = vi.fn();
	vi.stubGlobal('document', {
		addEventListener: (name: string, listener: EventListener) => documentListeners.set(name, listener),
		removeEventListener: removeListener
	});
	let resize = () => {};
	const disconnect = vi.fn();
	vi.stubGlobal('ResizeObserver', class {
		constructor(callback: () => void) { resize = callback; }
		observe() {}
		unobserve() {}
		disconnect = disconnect;
	});
	vi.stubGlobal('getComputedStyle', () => ({ paddingBottom: '8px' }));
	const root = Object.assign(new EventTarget(), { dataset: { ongoing: String(ongoing), generating: 'false' } });
	const lastMessage = { getBoundingClientRect: () => ({ bottom: contentHeight - top }) };
	const content = {
		getBoundingClientRect: () => ({ bottom: contentHeight + tailHeight + spacer - top }),
		querySelector: () => spacer ? { getBoundingClientRect: () => ({ height: spacer }) } : null
	};
	const scrollEvents = new EventTarget();
	const messages = {
		get clientHeight() { return viewportHeight; },
		get scrollHeight() { return Math.max(viewportHeight, contentHeight + tailHeight + spacer + reservation + 8); },
		get scrollTop() { return top; },
		set scrollTop(value: number) { top = Math.max(0, Math.min(value, this.scrollHeight - viewportHeight)); },
		getBoundingClientRect: () => ({ bottom: viewportHeight }),
		querySelector: () => content,
		querySelectorAll: (selector: string) => !virtualized || selector.includes('[data-message-window]') ? [lastMessage] : [],
		addEventListener: scrollEvents.addEventListener.bind(scrollEvents),
		removeEventListener: scrollEvents.removeEventListener.bind(scrollEvents)
	};
	messages.scrollTop = messages.scrollHeight - viewportHeight - distance;
	const pane = Object.assign(new EventTarget(), {
		querySelector: () => messages,
		style: {
			getPropertyValue: () => `${reservation}px`,
			setProperty: (_name: string, value: string) => {
				reservation = parseFloat(value);
				writes.push(reservation);
				top = Math.min(top, messages.scrollHeight - viewportHeight);
			}
		}
	});
	const node = {
		closest: (selector: string) => selector === '#chat-pane' ? pane : root,
		getBoundingClientRect: () => ({ top: viewportHeight - 8 - height, height, width }),
		contains: () => true,
		animate: vi.fn()
	} as unknown as HTMLElement;
	return {
		node, root, pane, messages, writes, removeListener, disconnect,
		gap: () => node.getBoundingClientRect().top - lastMessage.getBoundingClientRect().bottom,
		padding: () => reservation,
		resize: (value: number) => { height = value; resize(); },
		setHeight: (value: number) => { height = value; },
		setTailHeight: (value: number) => { tailHeight = value; },
		setWidth: (value: number) => { width = value; resize(); },
		setViewport: (value: number) => { viewportHeight = value; resize(); },
		scroll: (value: number) => { messages.scrollTop = value; scrollEvents.dispatchEvent(new Event('scroll')); },
		interact: (name: string) => documentListeners.get(name)?.({ target: {} } as Event),
		observe: () => resize()
	};
}

describe('canonical composer spacing', () => {
	it.each([0, 180])('preserves the pre-attachment reading state at distance %s', async (distance) => {
		const s = setup({ distance });
		const action = animateComposerHeight(s.node, layout('compact'));
		await tick();
		const top = s.messages.scrollTop;
		for (const [key, height, tail] of [['attachment', 160, 48], ['removed', 52, 24]] as const) {
			s.setTailHeight(tail); s.setHeight(height);
			await action.update(layout(key));
			expect(s.padding()).toBe(height + COMPOSER_READING_GAP - tail);
			if (distance === 0) expect(s.gap()).toBe(COMPOSER_READING_GAP);
			else expect(s.messages.scrollTop).toBe(top);
		}
		action.destroy();
	});
	it.each([0, 160])('handles a virtualized image tail at reading distance %s', async (distance) => {
		const s = setup({ virtualized: true, contentHeight: 1500, distance });
		const action = animateComposerHeight(s.node, layout('compact'));
		await tick();
		const top = s.messages.scrollTop;
		for (const height of [108, 260, 52, 108, 52]) {
			s.resize(height);
			expect(s.padding()).toBe(height + COMPOSER_READING_GAP - 24);
			if (distance === 0) expect(s.gap()).toBe(COMPOSER_READING_GAP);
			else expect(s.messages.scrollTop).toBe(top);
		}
		action.destroy();
	});
	it('does not discard the completed generation breathing room when the composer receives input', async () => {
		const s = setup({ contentHeight: 200, spacer: 300 });
		const action = animateComposerHeight(s.node, layout('compact'));
		await tick();
		const top = s.messages.scrollTop;
		const gap = s.gap();
		for (const event of ['pointerdown', 'keydown', 'paste', 'beforeinput']) {
			s.interact(event);
			await action.update(layout(event));
			expect(s.messages.scrollTop).toBe(top);
			expect(s.gap()).toBe(gap);
		}
		action.destroy();
	});
	it.each([52, 108, 260])('keeps a fixed end gap at height %s without retaining previous heights', async (height) => {
		const s = setup();
		const action = animateComposerHeight(s.node, layout('compact'));
		await tick();
		s.resize(height);
		expect(s.gap()).toBe(COMPOSER_READING_GAP);
		expect(s.padding()).toBe(height + COMPOSER_READING_GAP - 24);
		s.resize(52);
		expect(s.gap()).toBe(COMPOSER_READING_GAP);
		expect(s.padding()).toBe(52 + COMPOSER_READING_GAP - 24);
		action.destroy();
	});
	it('handles content growth from ResizeObserver even if the compact/expanded key is unchanged', async () => {
		const s = setup();
		const action = animateComposerHeight(s.node, layout('expanded'));
		await tick();
		for (const height of [108, 130, 160, 200, 260, 200, 108, 52, 260, 52]) {
			s.resize(height);
			expect(s.gap()).toBe(COMPOSER_READING_GAP);
			expect(s.padding()).toBe(height + COMPOSER_READING_GAP - 24);
		}
		expect(s.node.animate).not.toHaveBeenCalled();
		action.destroy();
	});
	it.each(['pointerdown', 'keydown', 'paste', 'beforeinput'])('follows the end on %s without animations or retained blank space', async (event) => {
		const s = setup();
		const action = animateComposerHeight(s.node, layout('compact'));
		await tick();
		s.interact(event);
		s.setHeight(260);
		await action.update(layout('filled'));
		expect(s.gap()).toBe(COMPOSER_READING_GAP);
		s.setHeight(52);
		await action.update(layout('cleared'));
		expect(s.padding()).toBe(52 + COMPOSER_READING_GAP - 24);
		expect(s.gap()).toBe(COMPOSER_READING_GAP);
		expect(s.node.animate).not.toHaveBeenCalled();
		action.destroy();
	});
	it('preserves the reading position away from the end instead of following the composer', async () => {
		const s = setup({ distance: 180 });
		const action = animateComposerHeight(s.node, layout('compact'));
		await tick();
		const top = s.messages.scrollTop;
		s.resize(260);
		expect(s.messages.scrollTop).toBe(top);
		s.resize(52);
		expect(s.messages.scrollTop).toBe(top);
		s.scroll(s.messages.scrollHeight);
		s.resize(108);
		expect(s.gap()).toBe(COMPOSER_READING_GAP);
		action.destroy();
	});
	it('follows both growth and contraction across model and conversation changes', async () => {
		const s = setup();
		const action = animateComposerHeight(s.node, layout('compact'));
		await tick();
		for (const conversation of ['chat-1', 'chat-2', 'chat-1']) {
			for (const [key, height, model] of [['expanded', 108, 'a'], ['compact', 52, 'b']] as const) {
				s.setHeight(height);
				await action.update(layout(key, conversation, model));
				expect(s.gap()).toBe(COMPOSER_READING_GAP);
				expect(s.padding()).toBe(height + COMPOSER_READING_GAP - 24);
			}
		}
		action.destroy();
	});
	it('removes an oversized reservation left by an older layout on mount', async () => {
		const s = setup({ padding: 400 });
		const action = animateComposerHeight(s.node, layout('compact'));
		await tick();
		expect(s.padding()).toBe(52 + COMPOSER_READING_GAP - 24);
		expect(s.gap()).toBe(COMPOSER_READING_GAP);
		action.destroy();
	});
	it('keeps short completed conversations at the top with at least the reading gap', async () => {
		const s = setup({ contentHeight: 200 });
		const action = animateComposerHeight(s.node, layout('compact'));
		await tick();
		for (const height of [108, 260, 52, 260, 52]) {
			s.resize(height);
			expect(s.gap()).toBeGreaterThanOrEqual(COMPOSER_READING_GAP);
			expect(s.messages.scrollTop).toBe(s.messages.scrollHeight - s.messages.clientHeight);
			expect(s.messages.scrollTop + (s.node.getBoundingClientRect().top - s.gap())).toBe(200);
		}
		action.destroy();
	});
	it('does not bottom-align the first short exchange when generation finishes', async () => {
		const s = setup({ contentHeight: 140 });
		s.root.dataset.generating = 'true';
		const action = animateComposerHeight(s.node, layout('streaming'));
		await tick();
		const before = s.node.getBoundingClientRect().top - s.gap();
		s.root.dataset.generating = 'false';
		await action.update(layout('completed'));
		expect(s.node.getBoundingClientRect().top - s.gap()).toBe(before);
		expect(s.messages.scrollTop).toBe(0);
		expect(s.gap()).toBeGreaterThanOrEqual(COMPOSER_READING_GAP);
		action.destroy();
	});
	it('does not count the independent generation spacer as composer padding or override its anchor', async () => {
		const s = setup({ spacer: 500 });
		s.root.dataset.generating = 'true';
		const action = animateComposerHeight(s.node, layout('compact'));
		await tick();
		const top = s.messages.scrollTop;
		s.resize(260);
		expect(s.messages.scrollTop).toBe(top);
		expect(s.padding()).toBe(260 + COMPOSER_READING_GAP - 24);
		s.root.dispatchEvent(new Event(SYNC_COMPOSER_LAYOUT));
		expect(s.messages.scrollTop).toBe(top);
		action.destroy();
	});
	it('follows viewport changes without reflowing text through animation', async () => {
		const s = setup();
		const action = animateComposerHeight(s.node, layout('compact'));
		await tick();
		s.setViewport(420);
		expect(s.gap()).toBe(COMPOSER_READING_GAP);
		s.setWidth(320);
		expect(s.gap()).toBe(COMPOSER_READING_GAP);
		s.setViewport(700);
		expect(s.gap()).toBe(COMPOSER_READING_GAP);
		action.destroy();
	});
	it('does not rewrite padding for content-only revisions with unchanged geometry', async () => {
		const s = setup();
		const action = animateComposerHeight(s.node, layout('compact'));
		await tick();
		const writes = s.writes.length;
		for (let i = 0; i < 10; i++) await action.update(layout('text-' + i));
		expect(s.writes).toHaveLength(writes);
		action.destroy();
	});
	it('leaves the new-chat layout untouched', async () => {
		const s = setup({ ongoing: false });
		const action = animateComposerHeight(s.node, layout('initial'));
		await tick();
		s.resize(260);
		expect(s.writes).toHaveLength(0);
		action.destroy();
	});
	it('ignores stale updates and disconnects every listener on destruction', async () => {
		const s = setup();
		const action = animateComposerHeight(s.node, layout('compact'));
		await tick();
		s.setHeight(260);
		const pending = action.update(layout('expanded'));
		s.setHeight(52);
		const latest = action.update(layout('compact-again'));
		await Promise.all([pending, latest]);
		expect(s.padding()).toBe(52 + COMPOSER_READING_GAP - 24);
		const writes = s.writes.length;
		action.destroy();
		s.observe();
		s.root.dispatchEvent(new Event(SYNC_COMPOSER_LAYOUT));
		expect(s.writes).toHaveLength(writes);
		expect(s.disconnect).toHaveBeenCalledOnce();
		expect(s.removeListener).toHaveBeenCalledTimes(4);
	});
});
