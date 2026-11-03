import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';
import ts from 'typescript';
import { describe, expect, it, vi } from 'vitest';

function setup() {
	const bitmap = { width: 1024, height: 576, close: vi.fn() };
	const self = { onmessage: null as any, postMessage: vi.fn() };
	const draw = vi.fn();
	const encode = vi.fn(async () => new Blob(['pixels'], { type: 'image/png' }));
	const canvas = vi.fn(function (this: any, w, h) {
		this.width = w;
		this.height = h;
		this.getContext = () => ({ drawImage: draw });
		this.convertToBlob = encode;
	});
	const source = readFileSync('src/lib/workers/image-compression.worker.ts', 'utf8');
	runInNewContext(
		ts.transpile(source.replace('export {};', ''), { target: ts.ScriptTarget.ES2022 }),
		{
			self,
			createImageBitmap: async () => bitmap,
			OffscreenCanvas: canvas
		}
	);
	return { bitmap, self, canvas, encode };
}

describe('image compression worker', () => {
	it('resizes PNG files off-thread and releases the bitmap', async () => {
		const { self, bitmap, canvas } = setup();
		bitmap.width = 3840;
		bitmap.height = 2160;
		await self.onmessage({ data: { file: new Blob(), mimeType: 'image/png', width: 1024, height: 1024 } });
		expect(canvas).toHaveBeenCalledWith(1024, 576);
		expect(bitmap.close).toHaveBeenCalledOnce();
	});
	it('returns small PNG files unchanged without encoding', async () => {
		const { self, bitmap, canvas } = setup();
		await self.onmessage({ data: { file: new Blob(), mimeType: 'image/png', width: 1024, height: 1024 } });
		expect(self.postMessage).toHaveBeenCalledWith({ unchanged: true });
		expect(canvas).not.toHaveBeenCalled();
		expect(bitmap.close).toHaveBeenCalledOnce();
	});
	it.each([
		['image/png', undefined],
		['image/jpeg', 0.92],
		['image/webp', 0.8]
	])('preserves native encoding settings for %s', async (mimeType, quality) => {
		const { self, canvas, bitmap, encode } = setup();
		await self.onmessage({ data: { image: bitmap, mimeType } });
		expect(canvas).toHaveBeenCalledWith(1024, 576);
		expect(encode).toHaveBeenCalledWith({ type: mimeType, quality });
		expect(self.postMessage.mock.calls[0][0].blob).toBeInstanceOf(Blob);
		expect(bitmap.close).toHaveBeenCalledOnce();
	});
	it('requests native fallback rather than losing unsupported images', async () => {
		const { self, bitmap, encode } = setup();
		encode.mockRejectedValue(new Error('unsupported'));
		await self.onmessage({
			data: { image: bitmap, mimeType: 'image/png', width: 1024, height: 1024 }
		});
		expect(self.postMessage).toHaveBeenCalledWith({ failed: true });
		expect(bitmap.close).toHaveBeenCalledOnce();
	});
});
