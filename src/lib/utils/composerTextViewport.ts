import type { EditorView } from 'prosemirror-view';

export function scrollComposerSelectionToEnd(view: EditorView): boolean {
	const { selection, doc } = view.state;
	if (!selection.empty || selection.to !== doc.content.size - 1 || !doc.lastChild?.isTextblock) return false;
	const viewport = view.dom.closest<HTMLElement>('#chat-input-container');
	if (!viewport || viewport.scrollHeight <= viewport.clientHeight || viewport.scrollWidth > viewport.clientWidth) return false;
	viewport.scrollTop = viewport.scrollHeight;
	return true;
}

export function composerTextViewport(node: HTMLElement, revision: number) {
	let currentRevision = revision;
	let frame = 0;
	const editorWrapper = node.parentElement;

	const updateShade = () => {
		editorWrapper?.classList.toggle('composer-text-scrolled',
			node.scrollHeight > node.clientHeight && node.scrollTop > 0.5);
	};
	const wheel = (event: WheelEvent) => {
		// A compositor wheel can round a fractional endpoint differently from caret scrolling.
		const maximum = node.scrollHeight - node.clientHeight;
		if (maximum > 0 && event.deltaY > 0 && !event.shiftKey && maximum - node.scrollTop <= 1) event.preventDefault();
	};
	const schedule = () => {
		if (frame) return;
		frame = requestAnimationFrame(() => {
			frame = 0;
			updateShade();
		});
	};
	const observer = new ResizeObserver(schedule);
	observer.observe(node);
	node.addEventListener('scroll', updateShade, { passive: true });
	node.addEventListener('wheel', wheel, { passive: false });
	schedule();
	return {
		update(nextRevision: number) {
			if (nextRevision !== currentRevision) {
				currentRevision = nextRevision;
				schedule();
			}
		},
		destroy() {
			cancelAnimationFrame(frame);
			observer.disconnect();
			node.removeEventListener('scroll', updateShade);
			node.removeEventListener('wheel', wheel);
			editorWrapper?.classList.remove('composer-text-scrolled');
		}
	};
}
