export function parameterWheel(node: HTMLElement) {
	const wheel = (event: WheelEvent) => {
		if (event.defaultPrevented || event.ctrlKey || event.shiftKey || !event.deltaY || Math.abs(event.deltaX) > Math.abs(event.deltaY)) return;
		if (event.deltaMode === 0 && Math.abs(event.deltaY) < 50) return;
		if (!['auto', 'scroll'].includes(getComputedStyle(node).overflowY)) return;
		if (node.scrollHeight <= node.clientHeight) return;
		// Preserve native scrolling inside an expanded system-prompt textarea.
		if (event.target instanceof Element) {
			const field = event.target.closest('textarea');
			if (field && field.scrollHeight > field.clientHeight) return;
		}
		const root = node.querySelector('.advanced-params');
		if (!root) return;
		const top = root.getBoundingClientRect().top;
		const rows = Array.from(root.children)
			.filter(row => row.getBoundingClientRect().height > 0)
			.map(row => row.getBoundingClientRect().top - top);
		if (!rows.length) return;
		const max = node.scrollHeight - node.clientHeight;
		const target = event.deltaY > 0
			? rows.find(offset => offset > node.scrollTop + 0.5) ?? max
			: rows.reverse().find(offset => offset < node.scrollTop - 0.5) ?? 0;
		event.preventDefault();
		node.scrollTop = Math.max(0, Math.min(max, target));
	};
	node.addEventListener('wheel', wheel, { passive: false });
	return {
		destroy() {
			node.removeEventListener('wheel', wheel);
		}
	};
}
