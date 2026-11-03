import CompressionWorker from '$lib/workers/image-compression.worker?worker';
import { compressImage } from '$lib/utils';

export async function prepareImageUpload(
	file: File,
	width: number | null,
	height: number | null
): Promise<File> {
	if (!width && !height) return file;
	if (typeof Worker !== 'undefined' && typeof OffscreenCanvas !== 'undefined') {
		let worker: Worker | undefined;
		let bitmap: ImageBitmap | undefined;
		let timeout: ReturnType<typeof setTimeout> | undefined;
		try {
			worker = new CompressionWorker();
			if (file.type !== 'image/png') {
				const source = URL.createObjectURL(file);
				try {
					const image = new Image();
					image.src = source;
					await image.decode();
					const originalWidth = image.naturalWidth;
					const originalHeight = image.naturalHeight;
					if ((!width || originalWidth <= width) && (!height || originalHeight <= height))
						return file;
					const scale = Math.min(
						width ? width / originalWidth : 1,
						height ? height / originalHeight : 1
					);
					const canvas = new OffscreenCanvas(
						Math.round(originalWidth * scale),
						Math.round(originalHeight * scale)
					);
					const context = canvas.getContext('2d');
					if (!context) throw new Error('Image canvas unavailable');
					// Preserve native drawImage pixels; only the expensive encoding moves to the worker.
					context.drawImage(image, 0, 0, canvas.width, canvas.height);
					bitmap = canvas.transferToImageBitmap();
				} finally {
					URL.revokeObjectURL(source);
				}
			}
			const result = await new Promise<{ blob?: Blob; unchanged?: boolean }>((resolve, reject) => {
				timeout = setTimeout(() => reject(new Error('Image compression timed out')), 10000);
				worker!.onmessage = ({ data }) =>
					data.failed ? reject(new Error('Image compression unavailable')) : resolve(data);
				worker!.onerror = () => reject(new Error('Image compression unavailable'));
				if (bitmap) worker!.postMessage({ image: bitmap, mimeType: file.type }, [bitmap]);
				else worker!.postMessage({ file, mimeType: file.type, width, height });
			});
			if (result.unchanged) return file;
			if (result.blob)
				return new File([result.blob], file.name, {
					type: result.blob.type,
					lastModified: file.lastModified
				});
		} catch {
			// Retain native canvas support when workers or a format are unavailable.
		} finally {
			clearTimeout(timeout);
			bitmap?.close();
			worker?.terminate();
		}
	}
	const source = URL.createObjectURL(file);
	try {
		const url = String(await compressImage(source, width, height, file.type));
		if (url === source) return file;
		const blob = await (await fetch(url)).blob();
		return new File([blob], file.name, { type: blob.type, lastModified: file.lastModified });
	} finally {
		URL.revokeObjectURL(source);
	}
}
