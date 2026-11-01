let queue = Promise.resolve();
const jobs = new Map<number, AbortController>();
self.onmessage = ({ data }: MessageEvent<{ id: number; source: string; cancel?: number }>) => {
	if (data.cancel !== undefined) {
		jobs.get(data.cancel)?.abort();
		jobs.delete(data.cancel);
		return;
	}
	const controller = new AbortController();
	jobs.set(data.id, controller);
	queue = queue.then(async () => {
		if (controller.signal.aborted) return;
		let image: ImageBitmap | undefined;
		const timeout = setTimeout(() => controller.abort(), 10000);
		try {
			const response = await fetch(data.source, { signal: controller.signal });
			if (!response.ok) throw new Error('Image unavailable');
			const blob = await response.blob();
			// Preserve animated formats and vector rendering in the native image element.
			if (['image/gif', 'image/webp', 'image/avif', 'image/svg+xml'].includes(blob.type)) {
				self.postMessage({ id: data.id });
				return;
			}
			image = await createImageBitmap(blob);
			if (controller.signal.aborted) return;
			const side = Math.min(image.width, image.height);
			const edge = Math.min(512, side);
			const canvas = new OffscreenCanvas(edge, edge);
			const context = canvas.getContext('2d')!;
			context.imageSmoothingQuality = 'high';
			context.drawImage(image, (image.width-side)/2, (image.height-side)/2, side, side, 0, 0, edge, edge);
			const preview = await canvas.convertToBlob({ type: 'image/png' });
			if (!controller.signal.aborted) self.postMessage({ id: data.id, blob: preview });
		} catch {
			self.postMessage({ id: data.id });
		} finally {
			clearTimeout(timeout);
			jobs.delete(data.id);
			if (controller.signal.aborted) self.postMessage({ id: data.id });
			image?.close();
		}
	});
};

export {};
