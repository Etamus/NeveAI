import { IMAGE_MODES } from './imageModes';

// Warm the small static previews before the menu is opened.
const thumbnails = new Map<string, { image: HTMLImageElement; ready: Promise<void> }>();

export function preloadImageModeThumbnails(): Promise<void> {
	if (typeof Image === 'undefined') return Promise.resolve();
	return Promise.all(IMAGE_MODES.filter(mode => mode.image).map(mode => {
		const cached = thumbnails.get(mode.image);
		if (cached) return cached.ready;
		const image = new Image();
		image.decoding = 'async';
		image.fetchPriority = 'low';
		const ready = new Promise<void>(resolve => {
			let settled = false;
			const finish = async () => {
				if (settled) return;
				settled = true;
				image.onload = null;
				image.onerror = null;
				if (image.naturalWidth) {
					try { await image.decode(); } catch { /* A loaded image is still usable. */ }
				} else thumbnails.delete(mode.image);
				resolve();
			};
			image.onload = finish;
			image.onerror = finish;
		});
		thumbnails.set(mode.image, { image, ready });
		image.src = mode.image;
		return ready;
	})).then(() => undefined);
}

// Reuse the warmed image when mounting its card.
export function mountImageModeThumbnail(node: HTMLElement, url: string) {
	const cached = thumbnails.get(url)?.image;
	const image = cached && !cached.isConnected ? cached : new Image();
	image.alt = '';
	image.width = 640;
	image.height = 800;
	image.decoding = 'async';
	image.className = 'absolute inset-0 block size-full object-cover';
	const failed = () => { image.style.visibility = 'hidden'; };
	image.addEventListener('error', failed);
	const source = url;
	if (image.getAttribute('src') !== source) image.src = source;
	node.appendChild(image);
	return { destroy() { image.removeEventListener('error', failed); image.remove(); } };
}
