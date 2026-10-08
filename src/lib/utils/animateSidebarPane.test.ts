import { afterEach, describe, expect, it, vi } from 'vitest';
import { animateSidebarPane } from './animateSidebarPane';

afterEach(() => { vi.unstubAllGlobals(); });

function fixture(reduced = false) {
	const cancel = vi.fn();
	const animate = vi.fn((_frames: Keyframe[], _options: KeyframeAnimationOptions) => ({ cancel }));
	const node = { offsetLeft: 0, offsetWidth: 1200, style: {}, animate } as unknown as HTMLElement;
	const removeEventListener = vi.fn();
	vi.stubGlobal('window', { addEventListener: vi.fn(), removeEventListener, matchMedia: () => ({ matches: reduced }) });
	const disconnect = vi.fn();
	vi.stubGlobal('ResizeObserver', class { observe() {} disconnect = disconnect; });
	vi.stubGlobal('getComputedStyle', () => ({ transform: 'matrix(1, 0, 0, 1, 40, 0)' }));
	vi.stubGlobal('DOMMatrixReadOnly', class { m41 = 40; });
	const action = animateSidebarPane(node, false);
	const expand = () => { Object.assign(node, { offsetLeft: 260, offsetWidth: 940 }); action.update(true); };
	return { node, action, expand, animate, cancel, disconnect, removeEventListener };
}

describe('Sidebar pane animation', () => {
	it('only animates translation, without resizing or scaling text', () => {
		const f = fixture();
		expect(f.animate).not.toHaveBeenCalled();
		f.expand();
		expect(f.animate.mock.calls[0][0]).toEqual([{ transform: 'translateX(-130px)' }, { transform: 'translateX(0)' }]);
		f.action.destroy();
		expect(f.cancel).toHaveBeenCalledOnce();
		expect(f.disconnect).toHaveBeenCalledOnce();
		expect(f.removeEventListener).toHaveBeenCalledOnce();
	});
	it('does not animate ordinary resizes or restored initial state', () => {
		const f = fixture();
		Object.assign(f.node, { offsetWidth: 1100 }); f.action.update(false);
		expect(f.animate).not.toHaveBeenCalled(); f.action.destroy();
	});
	it('respects reduced motion', () => {
		const f = fixture(true); f.expand(); expect(f.animate).not.toHaveBeenCalled(); f.action.destroy();
	});
	it('applies the final width before measuring the animation endpoint', () => {
		const f = fixture();
		Object.defineProperties(f.node, {
			offsetLeft: { get: () => f.node.style.marginLeft === '0' ? 0 : 260 },
			offsetWidth: { get: () => f.node.style.width === '100%' ? 1200 : 940 }
		});
		f.action.update(true);
		expect(f.node.style.width).toBe('calc(100% - var(--sidebar-width, 276px))');
		expect(f.animate.mock.calls[0][0][0]).toEqual({ transform: 'translateX(-130px)' });
		f.action.destroy();
	});
	it('cancels and reverses a running transition from its current position', () => {
		const f = fixture(); f.expand(); Object.assign(f.node, { offsetLeft: 0, offsetWidth: 1200 }); f.action.update(false);
		expect(f.cancel).toHaveBeenCalledOnce();
		expect(f.animate.mock.calls[1][0][0]).toEqual({ transform: 'translateX(170px)' }); f.action.destroy();
	});
});
