import { afterEach, expect, it, vi } from 'vitest';
import { artifactPanelActive } from '$lib/stores';
import { observeArtifactPanel } from './activity';

vi.mock('$lib/stores', () => ({ artifactPanelActive: { set: vi.fn() } }));
afterEach(() => { vi.unstubAllGlobals(); });

it('keeps the new panel active when an old drawer finishes closing and pauses while hidden', () => {
	const callbacks: IntersectionObserverCallback[] = [];
	const listeners = new Set<() => void>();
	let visibility = 'visible';
	vi.stubGlobal('document', {
		get visibilityState() {
			return visibility;
		},
		addEventListener: (_: string, listener: () => void) => listeners.add(listener),
		removeEventListener: (_: string, listener: () => void) => listeners.delete(listener)
	});
	vi.stubGlobal(
		'IntersectionObserver',
		class {
			constructor(callback: IntersectionObserverCallback) {
				callbacks.push(callback);
			}
			observe() {}
			disconnect() {}
		}
	);
	const oldPanel = observeArtifactPanel({} as HTMLElement);
	const newPanel = observeArtifactPanel({} as HTMLElement);
	const visible = [
		{ isIntersecting: true, intersectionRect: { width: 400, height: 800 } }
	] as IntersectionObserverEntry[];
	callbacks[1](
		[
			{ isIntersecting: false, intersectionRect: { width: 0, height: 0 } },
			...visible
		] as IntersectionObserverEntry[],
		{} as IntersectionObserver
	);
	expect(artifactPanelActive.set).toHaveBeenLastCalledWith(true);
	oldPanel.destroy();
	expect(artifactPanelActive.set).toHaveBeenLastCalledWith(true);
	callbacks[0](visible, {} as IntersectionObserver);
	visibility = 'hidden';
	listeners.forEach((listener) => listener());
	expect(artifactPanelActive.set).toHaveBeenLastCalledWith(false);
	visibility = 'visible';
	listeners.forEach((listener) => listener());
	expect(artifactPanelActive.set).toHaveBeenLastCalledWith(true);
	newPanel.destroy();
	expect(artifactPanelActive.set).toHaveBeenLastCalledWith(false);
	expect(listeners.size).toBe(0);
});
