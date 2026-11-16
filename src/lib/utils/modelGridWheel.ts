// Discrete wheel ticks advance whole rows; touch and fine trackpad input stay native.
export function modelGridWheel(node: HTMLElement) {
	const wheel = (event: WheelEvent) => {
		if (event.defaultPrevented || event.ctrlKey || event.shiftKey || !event.deltaY ||
			Math.abs(event.deltaX) > Math.abs(event.deltaY) ||
			(event.deltaMode === 0 && Math.abs(event.deltaY) < 50)) return;
		if (!['auto', 'scroll'].includes(getComputedStyle(node).overflowY)) return;
		const max = node.scrollHeight - node.clientHeight;
		if (max <= 0) return;
		const cards = node.querySelector('[data-model-grid]')?.children;
		if (!cards?.length) return;
		const first = cards[0].getBoundingClientRect().top;
		let step = 0;
		for (const card of Array.from(cards).slice(1)) {
			step = card.getBoundingClientRect().top - first;
			if (step > 1) break;
		}
		if (step <= 1) return;
		const row = node.scrollTop / step;
		const target = event.deltaY > 0
			? (Math.floor(row + 0.01) + 1) * step
			: (Math.ceil(row - 0.01) - 1) * step;
		event.preventDefault();
		node.scrollTop = Math.max(0, Math.min(max, target));
	};
	node.addEventListener('wheel', wheel, { passive: false });
	return { destroy() { node.removeEventListener('wheel', wheel); } };
}
