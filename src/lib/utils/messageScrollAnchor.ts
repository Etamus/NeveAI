export function getMessageScrollAnchor(message: HTMLElement): HTMLElement {
	return message.querySelector<HTMLElement>('[data-user-message-scroll-anchor]') ?? message;
}
