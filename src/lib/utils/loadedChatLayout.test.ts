import { afterEach, describe, expect, it, vi } from 'vitest';
import { prepareLoadedChatLayout } from './loadedChatLayout';

afterEach(() => { vi.unstubAllGlobals(); });

function fixture() {
	let nextId = 0;
	const frames = new Map<number, FrameRequestCallback>();
	vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => { frames.set(++nextId, callback); return nextId; });
	vi.stubGlobal('cancelAnimationFrame', (id: number) => frames.delete(id));
	const images: any[] = [], videos: any[] = [], rows: any[] = [];
	const view = {
		isConnected: true, scrollTop: 0, scrollHeight: 900, clientWidth: 600, clientHeight: 400,
		ownerDocument: { fonts: { status: 'loaded' } }, pendingRender: false,
		addEventListener: vi.fn(),
		querySelector: () => view.pendingRender ? {} : null,
		querySelectorAll: (selector: string) => selector === 'img' ? images : selector === 'video' ? videos : selector === '[data-message-measured="false"]' ? rows : []
	};
	const advance = (count = 1) => {
		for (let i = 0; i < count; i++) {
			const scheduled = [...frames.values()]; frames.clear();
			for (const callback of scheduled) callback(i * 16);
		}
	};
	return { view, images, videos, rows, frames, advance };
}

describe('Hidden existing-chat layout preparation', () => {
	it('waits for unknown image geometry without a five-second release or input listeners', async () => {
		const {view, images, advance, frames} = fixture();
		images.push({complete:false, loading:'lazy', hasAttribute:()=>false});
		let resolved = false;
		const ready = prepareLoadedChatLayout(view as any, new AbortController().signal).then(value => { resolved = true; return value; });
		advance(400); await Promise.resolve();
		expect(resolved).toBe(false);
		expect(images[0].loading).toBe('eager');
		expect(view.addEventListener).not.toHaveBeenCalled();
		images[0].complete = true; view.scrollHeight = 1200;
		advance(4); expect(await ready).toBe(true);
		expect(view.scrollTop).toBe(1200);
		expect(frames.size).toBe(0);
		view.scrollTop = 17; view.scrollHeight = 1800; advance(10);
		expect(view.scrollTop).toBe(17);
	});
	it('waits for fonts, async diagrams, metadata, and nonempty unmeasured rows', async () => {
		const {view, videos, rows, advance} = fixture();
		view.ownerDocument.fonts.status = 'loading'; view.pendingRender = true;
		const video = {readyState:0, HAVE_METADATA:1, error:null}; videos.push(video);
		rows.push({getBoundingClientRect:()=>({height:40})});
		let resolved = false;
		const ready = prepareLoadedChatLayout(view as any, new AbortController().signal).then(value => { resolved = true; return value; });
		advance(10); await Promise.resolve(); expect(resolved).toBe(false);
		view.ownerDocument.fonts.status = 'loaded'; view.pendingRender = false; video.readyState = 1;
		advance(10); await Promise.resolve(); expect(resolved).toBe(false);
		rows[0].getBoundingClientRect = () => ({height:0});
		advance(4); expect(await ready).toBe(true);
	});
	it('requires consecutive stable geometry and accepts completed error/fixed-size images', async () => {
		const {view, images, advance} = fixture();
		images.push({complete:true, hasAttribute:()=>false});
		images.push({complete:false, loading:'lazy', hasAttribute:()=>true});
		let resolved = false;
		const ready = prepareLoadedChatLayout(view as any, new AbortController().signal).then(value => { resolved = true; return value; });
		advance(2); view.clientHeight += 50; advance(2);
		await Promise.resolve(); expect(resolved).toBe(false);
		advance(2); expect(await ready).toBe(true);
	});
	it('stops completely when navigation aborts or the viewport is detached', async () => {
		for (const detach of [false, true]) {
			const {view, images, advance, frames} = fixture();
			images.push({complete:false, loading:'eager', hasAttribute:()=>false});
			const controller = new AbortController();
			const ready = prepareLoadedChatLayout(view as any, controller.signal);
			advance();
			if(detach) { view.isConnected = false; advance(); } else controller.abort();
			expect(await ready).toBe(false); expect(frames.size).toBe(0);
		}
	});
});
