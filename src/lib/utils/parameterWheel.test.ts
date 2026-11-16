import { afterEach, describe, expect, it, vi } from 'vitest';
import { parameterWheel } from './parameterWheel';

describe('Advanced parameter wheel', () => {
	afterEach(() => { vi.unstubAllGlobals(); });
	const setup = () => {
		let listener: Function = () => {};
		class TestElement { closest(): any { return null; } }
		vi.stubGlobal('Element', TestElement);
		vi.stubGlobal('getComputedStyle', () => ({ overflowY: 'auto' }));
		const root = {
			getBoundingClientRect: () => ({ top: 10 }),
			children: Array.from({ length: 24 }, (_, i) => ({ getBoundingClientRect: () => ({ top: 10 + i * 40, height: 34 }) }))
		};
		const node = { scrollTop: 100, scrollHeight: 1000, clientHeight: 300, querySelector: () => root,
			addEventListener: vi.fn((_name, fn) => listener = fn), removeEventListener: vi.fn() };
		const action = parameterWheel(node as unknown as HTMLElement);
		const wheel = (patch = {}) => {
			const event = { deltaX: 0, deltaY: 120, deltaMode: 0, ctrlKey: false, shiftKey: false, preventDefault: vi.fn(), ...patch };
			listener(event); return event;
		};
		return { node, root, action, wheel, TestElement };
	};
	it('aligns discrete input with actual parameter rows and clamps both ends', () => {
		const { node, wheel } = setup();
		expect(wheel().preventDefault).toHaveBeenCalled(); expect(node.scrollTop).toBe(120);
		wheel(); expect(node.scrollTop).toBe(160);
		node.scrollTop = 100; wheel({ deltaY: -120 }); expect(node.scrollTop).toBe(80);
		node.scrollTop = 690; wheel(); expect(node.scrollTop).toBe(700);
		node.scrollTop = 10; wheel({ deltaY: -120 }); expect(node.scrollTop).toBe(0);
	});
	it('uses actual offsets for variable-height rows', () => {
		const { node, root, wheel } = setup();
		root.children = [0, 34, 140, 180].map(top => ({ getBoundingClientRect: () => ({ top: top + 10, height: 34 }) }));
		wheel(); expect(node.scrollTop).toBe(140);
		wheel({ deltaY: -120 }); expect(node.scrollTop).toBe(34);
	});
	it.each([{ deltaY: 4 }, { deltaY: 0 }, { ctrlKey: true }, { shiftKey: true }, { deltaX: 150 }, { defaultPrevented: true }])('preserves native input %j', patch => {
		const { node, wheel } = setup(); expect(wheel(patch).preventDefault).not.toHaveBeenCalled(); expect(node.scrollTop).toBe(100);
	});
	it('preserves mobile, non-overflowing lists and nested textarea scrolling', () => {
		const { node, wheel, TestElement } = setup();
		node.scrollHeight = 300; expect(wheel().preventDefault).not.toHaveBeenCalled();
		node.scrollHeight = 1000;
		vi.stubGlobal('getComputedStyle', () => ({ overflowY: 'visible' })); expect(wheel().preventDefault).not.toHaveBeenCalled();
		vi.stubGlobal('getComputedStyle', () => ({ overflowY: 'auto' }));
		const target = new TestElement(); target.closest = () => ({ scrollHeight: 100, clientHeight: 50 });
		expect(wheel({ target }).preventDefault).not.toHaveBeenCalled();
	});
	it('cleans up its listener', () => {
		const { node, action } = setup(); action.destroy(); expect(node.removeEventListener).toHaveBeenCalledWith('wheel', expect.any(Function));
	});
});
