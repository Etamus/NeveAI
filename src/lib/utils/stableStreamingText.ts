// Replacing Text.data collapses live CSS Highlight ranges, even for an append.
// Keep the unchanged prefix/suffix and its paint ranges intact during streaming.
export function stableStreamingText(node: HTMLElement, initial: string) {
	const child = node.firstChild;
	if (!child || child.nodeType !== 3) return {};
	const text = child as Text;
	const update = (value: string) => {
		const next = value ?? '';
		const previous = text.data;
		if (previous === next) return;
		if (next.startsWith(previous)) {
			text.appendData(next.slice(previous.length));
			return;
		}
		let start = 0;
		while (start < previous.length && start < next.length && previous[start] === next[start]) start++;
		let beforeEnd = previous.length, afterEnd = next.length;
		while (beforeEnd > start && afterEnd > start && previous[beforeEnd - 1] === next[afterEnd - 1]) {
			beforeEnd--;
			afterEnd--;
		}
		text.replaceData(start, beforeEnd - start, next.slice(start, afterEnd));
	};
	update(initial);
	return { update };
}
