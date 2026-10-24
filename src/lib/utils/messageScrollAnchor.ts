export function getMessageScrollAnchor(message: HTMLElement): HTMLElement {
	return message.querySelector<HTMLElement>('[data-user-message-scroll-anchor]') ?? message;
}

export function getMessageAnchorScrollTop(
	currentScrollTop: number,
	containerTop: number,
	anchorTop: number,
	topOffset: number
): number {
	return Math.max(0, currentScrollTop + anchorTop - containerTop - topOffset);
}
