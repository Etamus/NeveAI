import { tick } from 'svelte';

const CLOSE_CHAT_DROPDOWNS = 'neve:close-chat-dropdowns';

export const onChatDropdownDismiss = (close: () => void) => {
	window.addEventListener(CLOSE_CHAT_DROPDOWNS, close);
	return () => window.removeEventListener(CLOSE_CHAT_DROPDOWNS, close);
};

export const dismissChatDropdowns = async () => {
	const panels = Array.from(document.querySelectorAll<HTMLElement>(
		'[role="menu"], [data-model-selector-content], [data-composer-dropdown-anchor]'
	));
	window.dispatchEvent(new Event(CLOSE_CHAT_DROPDOWNS));
	await tick();
	if (panels.length === 0) return;
	await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));
	// Finish the exit before a chat-mode change can reposition its anchors.
	const exits = panels.flatMap((panel) => panel.getAnimations());
	for (const animation of exits) animation.finish();
	await Promise.all(exits.map((animation) => animation.finished.catch(() => {})));
	await tick();
};
