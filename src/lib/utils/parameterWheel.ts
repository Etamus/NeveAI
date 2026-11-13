export function parameterWheel(node: HTMLElement) {
	const wheel = (event: WheelEvent) => {
		if (event.ctrlKey || event.shiftKey || Math.abs(event.deltaX) > Math.abs(event.deltaY)) return;
		if (event.deltaMode === 0 && Math.abs(event.deltaY) < 50) return;
		if (node.scrollHeight <= node.clientHeight) return;
		const unit = event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? node.clientHeight : 1;
		const amount = Math.sign(event.deltaY) * Math.min(48, Math.abs(event.deltaY * unit) * 0.5);
		event.preventDefault();
		node.scrollTop = Math.max(
			0,
			Math.min(node.scrollHeight - node.clientHeight, node.scrollTop + amount)
		);
	};
	node.addEventListener('wheel', wheel, { passive: false });
	return {
		destroy() {
			node.removeEventListener('wheel', wheel);
		}
	};
}
