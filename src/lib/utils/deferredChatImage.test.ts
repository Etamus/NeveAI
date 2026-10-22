import { describe, expect, it, vi } from 'vitest';
import { activateDeferredChatImages, isChatImageLayoutPending } from './deferredChatImage';

const image = (top: number, overrides = {}) => ({
	src: '/original.png',
	loading: 'lazy',
	closest: () => ({ getBoundingClientRect: () => ({ top: 0, bottom: 800 }) }),
	getBoundingClientRect: () => ({ width: 400, height: 225, top, bottom: top + 225 }),
	removeAttribute: vi.fn(),
	...overrides
});
const root = (...images: ReturnType<typeof image>[]) => ({
	querySelectorAll: (selector: string) => {
		expect(selector).toBe('img[loading="lazy"]');
		return images.filter(node => node.loading === 'lazy');
	}
}) as unknown as ParentNode;

describe('native deferred chat images with reserved dimensions', () => {
	it.each(['lazy', 'eager'])('does not wait for reserved %s images to measure history rows', (loading) => {
		const image = {complete: false, loading, hasAttribute: (name: string) => name === 'data-chat-image-sized'};
		expect(isChatImageLayoutPending(image as HTMLImageElement)).toBe(false);
	});
	it('still waits for unsized images and stops waiting when they finish or fail', () => {
		const image = {complete: false, hasAttribute: () => false};
		expect(isChatImageLayoutPending(image as unknown as HTMLImageElement)).toBe(true);
		image.complete = true;
		expect(isChatImageLayoutPending(image as unknown as HTMLImageElement)).toBe(false);
	});
	it('promotes nearby images without removing or replacing their sources', () => {
		const near = image(100), distant = image(-4000);
		expect(activateDeferredChatImages(root(near, distant))).toEqual([near]);
		expect(near.loading).toBe('eager');
		expect(distant.loading).toBe('lazy');
		for (const node of [near, distant]) {
			expect(node.src).toBe('/original.png');
			expect(node.removeAttribute).not.toHaveBeenCalled();
		}
	});
	it('keeps nearby images eligible for the startup media wait', () => {
		const nodes = [image(-1250), image(1999)];
		expect(activateDeferredChatImages(root(...nodes))).toEqual(nodes);
	});
	it('does not activate zero-sized images or images outside a chat', () => {
		const nodes = [image(100, {getBoundingClientRect: () => ({width:0,height:0,top:100,bottom:100})}), image(100, {closest: () => null})];
		expect(activateDeferredChatImages(root(...nodes))).toEqual([]);
		expect(nodes.every(node => node.loading === 'lazy')).toBe(true);
	});
	it('never demotes loaded images when scrolling away or repeating startup checks', () => {
		const node = image(100), container = root(node);
		activateDeferredChatImages(container);
		node.getBoundingClientRect = () => ({width:400,height:225,top:-4000,bottom:-3775});
		expect(activateDeferredChatImages(container)).toEqual([]);
		expect(node.loading).toBe('eager');
		expect(node.src).toBe('/original.png');
	});
	it('does not alter data URLs, blob URLs, or changed sources', () => {
		for (const src of ['data:image/png;base64,example', 'blob:example', '/new.png']) {
			const node = image(100, {src});
			activateDeferredChatImages(root(node));
			expect(node.src).toBe(src);
		}
	});
});
