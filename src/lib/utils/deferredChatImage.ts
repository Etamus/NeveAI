const preloadMargin = 1200;

// Reserved geometry can be measured before the image bytes arrive, including native-lazy images.
export const isChatImageLayoutPending = (image: HTMLImageElement): boolean =>
	!image.complete && !image.hasAttribute('data-chat-image-sized');

// Keep src owned by Svelte; promote nearby native-lazy images for the startup media wait.
export const activateDeferredChatImages = (root: ParentNode): HTMLImageElement[] => {
	const activated: HTMLImageElement[] = [];
	for (const image of root.querySelectorAll<HTMLImageElement>('img[loading="lazy"]')) {
		const viewport = image.closest('#messages-container');
		if (!viewport) continue;
		const bounds = image.getBoundingClientRect();
		const view = viewport.getBoundingClientRect();
		if (bounds.width > 0 && bounds.height > 0 &&
			bounds.bottom >= view.top - preloadMargin && bounds.top <= view.bottom + preloadMargin) {
			image.loading = 'eager';
			activated.push(image);
		}
	}
	return activated;
};
