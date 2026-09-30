import { describe, expect, it } from 'vitest';
import {
	filterMediaAttachments,
	getMediaAttachmentPolicy,
	isMediaAttachmentAllowed
} from './mediaAttachmentPolicy';

describe('media attachment limits', () => {
	it('keeps normal chat unrestricted', () => {
		expect(getMediaAttachmentPolicy(false, 'neve_image', false, false)).toBeNull();
	});

	it('limits video to two images', () => {
		const policy = getMediaAttachmentPolicy(false, 'neve_image', true, false);
		expect(filterMediaAttachments(policy, [
			{ type: 'image/png' }, { content_type: 'image/jpeg' }, { type: 'image/webp' }, { type: 'application/pdf' }
		])).toHaveLength(2);
	});

	it('uses the limit of each image model', () => {
		const images = Array.from({ length: 12 }, () => ({ type: 'image/png' }));
		expect(filterMediaAttachments(getMediaAttachmentPolicy(true, 'neve_image', false, false), images)).toHaveLength(0);
		expect(filterMediaAttachments(getMediaAttachmentPolicy(true, 'neve_image_2', false, false), images)).toHaveLength(1);
		for (const quality of ['qwen_image_2s', 'qwen_image_2_1_official']) {
			expect(filterMediaAttachments(getMediaAttachmentPolicy(true, quality, false, false), images)).toHaveLength(10);
		}
	});

	it('accepts music source formats but not unrelated files', () => {
		const policy = getMediaAttachmentPolicy(false, 'neve_image', false, true);
		for (const name of ['song.mp3', 'lyrics.txt', 'score.pdf', 'notes.docx']) {
			expect(isMediaAttachmentAllowed(policy, { name })).toBe(true);
		}
		expect(isMediaAttachmentAllowed(policy, { name: 'movie.mp4', type: 'video/mp4' })).toBe(false);
		expect(isMediaAttachmentAllowed(policy, { name: 'image.png', type: 'image/png' })).toBe(false);
	});
});
