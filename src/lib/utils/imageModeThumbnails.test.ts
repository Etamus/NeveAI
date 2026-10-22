import { afterEach, describe, expect, it, vi } from 'vitest';

afterEach(() => { vi.unstubAllGlobals(); vi.resetModules(); });

describe('image mode thumbnail preloading', () => {
	it('reuses warmed WebP previews across menu mounts', async () => {
		const images: any[] = [];
		class Preview {
			naturalWidth = 640;
			onload: (() => void) | null = null;
			onerror: (() => void) | null = null;
			isConnected = false;
			style = {};
			value = '';
			decode = vi.fn(async () => {});
			addEventListener = vi.fn();
			removeEventListener = vi.fn();
			remove() { this.isConnected = false; }
			getAttribute() { return this.value; }
			constructor() { images.push(this); }
			set src(value: string) { this.value = value; queueMicrotask(() => this.onload?.()); }
		}
		vi.stubGlobal('Image', Preview);
		const { preloadImageModeThumbnails, mountImageModeThumbnail } = await import('./imageModeThumbnails');
		await preloadImageModeThumbnails();
		const node = { appendChild: vi.fn(image => { image.isConnected = true; }) } as any;
		const url = '/static/aprimorar.webp';
		const first = mountImageModeThumbnail(node, url);
		const element = node.appendChild.mock.calls[0][0];
		expect(element).toBe(images[0]);
		first.destroy();
		const second = mountImageModeThumbnail(node, url);
		expect(node.appendChild.mock.calls[1][0]).toBe(element);
		expect(images).toHaveLength(5);
		expect(element.decode).toHaveBeenCalledTimes(1);
		second.destroy();
	});
	it('keeps a decoded image per card and deduplicates overlapping requests', async () => {
		const images: any[] = [];
		class Preview {
			naturalWidth = 640;
			onload: (() => void) | null = null;
			onerror: (() => void) | null = null;
			decode = vi.fn(async () => {});
			constructor() { images.push(this); }
			set src(_value: string) { queueMicrotask(() => this.onload?.()); }
		}
		vi.stubGlobal('Image', Preview);
		const { preloadImageModeThumbnails } = await import('./imageModeThumbnails');
		await Promise.all([preloadImageModeThumbnails(), preloadImageModeThumbnails()]);
		await preloadImageModeThumbnails();
		expect(images).toHaveLength(5);
		for (const image of images) expect(image.decode).toHaveBeenCalledTimes(1);
	});
	it('allows failed loads to retry and does not reject the whole menu', async () => {
		let count = 0;
		class Preview {
			naturalWidth = 0;
			onload: (() => void) | null = null;
			onerror: (() => void) | null = null;
			constructor() { count++; }
			set src(_value: string) { queueMicrotask(() => this.onerror?.()); }
		}
		vi.stubGlobal('Image', Preview);
		const { preloadImageModeThumbnails } = await import('./imageModeThumbnails');
		await preloadImageModeThumbnails();
		await preloadImageModeThumbnails();
		expect(count).toBe(10);
	});
});
