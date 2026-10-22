import { describe, expect, it, vi } from 'vitest';
import { continuousSpinner } from './continuousSpinner';

describe('continuous loading animation', () => {
	it('keeps replacements on the same document clock without timers', () => {
		const first = { startTime: 125 };
		const second = { startTime: 450 };
		const node = (animation: any) => ({ getAnimations: () => [animation] }) as unknown as Element;
		continuousSpinner(node(first));
		continuousSpinner(node(second));
		expect(first.startTime).toBe(0);
		expect(second.startTime).toBe(0);
	});
	it('leaves idle icons alone and synchronizes when loading starts', () => {
		const animation = { startTime: 400 };
		const getAnimations = vi.fn(() => [animation]);
		const action = continuousSpinner({ getAnimations } as unknown as Element, false);
		expect(getAnimations).not.toHaveBeenCalled();
		action.update(true);
		expect(animation.startTime).toBe(0);
		action.update(false);
		expect(getAnimations).toHaveBeenCalledTimes(1);
	});
});
