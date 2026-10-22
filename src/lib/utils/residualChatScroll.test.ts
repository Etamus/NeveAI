import { afterEach, describe, expect, it, vi } from 'vitest';
import { RESIDUAL_CHAT_SCROLL_ATTRIBUTE as attribute, stabilizeResidualChatScroll } from './residualChatScroll';

const setup = (overflow = 1, enabled = true) => {
	const attributes = new Set<string>();
	const viewport = {
		scrollHeight: 952 + overflow, clientHeight: 952, scrollTop: 1,
		firstElementChild: {},
		hasAttribute: (name: string) => attributes.has(name),
		toggleAttribute: (name: string, value: boolean) => value ? attributes.add(name) : attributes.delete(name),
		removeAttribute: (name: string) => attributes.delete(name)
	};
	let resized = () => {}, changed = () => {};
	const disconnectResize = vi.fn(), disconnectMutation = vi.fn(), observeResize = vi.fn();
	vi.stubGlobal('ResizeObserver', class {
		constructor(callback: () => void) { resized = callback; }
		observe = observeResize; disconnect = disconnectResize;
	});
	vi.stubGlobal('MutationObserver', class {
		constructor(callback: () => void) { changed = callback; }
		observe = vi.fn(); disconnect = disconnectMutation;
	});
	const action = stabilizeResidualChatScroll(viewport as unknown as HTMLElement, enabled);
	return {viewport, attributes, action, resize: () => resized(), mutate: () => changed(), disconnectResize, disconnectMutation, observeResize};
};
afterEach(() => vi.unstubAllGlobals());

describe('idle residual chat scrolling', () => {
	it('observes the wrapper border box so composer padding changes release the lock', () => {
		const test = setup();
		expect(test.observeResize).toHaveBeenCalledWith(test.viewport.firstElementChild, {box: 'border-box'});
	});
	it('suppresses exactly one pixel without changing position or geometry', () => {
		const {viewport, attributes} = setup();
		expect(attributes.has(attribute)).toBe(true);
		expect(viewport.scrollTop).toBe(1);
		expect(viewport.scrollHeight).toBe(953);
	});
	it.each([0, -1, 2, 100])('does not suppress a %s pixel overflow', (overflow) => {
		expect(setup(overflow).attributes.has(attribute)).toBe(false);
	});
	it('never suppresses while generation, spacer, or accordion handling disables it', () => {
		const test = setup(1, false);
		expect(test.attributes.has(attribute)).toBe(false);
		test.action.update(true); expect(test.attributes.has(attribute)).toBe(true);
		test.action.update(false); expect(test.attributes.has(attribute)).toBe(false);
	});
	it('restores native scrolling as soon as the viewport or content grows', () => {
		const test = setup();
		test.viewport.scrollHeight += 20; test.resize();
		expect(test.attributes.has(attribute)).toBe(false);
		test.viewport.clientHeight += 20; test.resize();
		expect(test.attributes.has(attribute)).toBe(true);
	});
	it('does not interfere with the history loading lock', () => {
		const test = setup();
		test.attributes.add('data-history-loading'); test.mutate();
		expect(test.attributes.has(attribute)).toBe(false);
		test.attributes.delete('data-history-loading'); test.mutate();
		expect(test.attributes.has(attribute)).toBe(true);
	});
	it('cleans up observers and ignores callbacks queued before destruction', () => {
		const test = setup(); test.action.destroy(); test.resize(); test.mutate();
		expect(test.attributes.has(attribute)).toBe(false);
		expect(test.disconnectResize).toHaveBeenCalledOnce();
		expect(test.disconnectMutation).toHaveBeenCalledOnce();
	});
});
