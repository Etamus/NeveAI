import { NEVEAI_API_BASE_URL } from '$lib/constants';

export const userMessageAttachmentUrl = (file: any): string =>
	file?.url?.startsWith('data') || file?.url?.startsWith('http')
		? file.url
		: `${NEVEAI_API_BASE_URL}/files/${file.url}${file?.content_type ? '/content' : ''}`;

export function userMessageImageSize(width: number, height: number) {
	if (!(width > 0 && height > 0 && Number.isFinite(width) && Number.isFinite(height))) return null;
	const scale = Math.min(1, 320 / width, 320 / height);
	return { width: width * scale, height: height * scale };
}

// Resolve the single preview's intrinsic size while it is still in the composer.
export async function prepareUserMessageImageLayout(files: any[]): Promise<void> {
	const images = files.filter(file => file.type === 'image' || file.content_type?.startsWith('image/'));
	if (images.length !== 1) return;
	const file = images[0];
	if (userMessageImageSize(file.image_width, file.image_height)) return;
	const source = userMessageAttachmentUrl(file);
	const loaded = typeof document === 'undefined' ? undefined : Array.from(document.images).find(
		image => image.complete && image.naturalWidth > 0 && image.src === source
	);
	if (loaded) {
		file.image_width = loaded.naturalWidth;
		file.image_height = loaded.naturalHeight;
		return;
	}
	const image = new Image();
	await new Promise<void>(resolve => {
		const finish = () => {
			clearTimeout(timeout);
			image.onload = image.onerror = null;
			if (image.naturalWidth > 0) {
				file.image_width = image.naturalWidth;
				file.image_height = image.naturalHeight;
			}
			resolve();
		};
		const timeout = setTimeout(finish, 5000);
		image.onload = image.onerror = finish;
		image.src = source;
		if (image.complete) finish();
	});
}
