import { afterEach, describe, expect, it, vi } from 'vitest';
import { downloadGridScroll } from './downloadGridScroll';

describe('Download catalog row scrolling', () => {
	afterEach(() => { vi.unstubAllGlobals(); });
	const setup = (detail = false, tops = [40, 40, 120, 120, 200, 200, 340, 340, 420, 420]) => {
		const listeners: Record<string, Function> = {};
		const resizes: Function[] = [];
		let contentHeight = 1000;
		const grid = { style: { clipPath: '' }, getBoundingClientRect: () => ({ top: 10 - node.scrollTop, bottom: 1000 - node.scrollTop }), get children() { return node.querySelectorAll('cards'); } };
		const node = {
			style: { paddingBottom: '', rowPadding: '',
				getPropertyValue() { return this.rowPadding; },
				setProperty(_name: string, value: string) { this.rowPadding = value; },
				removeProperty() { this.rowPadding = ''; }
			},
			scrollTop: 0, clientHeight: 300,
			get scrollHeight() { return Math.max(node.clientHeight, contentHeight + parseFloat(node.style.paddingBottom || '0') + parseFloat(node.style.rowPadding || '0')); },
			set scrollHeight(value: number) { contentHeight = value; },
			getBoundingClientRect: () => ({ top: 10, bottom: 310 }),
			querySelectorAll: (selector: string): any[] => selector.includes('heading')
				? [{ getBoundingClientRect: () => ({ height: 40 }) }]
				: selector.includes('grid]') ? [grid] : tops.map(top => ({
				getBoundingClientRect: () => ({ height: 72, top: top + 10 - node.scrollTop, bottom: top + 82 - node.scrollTop })
			})),
			querySelector: (selector: string) => selector.includes('heading')
				? { getBoundingClientRect: () => ({ height: 40 }) } : detail ? grid : null,
			addEventListener: (name: string, fn: Function) => listeners[name] = fn,
			removeEventListener: vi.fn()
		};
		const disconnect = vi.fn();
		vi.stubGlobal('ResizeObserver', class { constructor(callback: Function) { resizes.push(callback); } observe() {} unobserve() {} disconnect = disconnect; });
		vi.stubGlobal('MutationObserver', class { observe() {} disconnect = disconnect; });
		vi.stubGlobal('getComputedStyle', () => ({ overflowY: 'auto' }));
		const action = downloadGridScroll(node as unknown as HTMLElement, { detail });
		const wheel = (patch = {}) => {
			const event = { deltaX: 0, deltaY: 120, deltaMode: 0, preventDefault: vi.fn(), ...patch };
			listeners.wheel(event); return event;
		};
		return { node, wheel, action, disconnect, grid, listeners, resizes };
	};
	it('uses actual rows across the spacing between catalog sections', () => {
		const { node, wheel } = setup();
		wheel(); expect(node.scrollTop).toBe(80);
		wheel(); expect(node.scrollTop).toBe(160);
		wheel(); expect(node.scrollTop).toBe(300);
		wheel({ deltaY: -120 }); expect(node.scrollTop).toBe(160);
	});
	it('aligns arbitrary positions and keeps the final row accessible', () => {
		const { node, wheel } = setup();
		node.scrollTop = 95; wheel(); expect(node.scrollTop).toBe(160);
		node.scrollTop = 690; wheel(); expect(node.scrollTop).toBe(700);
		node.scrollTop = 1; wheel({ deltaY: -120 }); expect(node.scrollTop).toBe(0);
	});
	it.each([{ deltaY: 4 }, { deltaX: 200 }, { ctrlKey: true }, { shiftKey: true }, { defaultPrevented: true }])('preserves fine input, horizontal scroll and zoom %j', patch => {
		const { node, wheel } = setup();
		expect(wheel(patch).preventDefault).not.toHaveBeenCalled(); expect(node.scrollTop).toBe(0);
	});
	it('cleans up observers and listeners', () => {
		const { action, disconnect, node } = setup(); action.destroy();
		expect(disconnect).toHaveBeenCalledTimes(2);
		expect(node.removeEventListener).toHaveBeenCalledTimes(2);
	});
	it('clips only the partial bottom row without shrinking the viewport or scroll range', () => {
		const { node, grid, listeners, action } = setup(true);
		expect(grid.style.clipPath).toBe('');
		node.clientHeight = 240;
		node.getBoundingClientRect = () => ({ top: 10, bottom: 250 });
		listeners.scroll();
		expect(grid.style.clipPath).toBe('inset(0 0 798px 0)');
		expect(node.clientHeight).toBe(240); expect(node.scrollHeight).toBe(1000);
		action.destroy(); expect(grid.style.clipPath).toBe('');
	});
	it('aligns the native detail end with the same row origin as the top', () => {
		const { node, grid, listeners, action, resizes } = setup(true, Array.from({ length: 12 }, (_, i) => 80 * i));
		node.scrollHeight = 952;
		resizes[0]();
		node.scrollTop = node.scrollHeight - node.clientHeight;
		listeners.scroll();
		expect(grid.style.clipPath).toBe('');
		expect(node.scrollTop).toBe(720);
		expect(node.style.rowPadding).toBe('68px');
		resizes[0](); resizes[0]();
		expect(node.style.rowPadding).toBe('68px');
		expect(node.clientHeight).toBe(300);
		expect(node.style.paddingBottom).toBe('');
		node.scrollTop = 640;
		listeners.scroll();
		expect(grid.style.clipPath).toBe('inset(0 0 118px 0)');
		action.destroy();
		expect(grid.style.clipPath).toBe('');
		expect(node.style.rowPadding).toBe('');
	});
	it('keeps the detail end aligned after layout changes without moving readers above it', () => {
		const tops = Array.from({ length: 12 }, (_, i) => 80 * i);
		const { node, resizes } = setup(true, tops);
		node.scrollTop = node.scrollHeight - node.clientHeight;
		tops.forEach((_, index) => tops[index] = index * 82);
		resizes[0]();
		expect(node.scrollTop).toBe(738);
		expect(node.scrollTop).toBe(node.scrollHeight - node.clientHeight);
		node.scrollTop = 160;
		tops.forEach((_, index) => tops[index] = index * 84);
		resizes[0]();
		expect(node.scrollTop).toBe(160);
	});
	it('clips both edges on fractional scroll positions', () => {
		const { node, grid, listeners } = setup(true, Array.from({ length: 12 }, (_, i) => 80 * i));
		node.scrollTop = 650.25;
		node.getBoundingClientRect = () => ({ top: 10, bottom: 220 });
		listeners.scroll();
		expect(grid.style.clipPath).toBe('inset(720px 0 198px 0)');
	});
	it('keeps the final catalog stop on a row without a short clamped tick', () => {
		const { node, wheel, resizes, action } = setup(false, Array.from({ length: 12 }, (_, i) => 40 + 80 * i));
		expect(node.style.paddingBottom).toBe('20px');
		for (let i = 0; i < 12; i++) wheel();
		expect(node.scrollTop).toBe(720);
		expect(node.scrollTop).toBe(node.scrollHeight - node.clientHeight);
		resizes[0](); resizes[0]();
		expect(node.style.paddingBottom).toBe('20px');
		node.clientHeight = 320; resizes[0]();
		expect(node.style.paddingBottom).toBe('40px');
		action.destroy(); expect(node.style.paddingBottom).toBe('');
	});
	it('clips the partial bottom row in the main catalog as well as repository details', () => {
		const { node, grid, listeners } = setup();
		node.getBoundingClientRect = () => ({ top: 10, bottom: 250 });
		listeners.scroll(); expect(grid.style.clipPath).toBe('inset(0 0 798px 0)');
	});
});
