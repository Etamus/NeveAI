import { afterEach, describe, expect, it, vi } from 'vitest';
import { dismissTooltipsOnMediaScroll } from './mediaGenerationHover';

class Element extends EventTarget {
	parentElement: Element | null = null;
	_tippy: any;
	contains(element: Element): boolean {
		return element === this || Boolean(element.parentElement && this.contains(element.parentElement));
	}
}

const tooltip = (reference: Element) => {
	const state = { isEnabled: true, isDestroyed: false, isVisible: true, isMounted: true };
	const instance = {
		reference, state,
		disable: vi.fn(() => { state.isEnabled = false; state.isVisible = false; }),
		unmount: vi.fn(() => { state.isMounted = false; }),
		show: vi.fn(() => { state.isVisible = true; }),
		enable: vi.fn(() => { state.isEnabled = true; })
	};
	reference._tippy = instance;
	return instance;
};

const setup = (active = true) => {
	vi.stubGlobal('HTMLElement', Element);
	vi.stubGlobal('Element', Element);
	const poppers: Element[] = [];
	vi.stubGlobal('document', { querySelectorAll: () => poppers });
	const root = new Element();
	const reference = new Element(); reference.parentElement = root;
	const button = new Element(); button.parentElement = reference;
	const instance = tooltip(reference);
	const popper = new Element(); popper._tippy = instance; poppers.push(popper);
	const enabled = { value: active };
	const destroy = dismissTooltipsOnMediaScroll(root as any, () => enabled.value);
	const dispatch = (type: string, target: Element = root) => {
		const event = new Event(type);
		Object.defineProperty(event, 'target', { value: target });
		root.dispatchEvent(event);
	};
	return { root, reference, button, instance, poppers, enabled, dispatch, destroy };
};

afterEach(() => vi.unstubAllGlobals());

describe('tooltips while visual media is generating', () => {
	it('removes the floating tooltip and disables stale hover on scroll', () => {
		const test = setup(); test.dispatch('scroll');
		expect(test.instance.state).toMatchObject({ isEnabled: false, isVisible: false, isMounted: false });
		test.dispatch('scroll');
		expect(test.instance.disable).toHaveBeenCalledTimes(1);
		test.destroy();
	});
	it('also cancels a pending tooltip reached through the wheel target', () => {
		const test = setup(); test.poppers.length = 0;
		test.instance.state.isMounted = false;
		test.dispatch('wheel', test.button);
		expect(test.instance.disable).toHaveBeenCalledOnce();
		test.destroy();
	});
	it.each(['pointermove', 'pointerdown'])('restores controls on %s', (event) => {
		const test = setup(); test.dispatch('scroll'); test.dispatch(event);
		expect(test.instance.enable).toHaveBeenCalledOnce();
		test.destroy();
	});
	it('does not change ordinary chat behavior', () => {
		const test = setup(false); test.dispatch('wheel', test.button); test.dispatch('scroll');
		expect(test.instance.disable).not.toHaveBeenCalled();
		test.destroy();
	});
	it('can show the tooltip again when movement enters the restored reference', () => {
		const test = setup(); test.dispatch('scroll'); test.dispatch('pointermove', test.button);
		expect(test.instance.enable).toHaveBeenCalledOnce();
		expect(test.instance.show).toHaveBeenCalledOnce();
		test.destroy();
	});
	it('does not affect tooltips from outside this chat', () => {
		const test = setup();
		const outside = tooltip(new Element());
		const popper = new Element(); popper._tippy = outside; test.poppers.push(popper);
		test.dispatch('scroll');
		expect(outside.disable).not.toHaveBeenCalled();
		test.destroy();
	});
	it('restores a suppressed tooltip once the generation is no longer active', () => {
		const test = setup(); test.dispatch('scroll');
		test.enabled.value = false; test.dispatch('scroll');
		expect(test.instance.state.isEnabled).toBe(true);
		test.destroy();
	});
	it('cleans up listeners and tolerates a destroyed tooltip', () => {
		const test = setup(); test.dispatch('scroll');
		test.instance.state.isDestroyed = true; test.destroy();
		expect(test.instance.enable).not.toHaveBeenCalled();
		test.dispatch('wheel', test.button);
		expect(test.instance.disable).toHaveBeenCalledTimes(1);
	});
});
