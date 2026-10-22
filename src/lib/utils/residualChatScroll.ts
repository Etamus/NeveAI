export const RESIDUAL_CHAT_SCROLL_ATTRIBUTE = 'data-chat-residual-scroll';

// Ignore only the idle transcript's one-pixel overflow, without changing its reserved spacing.
export const stabilizeResidualChatScroll = (viewport: HTMLElement, enabled: boolean) => {
	let active = enabled;
	let destroyed = false;
	const synchronize = () => {
		if (destroyed) return;
		const overflow = viewport.scrollHeight - viewport.clientHeight;
		viewport.toggleAttribute(RESIDUAL_CHAT_SCROLL_ATTRIBUTE,
			active && viewport.clientHeight > 0 && overflow > 0 && overflow <= 1 &&
			!viewport.hasAttribute('data-history-loading')
		);
	};
	const resize = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(synchronize);
	resize?.observe(viewport);
	// Composer resizing changes this wrapper's padding, not necessarily its content box.
	if (viewport.firstElementChild) resize?.observe(viewport.firstElementChild, { box: 'border-box' });
	const mutations = typeof MutationObserver === 'undefined' ? null : new MutationObserver(synchronize);
	mutations?.observe(viewport, { attributes: true, attributeFilter: ['data-history-loading'] });
	synchronize();
	return {
		update(value: boolean) { active = value; synchronize(); },
		destroy() {
			destroyed = true;
			resize?.disconnect();
			mutations?.disconnect();
			viewport.removeAttribute(RESIDUAL_CHAT_SCROLL_ATTRIBUTE);
		}
	};
};
