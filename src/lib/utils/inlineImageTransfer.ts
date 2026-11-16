export const INLINE_IMAGE_THRESHOLD = 1024 * 1024;

export function isLargeInlineImage(value: unknown): value is string {
	return typeof value === 'string' && value.length >= INLINE_IMAGE_THRESHOLD &&
		value.startsWith('data:image/') && value.slice(0, 256).includes(';base64,');
}

// Blob handles avoid copying the same multi-megabyte string across threads repeatedly.
export function packInlineImages(value: unknown, images = new Map<string, Blob>()): unknown {
	if (isLargeInlineImage(value)) {
		let blob = images.get(value);
		if (!blob) { blob = new Blob([value]); images.set(value, blob); }
		return blob;
	}
	if (Array.isArray(value)) return value.map(item => packInlineImages(item, images));
	if (value !== null && typeof value === 'object') return Object.fromEntries(
		Object.entries(value).map(([key, item]) => [key, packInlineImages(item, images)])
	);
	return value;
}

export async function unpackInlineImages(value: unknown, images = new Map<Blob, Promise<string>>()): Promise<unknown> {
	if (value instanceof Blob) {
		let text = images.get(value);
		if (!text) { text = value.text(); images.set(value, text); }
		return text;
	}
	if (Array.isArray(value)) return Promise.all(value.map(item => unpackInlineImages(item, images)));
	if (value !== null && typeof value === 'object') return Object.fromEntries(await Promise.all(
		Object.entries(value).map(async ([key, item]) => [key, await unpackInlineImages(item, images)])
	));
	return value;
}
