// Notify before changing accordion state so the chat can preserve its reading position.
export function notifyChatLayout(element: Element | null | undefined, duration = 0, opening?: boolean) {
	element?.dispatchEvent(new CustomEvent('neve:chat-layout', {
		bubbles: true,
		detail: { duration, ...(opening === undefined ? {} : { opening }) }
	}));
}
