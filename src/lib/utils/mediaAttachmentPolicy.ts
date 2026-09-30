export type MediaAttachmentPolicy = {
	kind: 'image' | 'music';
	maxCount: number;
	accept: string;
};

type Attachment = { type?: string; content_type?: string; name?: string };

export const getMediaAttachmentPolicy = (
	imageEnabled: boolean,
	imageQuality: string,
	videoEnabled: boolean,
	musicEnabled: boolean
): MediaAttachmentPolicy | null => {
	if (videoEnabled) return { kind: 'image', maxCount: 2, accept: 'image/*' };
	if (imageEnabled) {
		const maxCount = imageQuality === 'neve_image' ? 0 : imageQuality === 'neve_image_2' ? 1 : 10;
		return { kind: 'image', maxCount, accept: 'image/*' };
	}
	if (musicEnabled) {
		return {
			kind: 'music',
			maxCount: Infinity,
			accept: 'audio/*,.mp3,.wav,.flac,.m4a,.ogg,.opus,.aac,.wma,.pdf,.txt,.docx'
		};
	}
	return null;
};

export const isMediaAttachmentAllowed = (
	policy: MediaAttachmentPolicy | null,
	attachment: Attachment
): boolean => {
	if (!policy) return true;
	const mime = (attachment.content_type || attachment.type || '').toLowerCase();
	const name = (attachment.name || '').toLowerCase();
	if (policy.kind === 'image') return attachment.type === 'image' || mime.startsWith('image/');
	return (
		mime.startsWith('audio/') ||
		/\.(mp3|wav|flac|m4a|ogg|opus|aac|wma)$/.test(name) ||
		mime === 'application/pdf' ||
		name.endsWith('.pdf') ||
		mime === 'text/plain' ||
		name.endsWith('.txt') ||
		mime === 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' ||
		name.endsWith('.docx')
	);
};

export const filterMediaAttachments = <T extends Attachment>(
	policy: MediaAttachmentPolicy | null,
	attachments: T[]
): T[] => {
	if (!policy) return attachments;
	return attachments.filter((attachment) => isMediaAttachmentAllowed(policy, attachment)).slice(0, policy.maxCount);
};
