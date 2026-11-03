import { describe, expect, it } from 'vitest';
import { imageCompressionBounds } from './imageCompressionBounds';

describe('image compression bounds', () => {
	it('leaves original files untouched by default or with inactive user limits', () => {
		expect(imageCompressionBounds()).toEqual({ width: null, height: null });
		expect(imageCompressionBounds({ imageCompressionSize: { width: 512, height: 512 } })).toEqual({
			width: null,
			height: null
		});
	});
	it('preserves user bounds and permits a single constrained dimension', () => {
		expect(
			imageCompressionBounds({ imageCompression: true, imageCompressionSize: { width: 1024 } })
		).toEqual({ width: 1024, height: null });
		expect(imageCompressionBounds({ imageCompression: true })).toEqual({
			width: null,
			height: null
		});
	});
	it('honors server limits even when user compression is disabled', () => {
		expect(imageCompressionBounds({}, { file: { image_compression: { height: 768 } } })).toEqual({
			width: null,
			height: 768
		});
	});
	it('uses the stricter configured bound independently on each axis', () => {
		expect(
			imageCompressionBounds(
				{ imageCompression: true, imageCompressionSize: { width: 1024, height: 768 } },
				{ file: { image_compression: { width: 512, height: 2048 } } }
			)
		).toEqual({ width: 512, height: 768 });
	});
});
