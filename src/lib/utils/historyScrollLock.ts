export const HISTORY_LAYOUT_EVENT = 'neve:history-layout';

export const observeHistoryBoundary = (sentinel: HTMLElement, load: () => void) => {
	const viewport = sentinel.closest<HTMLElement>('#messages-container');
	if (!viewport) return {};
	const check = () => {
		const view = viewport.getBoundingClientRect();
		const bounds = sentinel.getBoundingClientRect();
		if (viewport.scrollTop <= 1 && bounds.bottom > view.top && bounds.top < view.bottom) load();
	};
	const wheel = (event: WheelEvent) => {
		if (event.deltaY >= 0) return;
		check();
		if (viewport.hasAttribute('data-history-loading')) {
			event.preventDefault();
			event.stopImmediatePropagation();
		}
	};
	const observer = typeof IntersectionObserver === 'undefined' ? null : new IntersectionObserver(
		(entries) => { if (entries.some((entry) => entry.isIntersecting)) check(); },
		{ root: viewport, rootMargin: '0px' }
	);
	observer?.observe(sentinel);
	viewport.addEventListener('scroll', check, { capture: true });
	viewport.addEventListener('wheel', wheel, { capture: true, passive: false });
	return { destroy() {
		observer?.disconnect();
		viewport.removeEventListener('scroll', check, { capture: true });
		viewport.removeEventListener('wheel', wheel, { capture: true });
	} };
};

export const lockHistoryScroll = (viewport: HTMLElement, align: () => void) => {
	const properties = ['overflow-y', 'scroll-behavior'] as const;
	const previous = properties.map((name) => ({
		name, value: viewport.style.getPropertyValue(name), priority: viewport.style.getPropertyPriority(name)
	}));
	let released = false;
	const capture = { capture: true };
	const synchronize = () => {
		if (released) return;
		align();
		viewport.dispatchEvent(new Event(HISTORY_LAYOUT_EVENT));
	};
	const prevent = (event: Event) => {
		event.preventDefault();
		event.stopImmediatePropagation();
	};
	const keydown = (event: KeyboardEvent) => {
		if ((event.target as Element)?.closest?.('input, textarea, [contenteditable="true"]')) return;
		if (['ArrowUp', 'ArrowDown', 'PageUp', 'PageDown', 'Home', 'End', ' '].includes(event.key)) prevent(event);
	};
	const scroll = (event: Event) => {
		event.stopImmediatePropagation();
		synchronize();
	};
	viewport.style.setProperty('overflow-y', 'hidden');
	viewport.style.setProperty('scroll-behavior', 'auto');
	viewport.setAttribute('data-history-loading', 'true');
	viewport.addEventListener('wheel', prevent, { capture: true, passive: false });
	viewport.addEventListener('touchmove', prevent, { capture: true, passive: false });
	viewport.addEventListener('keydown', keydown, true);
	viewport.addEventListener('scroll', scroll, true);
	// ResizeObserver runs after layout, before paint, including cold image/font reflows.
	const resize = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(synchronize);
	const content = viewport.querySelector?.('[data-messages-content]');
	if (content) resize?.observe(content);
	const observedRows = new WeakSet<Element>();
	const observeRows = () => {
		for (const row of content?.querySelectorAll?.('[data-message-window]') ?? []) {
			if (observedRows.has(row)) continue;
			observedRows.add(row);
			resize?.observe(row);
		}
	};
	observeRows();
	// Inner reflows can move the reading anchor without resizing the whole list.
	// Compensate DOM/media changes before paint instead of waiting for the next RAF.
	const mutations = typeof MutationObserver === 'undefined' ? null : new MutationObserver(() => {
		observeRows();
		synchronize();
	});
	if (content) mutations?.observe(content, {
		childList: true, characterData: true, subtree: true, attributes: true,
		attributeFilter: ['style', 'class', 'src', 'width', 'height', 'open']
	});
	viewport.addEventListener('load', synchronize, true);
	viewport.addEventListener('error', synchronize, true);
	return {
		synchronize,
		release(synchronizePosition = true) {
			if (released) return;
			if (synchronizePosition) synchronize();
			released = true;
			resize?.disconnect();
			mutations?.disconnect();
			viewport.removeEventListener('load', synchronize, true);
			viewport.removeEventListener('error', synchronize, true);
			viewport.removeEventListener('wheel', prevent, capture);
			viewport.removeEventListener('touchmove', prevent, capture);
			viewport.removeEventListener('keydown', keydown, capture);
			viewport.removeEventListener('scroll', scroll, capture);
			for (const {name, value, priority} of previous) {
				if (value) viewport.style.setProperty(name, value, priority);
				else viewport.style.removeProperty(name);
			}
			viewport.removeAttribute('data-history-loading');
		}
	};
};

export const waitForHistoryLayout = (
	viewport: HTMLElement, synchronize: () => void, ready: () => boolean, signal: AbortSignal
) => new Promise<void>((resolve) => {
	let frame: number;
	let stableFrames = 0;
	let height = -1;
	const started = performance.now();
	const finish = () => {
		cancelAnimationFrame(frame);
		signal.removeEventListener('abort', finish);
		resolve();
	};
	const update = () => {
		if (signal.aborted || !viewport.isConnected) { finish(); return; }
		synchronize();
		const nextHeight = viewport.scrollHeight;
		stableFrames = nextHeight === height && ready() && viewport.ownerDocument?.fonts?.status !== 'loading'
			? stableFrames + 1 : 0;
		height = nextHeight;
		const elapsed = performance.now() - started;
		// Give the loading indicator time to be painted, even for a cached batch.
		if ((stableFrames >= 3 && elapsed >= 180) || elapsed >= 5000) finish();
		else frame = requestAnimationFrame(update);
	};
	signal.addEventListener('abort', finish, { once: true });
	frame = requestAnimationFrame(update);
});
