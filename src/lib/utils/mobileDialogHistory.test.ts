import { describe, expect, it, vi } from 'vitest';
import { createMobileDialogHistory } from './mobileDialogHistory';

function setup() {
	const history: (string | undefined)[] = [undefined];
	let index = 0;
	const back = vi.fn();
	const manager = createMobileDialogHistory({
		push: id => { history.splice(++index); history.push(id); }, back, current: () => history[index]
	});
	return { manager, back, current: () => history[index],
		navigate() { history.splice(++index); history.push(undefined); },
		pop() { index--; manager.synchronize(history[index]); } };
}

describe('Mobile dialog shallow navigation', () => {
	it('closing after a real route navigation does not undo the destination', () => {
		const s = setup(), release = s.manager.open(vi.fn()); s.navigate(); release();
		expect(s.back).not.toHaveBeenCalled(); expect(s.current()).toBeUndefined();
	});
	it('Back closes a dialog without another navigation', () => {
		const s = setup(), close = vi.fn(); s.manager.open(close);
		s.pop(); expect(close).toHaveBeenCalledOnce(); expect(s.back).not.toHaveBeenCalled();
	});
	it('nested dialogs close from the top down', () => {
		const s = setup(), parent = vi.fn(), child = vi.fn();
		s.manager.open(parent); s.manager.open(child);
		s.pop(); expect(child).toHaveBeenCalledOnce(); expect(parent).not.toHaveBeenCalled();
		s.pop(); expect(parent).toHaveBeenCalledOnce();
	});
	it('a settings detail returns to the index before closing settings', () => {
		const s = setup(), index = vi.fn(), detail = vi.fn();
		s.manager.open(index); s.manager.open(detail); s.pop();
		expect(detail).toHaveBeenCalledOnce(); expect(index).not.toHaveBeenCalled();
		s.pop(); expect(index).toHaveBeenCalledOnce();
	});
	it('programmatic close consumes its entry once, without invoking Back callbacks', () => {
		const s = setup(), close = vi.fn(), release = s.manager.open(close);
		release(); release(); expect(s.back).toHaveBeenCalledOnce();
		s.pop(); expect(close).not.toHaveBeenCalled(); expect(s.current()).toBeUndefined();
	});
	it('waits for a pending Back before opening a replacement', () => {
		const s = setup(), replacement = vi.fn(), release = s.manager.open(vi.fn());
		const first = s.current(); release(); s.manager.open(replacement);
		expect(s.current()).toBe(first); s.manager.synchronize(first);
		expect(s.back).toHaveBeenCalledOnce(); s.pop();
		expect(s.current()).not.toBe(first); expect(s.current()).toBeDefined();
		expect(replacement).not.toHaveBeenCalled(); s.pop(); expect(replacement).toHaveBeenCalledOnce();
	});
	it('closing both levels does not leave a ghost parent entry', () => {
		const s = setup(), parent = vi.fn(), child = vi.fn();
		const a = s.manager.open(parent), b = s.manager.open(child); b(); a();
		s.pop(); expect(s.back).toHaveBeenCalledTimes(2); s.pop();
		expect(s.current()).toBeUndefined(); expect(parent).not.toHaveBeenCalled(); expect(child).not.toHaveBeenCalled();
	});
	it('does not activate an overlay which was cancelled while queued', () => {
		const s = setup(), release = s.manager.open(vi.fn()); release();
		const close = vi.fn(), cancel = s.manager.open(close); cancel(); s.pop();
		expect(s.current()).toBeUndefined(); expect(close).not.toHaveBeenCalled();
	});
});
