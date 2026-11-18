type Options = { detail?: boolean };

export function downloadGridScroll(node: HTMLElement, options: Options = {}) {
	let grids: HTMLElement[] = [];
	const originalPadding = node.style.paddingBottom;
	const rowPaddingProperty = '--download-grid-row-padding';
	const originalRowPadding = node.style.getPropertyValue(rowPaddingProperty);
	let addedPadding = 0;
	const cards = () => Array.from(node.querySelectorAll<HTMLElement>(options.detail
		? '[data-hf-file]' : '[data-catalog-model], [data-hf-repo]'));
	const headerHeight = () => options.detail ? 0 : Math.max(0,
		...Array.from(node.querySelectorAll<HTMLElement>('[data-catalog-section-heading]'))
			.map(heading => heading.getBoundingClientRect().height));
	const rowOffsets = () => {
		const top = node.getBoundingClientRect().top, header = headerHeight();
		return [...new Set(cards().map(card => card.getBoundingClientRect())
			.filter(rect => rect.height > 0).map(rect => Math.max(0, rect.top - top + node.scrollTop - header)))].sort((a, b) => a - b);
	};
	const clip = () => {
		const { top, bottom } = node.getBoundingClientRect();
		for (const grid of grids) {
			const bounds = Array.from(grid.children).map(card => card.getBoundingClientRect()).filter(rect => rect.height > 0);
			const partial = bounds.some(rect => rect.top < bottom - 0.5 && rect.bottom > bottom + 0.5);
			const complete = bounds.filter(rect => rect.bottom <= bottom + 0.5);
			const partialTop = options.detail && bounds.some(rect => rect.top < top - 0.5 && rect.bottom > top + 0.5);
			const firstBelowTop = bounds.find(rect => rect.top >= top - 0.5);
			const topInset = partialTop
				? firstBelowTop ? `${Math.max(0, firstBelowTop.top - grid.getBoundingClientRect().top)}px` : '100%'
				: '0';
			// Clip paint only: keep the expanded viewport and native scrollbar geometry.
			const bottomInset = partial
				? complete.length ? `${Math.max(0, grid.getBoundingClientRect().bottom - complete.at(-1)!.bottom)}px` : '100%'
				: '0';
			grid.style.clipPath = partial || partialTop ? `inset(${topInset} 0 ${bottomInset} 0)` : '';
		}
	};
	const refresh = () => {
		const next = Array.from(node.querySelectorAll<HTMLElement>(options.detail ? '[data-quantization-grid]' : '[data-download-grid], [data-hf-grid]'));
		for (const grid of grids) if (!next.includes(grid)) { resize.unobserve(grid); grid.style.clipPath = ''; }
		for (const grid of next) if (!grids.includes(grid)) resize.observe(grid);
		grids = next;
		const max = node.scrollHeight - node.clientHeight;
		const naturalMax = Math.max(0, max - addedPadding);
		const end = naturalMax > 0 ? rowOffsets().find(offset => offset >= naturalMax - 0.5) : undefined;
		// Align the native scroll limit with a row without changing the viewport height.
		const padding = end === undefined ? 0 : Math.max(0, Math.round(end) - naturalMax);
		if (padding !== addedPadding) {
			const pinnedToEnd = options.detail && max > 0 && node.scrollTop >= max - 0.5;
			addedPadding = padding;
			if (options.detail) node.style.setProperty(rowPaddingProperty, `${padding}px`);
			else node.style.paddingBottom = padding ? `${padding}px` : originalPadding;
			if (pinnedToEnd) node.scrollTop = node.scrollHeight - node.clientHeight;
		}
		clip();
	};
	const wheel = (event: WheelEvent) => {
		if (event.defaultPrevented || event.ctrlKey || event.shiftKey || !event.deltaY ||
			Math.abs(event.deltaX) > Math.abs(event.deltaY) ||
			(event.deltaMode === 0 && Math.abs(event.deltaY) < 50) ||
			!['auto', 'scroll'].includes(getComputedStyle(node).overflowY)) return;
		const max = node.scrollHeight - node.clientHeight;
		if (max <= 0) return;
		const stops = [...new Set([0, max, ...rowOffsets().map(offset => Math.min(max, offset))])].sort((a, b) => a - b);
		const target = event.deltaY > 0
			? stops.find(stop => stop > node.scrollTop + 1) ?? max
			: stops.slice().reverse().find(stop => stop < node.scrollTop - 1) ?? 0;
		event.preventDefault();
		node.scrollTop = target;
		clip();
	};
	const resize = new ResizeObserver(refresh);
	const mutation = new MutationObserver(refresh);
	resize.observe(node);
	mutation.observe(node, { childList: true, subtree: true });
	node.addEventListener('scroll', clip, { passive: true });
	node.addEventListener('wheel', wheel, { passive: false });
	refresh();
	return { destroy() {
		resize.disconnect(); mutation.disconnect();
		node.removeEventListener('scroll', clip); node.removeEventListener('wheel', wheel);
		for (const grid of grids) grid.style.clipPath = '';
		node.style.paddingBottom = originalPadding;
		if (originalRowPadding) node.style.setProperty(rowPaddingProperty, originalRowPadding);
		else node.style.removeProperty(rowPaddingProperty);
	} };
}
