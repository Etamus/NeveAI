import { activateDeferredChatImages, isChatImageLayoutPending } from './deferredChatImage';

// This barrier runs while the existing chat is hidden. It owns no visible-scroll listeners.
export function prepareLoadedChatLayout(viewport: HTMLElement, signal: AbortSignal): Promise<boolean> {
	return new Promise(resolve => {
		let frame = 0;
		let stableFrames = 0;
		let previous = '';
		const finish = (ready: boolean) => {
			cancelAnimationFrame(frame);
			signal.removeEventListener('abort', abort);
			resolve(ready);
		};
		const abort = () => finish(false);
		const update = () => {
			if (signal.aborted || !viewport.isConnected) { finish(false); return; }
			viewport.scrollTop = viewport.scrollHeight;
			activateDeferredChatImages(viewport);
			let imagesPending = false;
			for (const image of viewport.querySelectorAll<HTMLImageElement>('img')) {
				if (isChatImageLayoutPending(image)) {
					// Unknown geometry above the viewport also affects its final scroll position.
					if (image.loading === 'lazy') image.loading = 'eager';
					imagesPending = true;
				} else if (!image.complete && image.loading !== 'lazy' && image.closest('[data-generated-visual-media]')) {
					imagesPending = true;
				}
			}
			const mediaPending = Array.from(viewport.querySelectorAll<HTMLVideoElement>('video')).some(video =>
				video.readyState < video.HAVE_METADATA && !video.error
			);
			const rowsPending = Array.from(viewport.querySelectorAll<HTMLElement>('[data-message-measured="false"]')).some(row =>
				row.getBoundingClientRect().height > 0
			);
			const pending = viewport.clientWidth <= 0 || viewport.clientHeight <= 0 || imagesPending || mediaPending || rowsPending ||
				viewport.ownerDocument.fonts?.status === 'loading' ||
				Boolean(viewport.querySelector('[data-chat-layout-pending="true"]'));
			const geometry = `${viewport.scrollHeight}:${viewport.clientHeight}:${viewport.clientWidth}:${viewport.scrollTop}`;
			stableFrames = !pending && geometry === previous ? stableFrames + 1 : 0;
			previous = geometry;
			if (stableFrames >= 3) { finish(true); return; }
			frame = requestAnimationFrame(update);
		};
		signal.addEventListener('abort', abort, { once: true });
		if (signal.aborted) { finish(false); return; }
		frame = requestAnimationFrame(update);
	});
}
