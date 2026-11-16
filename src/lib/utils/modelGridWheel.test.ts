import { afterEach, describe, expect, it, vi } from 'vitest';
import { modelGridWheel } from './modelGridWheel';

describe('Model grid wheel', () => {
	afterEach(() => { vi.unstubAllGlobals(); });
	const setup = () => {
		let listener: Function = () => {};
		const node = {
			scrollTop: 0, scrollHeight: 900, clientHeight: 300,
			querySelector: () => ({ children: [0, 0, 80, 80].map(top => ({ getBoundingClientRect: () => ({ top }) })) }),
			addEventListener: vi.fn((_name, fn) => listener = fn), removeEventListener: vi.fn()
		};
		vi.stubGlobal('getComputedStyle', () => ({ overflowY: 'auto' }));
		const action = modelGridWheel(node as unknown as HTMLElement);
		const wheel = (patch = {}) => {
			const event = { deltaX: 0, deltaY: 120, deltaMode: 0, ctrlKey: false, shiftKey: false, preventDefault: vi.fn(), ...patch };
			listener(event); return event;
		};
		return { node, action, wheel };
	};
	it('advances a full row and aligns partial positions in either direction', () => {
		const { node, wheel } = setup();
		expect(wheel().preventDefault).toHaveBeenCalled(); expect(node.scrollTop).toBe(80);
		node.scrollTop = 95; wheel(); expect(node.scrollTop).toBe(160);
		node.scrollTop = 95; wheel({ deltaY: -120 }); expect(node.scrollTop).toBe(80);
	});
	it('clamps both ends and exposes the last row', () => {
		const { node, wheel } = setup();
		node.scrollTop = 590; wheel(); expect(node.scrollTop).toBe(600);
		node.scrollTop = 10; wheel({ deltaY: -120 }); expect(node.scrollTop).toBe(0);
	});
	it.each([{ deltaY: 4 }, { deltaY: 0 }, { ctrlKey: true }, { shiftKey: true }, { deltaX: 180 }, { defaultPrevented: true }])('preserves native input %j', patch => {
		const { node, wheel } = setup(); expect(wheel(patch).preventDefault).not.toHaveBeenCalled(); expect(node.scrollTop).toBe(0);
	});
	it('does not intercept mobile or non-overflowing lists', () => {
		const { node, wheel, action } = setup();
		node.scrollHeight = 300; expect(wheel().preventDefault).not.toHaveBeenCalled();
		node.scrollHeight = 900; vi.stubGlobal('getComputedStyle', () => ({ overflowY: 'visible' }));
		expect(wheel().preventDefault).not.toHaveBeenCalled();
		action.destroy(); expect(node.removeEventListener).toHaveBeenCalledWith('wheel', expect.any(Function));
	});
});
