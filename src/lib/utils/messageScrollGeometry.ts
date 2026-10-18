export function consumeGenerationSpacerHeight(height: number, upwardDistance: number): number {
	return Math.max(0, height - Math.max(0, upwardDistance));
}

export function hasHiddenMessageContentBelow(container: HTMLElement, visibleBottom: number): boolean {
	const lastMessage = container.querySelector<HTMLElement>('[role="log"] > [role="listitem"]:last-child');
	if (!lastMessage) return false;
	return lastMessage.getBoundingClientRect().bottom > Math.min(container.getBoundingClientRect().bottom, visibleBottom) + 5;
}

export function getMessagesContentHeight(container: HTMLElement, spacerHeight: number): number {
	const content = container.querySelector<HTMLElement>('[data-messages-content]');
	const wrapper = content?.parentElement;
	if (!content || !wrapper) return Math.max(0, container.scrollHeight - spacerHeight);

	const wrapperStyle = getComputedStyle(wrapper);
	const containerStyle = getComputedStyle(container);
	const pixels = (value: string) => parseFloat(value) || 0;
	// The wrapper's min-height fills the viewport; it is not the messages' natural height.
	return Math.max(
		0,
		content.getBoundingClientRect().height +
			pixels(wrapperStyle.paddingTop) +
			pixels(wrapperStyle.paddingBottom) +
			pixels(containerStyle.paddingTop) +
			pixels(containerStyle.paddingBottom) -
			spacerHeight
	);
}
