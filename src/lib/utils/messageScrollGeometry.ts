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
		content.getBoundingClientRect().bottom -
			wrapper.getBoundingClientRect().top +
			pixels(wrapperStyle.paddingBottom) +
			pixels(containerStyle.paddingTop) +
			pixels(containerStyle.paddingBottom) -
			spacerHeight
	);
}
