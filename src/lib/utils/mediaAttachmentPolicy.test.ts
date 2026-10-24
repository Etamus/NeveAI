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
		expect(filterMediaAttachments(getMediaAttachmentPolicy(true, 'moss_image_3', false, false), images)).toHaveLength(4);
		for (const quality of ['qwen_image_2s', 'qwen_image_2_1_official']) {
			expect(filterMediaAttachments(getMediaAttachmentPolicy(true, quality, false, false), images)).toHaveLength(10);
		}
	});
	it('keeps Neve Image 3 limited to four image references regardless of stale mode', () => {
		for (const mode of ['normal', 'restore', 'inpaint', 'outpaint', 'outfit', 'body']) {
			const policy = getMediaAttachmentPolicy(true, 'moss_image_3', false, false, mode);
			expect(policy?.maxCount).toBe(4);
			expect(isMediaAttachmentAllowed(policy, { type: 'application/pdf' })).toBe(false);
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
	it('limits only Neve Image 2 swap and restore attachments', () => {
		expect(getMediaAttachmentPolicy(true,'qwen_image_2s',false,false,'outfit')?.maxCount).toBe(4);
		expect(getMediaAttachmentPolicy(true,'qwen_image_2s',false,false,'body')?.maxCount).toBe(4);
		expect(getMediaAttachmentPolicy(true,'qwen_image_2s',false,false,'restore')?.maxCount).toBe(1);
		for(const mode of ['inpaint','outpaint'])expect(getMediaAttachmentPolicy(true,'qwen_image_2s',false,false,mode)?.maxCount).toBe(1);
		expect(getMediaAttachmentPolicy(true,'qwen_image_2s',false,false,'normal')?.maxCount).toBe(10);
		expect(getMediaAttachmentPolicy(true,'qwen_image_2_1_official',false,false,'restore')?.maxCount).toBe(10);
	});
});
