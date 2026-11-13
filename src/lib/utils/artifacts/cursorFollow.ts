export function verticalFollowDelta(target: number, top: number, height: number): number {
	const margin = Math.min(32, height / 4);
	if (target < top + margin) return target - top - margin;
	if (target > top + height - margin) return target - top - height + margin;
	return 0;
}

export function followCursorTarget(element: Element): boolean {
	let moved = false;
	const marker = () => {
		const bounds = element.getBoundingClientRect();
		return bounds.top + Math.min(bounds.height / 2, 16);
	};
	// Walk only the target's own ancestors. Never scroll its parent browsing context.
	for (let parent = element.parentElement; parent; parent = parent.parentElement) {
		if (parent === document.scrollingElement) continue;
		if (parent.scrollHeight <= parent.clientHeight || parent.clientHeight <= 0) continue;
		if (!/^(?:auto|scroll|overlay)$/.test(getComputedStyle(parent).overflowY)) continue;
		const bounds = parent.getBoundingClientRect();
		const delta = verticalFollowDelta(marker(), bounds.top + parent.clientTop, parent.clientHeight);
		if (Math.abs(delta) >= 1) {
			const previous = parent.scrollTop;
			parent.scrollBy({ top: delta, behavior: 'instant' });
			moved ||= parent.scrollTop !== previous;
		}
	}
	const delta = verticalFollowDelta(marker(), 0, innerHeight);
	if (Math.abs(delta) >= 1) {
		const previous = scrollY;
		window.scrollBy({ top: delta, behavior: 'instant' });
		moved ||= scrollY !== previous;
	}
	return moved;
}
