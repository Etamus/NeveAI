self.onmessage = async ({
	data
}: MessageEvent<{
	image?: ImageBitmap;
	file?: File;
	mimeType: string;
	width?: number | null;
	height?: number | null;
}>) => {
	let image = data.image;
	try {
		if (!image && data.file) image = await createImageBitmap(data.file);
		if (!image) throw new Error('Image unavailable');
		let { width, height } = image;
		if (data.file) {
			const maxWidth = data.width;
			const maxHeight = data.height;
			if ((!maxWidth || width <= maxWidth) && (!maxHeight || height <= maxHeight)) {
				self.postMessage({ unchanged: true });
				return;
			}
			const scale = Math.min(maxWidth ? maxWidth / width : 1, maxHeight ? maxHeight / height : 1);
			width = Math.round(width * scale);
			height = Math.round(height * scale);
		}
		const canvas = new OffscreenCanvas(width, height);
		const context = canvas.getContext('2d');
		if (!context) throw new Error('Image canvas unavailable');
		context.drawImage(image, 0, 0, width, height);
		// Match native canvas defaults; OffscreenCanvas can otherwise choose a different quality.
		const quality =
			data.mimeType === 'image/jpeg' ? 0.92 : data.mimeType === 'image/webp' ? 0.8 : undefined;
		self.postMessage({ blob: await canvas.convertToBlob({ type: data.mimeType, quality }) });
	} catch {
		self.postMessage({ failed: true });
	} finally {
		image?.close();
	}
};

export {};
