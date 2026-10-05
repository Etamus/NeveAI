// Reflow once, then move the pane on the compositor instead of resizing text every frame.
export function animateSidebarPane(node: HTMLElement, expanded: boolean) {
	const setLayout = (open: boolean) => {
		node.style.marginLeft = open ? 'var(--sidebar-width, 260px)' : '0';
		node.style.width = open ? 'calc(100% - var(--sidebar-width, 260px))' : '100%';
	};
	setLayout(expanded);
	let state = expanded;
	let animation: Animation | undefined;
	const center = () => node.offsetLeft + node.offsetWidth / 2;
	let previousCenter = center();
	const observer = new ResizeObserver(() => { previousCenter = center(); });
	observer.observe(node);
	const cancel = () => { animation?.cancel(); animation = undefined; };
	window.addEventListener('resize', cancel);
	return {
		update(next: boolean) {
			const currentOffset = animation ? new DOMMatrixReadOnly(getComputedStyle(node).transform).m41 : 0;
			const currentCenter = previousCenter + currentOffset;
			cancel();
			// Own the layout change so Svelte cannot apply it after the FLIP measurement.
			setLayout(next);
			const target = center();
			const offset = currentCenter - target;
			if (next !== state && Math.abs(offset) > 0.5 && !window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
				animation = node.animate([
					{ transform: `translateX(${offset}px)` }, { transform: 'translateX(0)' }
				], { duration: 250, easing: 'cubic-bezier(0.22, 1, 0.36, 1)' });
			}
			state = next;
			previousCenter = target;
		},
		destroy() { cancel(); observer.disconnect(); window.removeEventListener('resize', cancel); }
	};
}
