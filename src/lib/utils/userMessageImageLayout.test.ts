import { afterEach, describe, expect, it, vi } from 'vitest';
import { prepareUserMessageImageLayout, userMessageImageSize } from './userMessageImageLayout';

afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); });

describe('user image preview layout', () => {
	it.each([[960, 640, 320, 640 / 3], [640, 960, 640 / 3, 320], [80, 60, 80, 60]])(
		'reserves the final size of a %s by %s image without upscaling', (w, h, width, height) => {
			const size = userMessageImageSize(w, h)!;
			expect(size.width).toBeCloseTo(width);
			expect(size.height).toBeCloseTo(height);
		}
	);
	it.each([[0, 10], [10, NaN], [Infinity, 20]])('rejects invalid dimensions %s by %s', (w, h) => {
		expect(userMessageImageSize(w, h)).toBeNull();
	});
	it('resolves intrinsic dimensions before the single attachment is inserted', async () => {
		vi.stubGlobal('Image', class {
			naturalWidth = 960; naturalHeight = 640; complete = true;
		});
		const file: any = {type: 'image', url: 'data:image/png;base64,test'};
		await prepareUserMessageImageLayout([file]);
		expect([file.image_width, file.image_height]).toEqual([960, 640]);
	});
	it('keeps grid previews and documents independent of image loading', async () => {
		const create = vi.fn(); vi.stubGlobal('Image', create);
		await prepareUserMessageImageLayout([{type: 'file', content_type: 'application/pdf'}]);
		await prepareUserMessageImageLayout([{type: 'image'}, {type: 'image'}]);
		expect(create).not.toHaveBeenCalled();
	});
	it('reuses the loaded composer image without making another image request', async () => {
		const create = vi.fn(); vi.stubGlobal('Image', create);
		vi.stubGlobal('document', {images: [{src: 'https://example.test/image.png', complete: true, naturalWidth: 640, naturalHeight: 960}]});
		const file: any = {type: 'image', url: 'https://example.test/image.png'};
		await prepareUserMessageImageLayout([file]);
		expect([file.image_width, file.image_height]).toEqual([640, 960]);
		expect(create).not.toHaveBeenCalled();
	});
	it('does not block a send indefinitely when the image server fails to respond', async () => {
		vi.useFakeTimers();
		vi.stubGlobal('Image', class { complete = false; naturalWidth = 0; });
		const file = {type: 'image', url: 'https://example.test/missing.png'};
		const pending = prepareUserMessageImageLayout([file]);
		await vi.advanceTimersByTimeAsync(5000);
		await pending;
		expect(file).not.toHaveProperty('image_width');
	});
});
