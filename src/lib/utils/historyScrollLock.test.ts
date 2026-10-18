import { afterEach, describe, expect, it, vi } from 'vitest';
import { HISTORY_LAYOUT_EVENT, lockHistoryScroll, observeHistoryBoundary, waitForHistoryLayout } from './historyScrollLock';

class Viewport extends EventTarget {
	values = new Map<string, [string, string]>();
	attributes = new Map<string, string>();
	scrollHeight = 1000;
	scrollTop = 0;
	isConnected = true;
	style = {
		getPropertyValue: (name: string) => this.values.get(name)?.[0] ?? '',
		getPropertyPriority: (name: string) => this.values.get(name)?.[1] ?? '',
		setProperty: (name: string, value: string, priority = '') => { this.values.set(name, [value, priority]); },
		removeProperty: (name: string) => { this.values.delete(name); }
	};
	setAttribute(name: string, value: string) { this.attributes.set(name, value); }
	removeAttribute(name: string) { this.attributes.delete(name); }
	hasAttribute(name: string) { return this.attributes.has(name); }
	getBoundingClientRect() { return { top: 0, bottom: 800 }; }
}

afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

describe('history scroll lock', () => {
	it('compensates cold layout changes before paint and disconnects on release', () => {
		const viewport = new Viewport(); const content = {};
		(viewport as any).querySelector = () => content;
		let resize: () => void;
		const disconnect = vi.fn(); const observe = vi.fn();
		vi.stubGlobal('ResizeObserver', class {
			constructor(callback: () => void) { resize = callback; }
			observe = observe;
			disconnect = disconnect;
		});
		const align = vi.fn(); const lock = lockHistoryScroll(viewport as any, align);
		expect(observe).toHaveBeenCalledWith(content);
		resize!(); expect(align).toHaveBeenCalledOnce();
		lock.release(false); expect(disconnect).toHaveBeenCalledOnce();
	});
	it.each(['wheel', 'touchmove'])('blocks %s only until released', (type) => {
		const viewport = new Viewport();
		const lock = lockHistoryScroll(viewport as any, vi.fn());
		const event = new Event(type, { cancelable: true });
		viewport.dispatchEvent(event);
		expect(event.defaultPrevented).toBe(true);
		expect(viewport.style.getPropertyValue('overflow-y')).toBe('hidden');
		lock.release();
		const next = new Event(type, { cancelable: true });
		viewport.dispatchEvent(next);
		expect(next.defaultPrevented).toBe(false);
		expect(viewport.attributes.has('data-history-loading')).toBe(false);
	});
	it('restores inline styles and priorities exactly and releases once', () => {
		const viewport = new Viewport();
		viewport.style.setProperty('overflow-y', 'scroll', 'important');
		const align = vi.fn();
		const lock = lockHistoryScroll(viewport as any, align);
		lock.release(); lock.release();
		expect(align).toHaveBeenCalledOnce();
		expect(viewport.values.get('overflow-y')).toEqual(['scroll', 'important']);
		expect(viewport.values.has('scroll-behavior')).toBe(false);
	});
	it('cancellation does not move a newly opened chat', () => {
		const viewport = new Viewport(); const align = vi.fn();
		const lock = lockHistoryScroll(viewport as any, align);
		lock.release(false); lock.synchronize(); lock.release();
		expect(align).not.toHaveBeenCalled();
	});
	it('realigns attempted programmatic scroll and publishes the new baseline', () => {
		const viewport = new Viewport(); const align = vi.fn(); const baseline = vi.fn();
		viewport.addEventListener(HISTORY_LAYOUT_EVENT, baseline);
		const lock = lockHistoryScroll(viewport as any, align);
		viewport.dispatchEvent(new Event('scroll'));
		expect(align).toHaveBeenCalledOnce(); expect(baseline).toHaveBeenCalledOnce();
		lock.release(false);
	});
	it('blocks navigation keys without blocking editing or ordinary keys', () => {
		const viewport = new Viewport(); const lock = lockHistoryScroll(viewport as any, vi.fn());
		const key = (value: string, editing = false) => {
			const event = new Event('keydown', { cancelable: true });
			Object.defineProperties(event, { key: { value }, target: { value: { closest: () => editing } } });
			viewport.dispatchEvent(event); return event.defaultPrevented;
		};
		for (const value of ['ArrowUp', 'ArrowDown', 'PageUp', 'PageDown', 'Home', 'End', ' ']) expect(key(value)).toBe(true);
		expect(key('ArrowUp', true)).toBe(false); expect(key('a')).toBe(false);
		lock.release(false);
	});
});

describe('history boundary', () => {
	const setup = () => {
		const viewport = new Viewport();
		const bounds = { top: 40, bottom: 64 };
		const sentinel = { closest: () => viewport, getBoundingClientRect: () => bounds };
		const load = vi.fn(() => { viewport.setAttribute('data-history-loading', 'true'); });
		return { viewport, bounds, load, action: observeHistoryBoundary(sentinel as any, load) };
	};
	it('starts on the first scroll event, without the loader timer', () => {
		const test = setup(); test.viewport.dispatchEvent(new Event('scroll'));
		expect(test.load).toHaveBeenCalledOnce(); test.action.destroy!();
	});
	it('blocks an upward wheel already at the boundary before native scrolling', () => {
		const test = setup(); const event = new Event('wheel', { cancelable: true });
		Object.defineProperty(event, 'deltaY', { value: -80 });
		test.viewport.dispatchEvent(event);
		expect(event.defaultPrevented).toBe(true); expect(test.load).toHaveBeenCalledOnce(); test.action.destroy!();
	});
	it('does not load or prevent ordinary downward scrolling', () => {
		const test = setup(); const event = new Event('wheel', { cancelable: true });
		Object.defineProperty(event, 'deltaY', { value: 80 });
		test.viewport.dispatchEvent(event);
		expect(event.defaultPrevented).toBe(false); expect(test.load).not.toHaveBeenCalled(); test.action.destroy!();
	});
	it('waits for the actual top instead of blocking near it', () => {
		const test = setup(); test.viewport.scrollTop = 40;
		test.viewport.dispatchEvent(new Event('scroll')); expect(test.load).not.toHaveBeenCalled();
		test.viewport.scrollTop = 0; test.viewport.dispatchEvent(new Event('scroll'));
		expect(test.load).toHaveBeenCalledOnce(); test.action.destroy!();
	});
	it('ignores a distant or already passed sentinel and cleans up listeners', () => {
		const test = setup(); test.bounds.top = 1000; test.bounds.bottom = 1024;
		test.viewport.dispatchEvent(new Event('scroll'));
		test.bounds.top = -1000; test.bounds.bottom = -976;
		test.viewport.dispatchEvent(new Event('scroll')); expect(test.load).not.toHaveBeenCalled();
		test.action.destroy!(); test.bounds.top = 40; test.bounds.bottom = 64;
		test.viewport.dispatchEvent(new Event('scroll')); expect(test.load).not.toHaveBeenCalled();
	});
});

describe('history layout readiness', () => {
	const setup = () => {
		vi.useFakeTimers();
		vi.spyOn(performance, 'now').mockImplementation(() => Date.now());
		vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => setTimeout(() => callback(performance.now()), 16));
		vi.stubGlobal('cancelAnimationFrame', (id: any) => clearTimeout(id));
		return new Viewport();
	};
	it('waits for media readiness and consecutive stable frames', async () => {
		const viewport = setup(); let ready = false; const done = vi.fn(); const align = vi.fn();
		const promise = waitForHistoryLayout(viewport as any, align, () => ready, new AbortController().signal).then(done);
		await vi.advanceTimersByTimeAsync(100); expect(done).not.toHaveBeenCalled();
		ready = true; viewport.scrollHeight = 1200;
		await vi.advanceTimersByTimeAsync(96); await promise;
		expect(done).toHaveBeenCalledOnce(); expect(align).toHaveBeenCalled();
	});
	it('does not unlock while a cold webfont can still change wrapping', async () => {
		const viewport = setup(); const fonts = { status: 'loading' };
		(viewport as any).ownerDocument = { fonts };
		const done = vi.fn();
		const promise = waitForHistoryLayout(viewport as any, () => {}, () => true, new AbortController().signal).then(done);
		await vi.advanceTimersByTimeAsync(300); expect(done).not.toHaveBeenCalled();
		fonts.status = 'loaded'; await vi.advanceTimersByTimeAsync(64); await promise;
		expect(done).toHaveBeenCalledOnce();
	});
	it('keeps the indicator visible briefly even for an already cached batch', async () => {
		const viewport = setup(); const done = vi.fn();
		const promise = waitForHistoryLayout(viewport as any, () => {}, () => true, new AbortController().signal).then(done);
		await vi.advanceTimersByTimeAsync(100); expect(done).not.toHaveBeenCalled();
		await vi.advanceTimersByTimeAsync(100); await promise; expect(done).toHaveBeenCalledOnce();
	});
	it('cancels pending frames on navigation', async () => {
		const viewport = setup(); const controller = new AbortController(); const align = vi.fn();
		const promise = waitForHistoryLayout(viewport as any, align, () => false, controller.signal);
		controller.abort(); await promise; await vi.advanceTimersByTimeAsync(100);
		expect(align).not.toHaveBeenCalled(); expect(vi.getTimerCount()).toBe(0);
	});
	it('does not permanently lock on failed or stalled media', async () => {
		const viewport = setup(); const done = vi.fn();
		const promise = waitForHistoryLayout(viewport as any, () => {}, () => false, new AbortController().signal).then(done);
		await vi.advanceTimersByTimeAsync(5100); await promise;
		expect(done).toHaveBeenCalledOnce(); expect(vi.getTimerCount()).toBe(0);
	});
	it('finishes if the viewport is removed', async () => {
		const viewport = setup(); viewport.isConnected = false;
		await vi.advanceTimersByTimeAsync(0);
		const promise = waitForHistoryLayout(viewport as any, () => {}, () => false, new AbortController().signal);
		await vi.advanceTimersByTimeAsync(16); await promise;
		expect(vi.getTimerCount()).toBe(0);
	});
});
