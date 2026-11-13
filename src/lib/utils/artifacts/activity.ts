import { artifactPanelActive } from '$lib/stores';

const panels = new Map<HTMLElement, boolean>();
const publish = () =>
	artifactPanelActive.set(
		document.visibilityState === 'visible' && [...panels.values()].some(Boolean)
	);

export function observeArtifactPanel(node: HTMLElement) {
	let destroyed = false;
	panels.set(node, false);
	const observer = new IntersectionObserver((entries) => {
		if (destroyed) return;
		const entry = entries.at(-1);
		if (!entry) return;
		panels.set(
			node,
			entry.isIntersecting && entry.intersectionRect.width > 0 && entry.intersectionRect.height > 0
		);
		publish();
	});
	observer.observe(node);
	document.addEventListener('visibilitychange', publish);
	return {
		destroy() {
			destroyed = true;
			observer.disconnect();
			panels.delete(node);
			// A previous mobile drawer can finish its outro after the new panel mounts.
			if (!panels.size) document.removeEventListener('visibilitychange', publish);
			publish();
		}
	};
}
