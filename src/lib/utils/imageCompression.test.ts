import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';
import ts from 'typescript';
import { describe, expect, it, vi } from 'vitest';

function compression(width = 3840, height = 2160) {
	const source = readFileSync('src/lib/utils/index.ts', 'utf8');
	const start = source.indexOf('export const compressImage =');
	const end = source.indexOf('export const generateInitialsImage', start);
	const resize = vi.fn(async (_image, _width, _height, mime) => `data:${mime};base64,result`);
	const context: any = {
		resizeImageToDataURL: resize,
		Image: class {
			width = width;
			height = height;
			onload: () => void;
			set src(_value: string) {
				queueMicrotask(() => this.onload());
			}
		}
	};
	runInNewContext(
		ts.transpile(
			source
				.slice(start, end)
				.replace('export const compressImage =', 'globalThis.compressImage ='),
			{ target: ts.ScriptTarget.ES2022 }
		),
		context
	);
	return { compress: context.compressImage, resize };
}

describe('image compression input sources', () => {
	it.each(['image/png', 'image/jpeg', 'image/webp'])('preserves %s for blob URLs', async (mime) => {
		const { compress, resize } = compression();
		expect(await compress('blob:original', 1024, 1024, mime)).toContain(`data:${mime};`);
		expect(resize).toHaveBeenCalledWith(expect.anything(), 1024, 576, mime);
	});
	it('keeps legacy data URL callers unchanged', async () => {
		const { compress } = compression();
		expect(await compress('data:image/png;base64,original', 1024, 1024)).toContain(
			'data:image/png;'
		);
	});
	it('returns the original URL without exporting pixels when already small enough', async () => {
		const { compress, resize } = compression(960, 540);
		expect(await compress('blob:original', 1024, 1024, 'image/png')).toBe('blob:original');
		expect(resize).not.toHaveBeenCalled();
	});
	it('retains single-axis resizing and aspect ratio', async () => {
		const { compress, resize } = compression();
		await compress('blob:original', null, 720, 'image/jpeg');
		expect(resize).toHaveBeenCalledWith(expect.anything(), 1280, 720, 'image/jpeg');
	});
});
