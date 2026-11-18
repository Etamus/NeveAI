// Discrete wheel ticks advance whole rows; touch and fine trackpad input stay native.
export function modelGridWheel(node: HTMLElement) {
	const wheel = (event: WheelEvent) => {
		if (event.defaultPrevented || event.ctrlKey || event.shiftKey || !event.deltaY ||
			Math.abs(event.deltaX) > Math.abs(event.deltaY) ||
			(event.deltaMode === 0 && Math.abs(event.deltaY) < 50)) return;
		if (!['auto', 'scroll'].includes(getComputedStyle(node).overflowY)) return;
		const max = node.scrollHeight - node.clientHeight;
		if (max <= 0) return;
		const cards = (node.matches?.('[data-model-grid]') ? node : node.querySelector('[data-model-grid]'))?.children;
		if (!cards?.length) return;
		const first = cards[0].getBoundingClientRect().top;
		let step = 0;
		for (let i = 1; i < cards.length; i++) {
			step = cards[i].getBoundingClientRect().top - first;
			if (step > 1) break;
		}
		if (step <= 1) return;
		const position = node.scrollTop / step;
		const nearest = Math.round(position);
		// scrollTop may round to a CSS pixel while rem-based download rows are fractional.
		const row = node.matches?.('[data-download-queue]') && Math.abs(node.scrollTop - nearest * step) <= 1
			? nearest : position;
		const target = node.classList?.contains('files-list-scroll')
			? node.scrollTop + Math.sign(event.deltaY) * step
			: event.deltaY > 0
			? (Math.floor(row + 0.01) + 1) * step
			: (Math.ceil(row - 0.01) - 1) * step;
		event.preventDefault();
		node.scrollTop = Math.max(0, Math.min(max, target));
	};
	node.addEventListener('wheel', wheel, { passive: false });
	return { destroy() { node.removeEventListener('wheel', wheel); } };
}
