import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

describe('streaming text paint-only fade', () => {
	let frames: Map<number, FrameRequestCallback>;
	let registry: Map<string, unknown>;
	let rules: Array<{ style: { color: string } }>;
	let child: { nodeType: number; textContent: string };
	let node: HTMLElement;
	let nextFrame: number;

	beforeEach(() => {
		vi.resetModules();
		frames = new Map(); registry = new Map(); rules = []; nextFrame = 0;
		child = { nodeType: 3, textContent: 'First' };
		node = { firstChild: child } as unknown as HTMLElement;
		const sheet = {
			cssRules: rules,
			insertRule() { rules.push({ style: { color: 'transparent' } }); return rules.length - 1; },
			deleteRule(index: number) { rules.splice(index, 1); }
		};
		vi.stubGlobal('CSS', { highlights: registry, supports: () => true });
		vi.stubGlobal('getComputedStyle', () => ({ color: 'rgb(240, 240, 240)' }));
		vi.stubGlobal('Highlight', class { constructor(public range: Range) {} });
		vi.stubGlobal('document', {
			createElement: () => ({ dataset: {}, sheet }), head: { appendChild: vi.fn() },
			createRange: () => ({
				setStart: vi.fn((node, offset) => { if (offset > node.textContent.length) throw Error('Invalid start'); }),
				setEnd: vi.fn((node, offset) => { if (offset > node.textContent.length) throw Error('Invalid end'); })
			})
		});
		vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => { frames.set(++nextFrame, callback); return nextFrame; });
		vi.stubGlobal('cancelAnimationFrame', (id: number) => frames.delete(id));
	});
	afterEach(() => { vi.unstubAllGlobals(); });
	const flush = async () => { await Promise.resolve(); await Promise.resolve(); };
	const create = async (done = false) => {
		const { streamingTextFade } = await import('./streamingTextFade');
		return streamingTextFade(node, { text: 'First', done });
	};
	it('has no animation or word nodes for completed history', async () => {
		const action = await create(true); await flush();
		expect(registry.size).toBe(0); expect(rules).toHaveLength(0); expect(frames.size).toBe(0);
		expect(node.firstChild).toBe(child); action.destroy!();
	});
	it('animates paint and removes both range and CSS rule at the end', async () => {
		const action = await create(); await flush();
		expect(registry.size).toBe(1); expect(rules).toHaveLength(1);
		const callbacks = [...frames.values()]; frames.clear(); callbacks.forEach(callback => callback(performance.now() + 200));
		expect(registry.size).toBe(0); expect(rules).toHaveLength(0); expect(frames.size).toBe(0);
		expect(node.firstChild).toBe(child); action.destroy!();
	});
	it('waits for DOM updates and restores ranges when text grows', async () => {
		const action = await create(); await flush();
		action.update!({ text: 'First second', done: false });
		child.textContent = 'First second'; await flush();
		expect(registry.size).toBe(2); expect(rules).toHaveLength(2);
		action.update!({ text: child.textContent, done: true }); await flush();
		expect(registry.size).toBe(0); expect(rules).toHaveLength(0); expect(frames.size).toBe(0); action.destroy!();
	});
	it('cleans up pending work when a message is removed', async () => {
		const action = await create(); action.destroy!(); await flush();
		expect(registry.size).toBe(0); expect(rules).toHaveLength(0); expect(frames.size).toBe(0);
	});
	it('cleans up an active animation on removal and rewrite', async () => {
		const action = await create(); await flush();
		child.textContent = 'Other'; action.update!({ text: 'Other', done: false }); await flush();
		expect(registry.size).toBe(1); expect(rules).toHaveLength(1);
		action.destroy!(); expect(registry.size).toBe(0); expect(rules).toHaveLength(0); expect(frames.size).toBe(0);
	});
	it('shows stable text without an animation on unsupported browsers', async () => {
		vi.stubGlobal('Highlight', undefined);
		const action = await create(); await flush();
		expect(registry.size).toBe(0); expect(frames.size).toBe(0); expect(node.firstChild).toBe(child);
		expect(action.update).toBeUndefined();
	});
	it('does not make already-visible text transparent after Markdown restructuring', async () => {
		const { streamingTextFade } = await import('./streamingTextFade');
		const paintContext = { suppress: true };
		const action = streamingTextFade(node, { text: 'First', done: false, paintContext });
		await flush(); expect(registry.size).toBe(0);
		paintContext.suppress = false;
		child.textContent += ' new';
		action.update!({ text: child.textContent, done: false, paintContext });
		await flush(); expect(registry.size).toBe(1);
		paintContext.suppress = true;
		action.update!({ text: child.textContent, done: false, paintContext });
		await flush(); expect(registry.size).toBe(0); action.destroy!();
	});
	it('falls back to stable text when a policy blocks the animation stylesheet', async () => {
		const remove = vi.fn();
		vi.stubGlobal('document', { createElement: () => ({ dataset: {}, sheet: null, remove }), head: { appendChild: vi.fn() } });
		const action = await create(); await flush();
		expect(remove).toHaveBeenCalledOnce(); expect(action.update).toBeUndefined();
		expect(registry.size).toBe(0); expect(frames.size).toBe(0);
	});

	it('keeps streamed text opaque while forcing downward scrolling, then resumes new-character fades', async () => {
		let now = 100;
		vi.spyOn(performance, 'now').mockImplementation(() => now);
		const listeners = new Map<string, (event: { deltaY: number; ctrlKey?: boolean }) => void>();
		const viewport = {
			addEventListener: vi.fn((name, handler) => listeners.set(name, handler)),
			removeEventListener: vi.fn((name) => listeners.delete(name))
		};
		(node as any).closest = () => viewport;
		const action = await create(); await flush();
		expect(registry.size).toBe(1);
		listeners.get('wheel')!({ deltaY: 180 });
		expect(registry.size).toBe(0); expect(frames.size).toBe(0);
		child.textContent = 'First second'; action.update!({ text: child.textContent, done: false }); await flush();
		expect(registry.size).toBe(0);
		action.destroy!();
		child.textContent = 'First';
		const replacement = await create(); await flush();
		expect(registry.size).toBe(0); // A newly parsed paragraph shares the current scroll gesture.
		now += 181;
		child.textContent += ' third'; replacement.update!({ text: child.textContent, done: false }); await flush();
		expect(registry.size).toBe(1);
		replacement.update!({ text: child.textContent, done: true }); await flush();
		expect(listeners.size).toBe(0); expect(registry.size).toBe(0); replacement.destroy!();
		vi.restoreAllMocks();
	});
});
