let queue = Promise.resolve();
self.onmessage = ({ data }: MessageEvent<{ id: number; source: string }>) => {
	queue = queue.then(async () => {
		let image: ImageBitmap | undefined;
		try {
			const response = await fetch(data.source, { signal: AbortSignal.timeout(10000) });
			if (!response.ok) throw new Error('Image unavailable');
			const blob = await response.blob();
			// Preserve animated formats and vector rendering in the native image element.
			if (['image/gif', 'image/webp', 'image/avif', 'image/svg+xml'].includes(blob.type)) {
				self.postMessage({ id: data.id });
				return;
			}
			image = await createImageBitmap(blob);
			const side = Math.min(image.width, image.height);
			const edge = Math.min(512, side);
			const canvas = new OffscreenCanvas(edge, edge);
			const context = canvas.getContext('2d')!;
			context.imageSmoothingQuality = 'high';
			context.drawImage(image, (image.width-side)/2, (image.height-side)/2, side, side, 0, 0, edge, edge);
			self.postMessage({ id: data.id, blob: await canvas.convertToBlob({ type: 'image/png' }) });
		} catch {
			self.postMessage({ id: data.id });
		} finally {
			image?.close();
		}
	});
};

export {};
