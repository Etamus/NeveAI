import {afterEach,describe,expect,it,vi} from 'vitest';
const state=vi.hoisted(()=>({workers:[] as any[]}));
vi.mock('$lib/workers/attachment-thumbnail.worker?worker',()=>({default:class {
	onmessage:any;onerror:any;postMessage=vi.fn();terminate=vi.fn();
	constructor(){state.workers.push(this);}
}}));
afterEach(()=>{vi.unstubAllGlobals();vi.restoreAllMocks();vi.resetModules();state.workers=[];});
async function setup(){
	vi.stubGlobal('Worker',class {});vi.stubGlobal('OffscreenCanvas',class {});
	vi.stubGlobal('location',{origin:'http://localhost'});
	vi.spyOn(URL,'createObjectURL').mockImplementation(()=>`blob:test-${Math.random()}`);
	vi.spyOn(URL,'revokeObjectURL').mockImplementation(()=>{});
	return import('./attachmentThumbnails');
}
describe('attachment preview cache',()=>{
	it('cancels unreferenced queued work, but not a shared or immediately remounted preview',async()=>{
		const {acquireAttachmentThumbnail}=await setup();
		const first=acquireAttachmentThumbnail('/cancel.png');
		const shared=acquireAttachmentThumbnail('/cancel.png');
		const worker=state.workers[0];
		first.release();await Promise.resolve();
		expect(worker.postMessage).toHaveBeenCalledTimes(1);
		shared.release();
		const remount=acquireAttachmentThumbnail('/cancel.png');
		await Promise.resolve();expect(worker.postMessage).toHaveBeenCalledTimes(1);
		remount.release();await Promise.resolve();
		expect(worker.postMessage).toHaveBeenLastCalledWith({cancel:1});
		expect(await remount.ready).toBe('/cancel.png');
		const next=acquireAttachmentThumbnail('/cancel.png');
		expect(worker.postMessage).toHaveBeenLastCalledWith({id:2,source:'/cancel.png'});
		worker.onmessage({data:{id:2,blob:new Blob(['valid'])}});
		expect(await next.ready).toMatch(/^blob:/);next.release();
	});
	it('shares one decode across mounts and keeps referenced previews alive',async()=>{
		const {acquireAttachmentThumbnail}=await setup();
		const first=acquireAttachmentThumbnail('/image.png'),second=acquireAttachmentThumbnail('/image.png');
		const worker=state.workers[0],id=worker.postMessage.mock.calls[0][0].id;
		expect(worker.postMessage).toHaveBeenCalledTimes(1);
		worker.onmessage({data:{id,blob:new Blob(['image'])}});
		expect(await first.ready).toBe(await second.ready);first.release();
		expect(URL.revokeObjectURL).not.toHaveBeenCalled();
		const again=acquireAttachmentThumbnail('/image.png');expect(await again.ready).toBe(await second.ready);
		expect(worker.postMessage).toHaveBeenCalledTimes(1);again.release();second.release();
	});
	it('bounds the cache and never revokes a mounted thumbnail',async()=>{
		const {acquireAttachmentThumbnail}=await setup();
		const held=acquireAttachmentThumbnail('/held.png');const worker=state.workers[0];
		worker.onmessage({data:{id:1,blob:new Blob(['held'])}});const heldUrl=await held.ready;
		for(let i=0;i<30;i++){
			const entry=acquireAttachmentThumbnail(`/image-${i}.png`);
			const id=worker.postMessage.mock.calls.at(-1)[0].id;
			worker.onmessage({data:{id,blob:new Blob(['image'])}});await entry.ready;entry.release();
		}
		expect(URL.revokeObjectURL).toHaveBeenCalled();expect(URL.revokeObjectURL).not.toHaveBeenCalledWith(heldUrl);held.release();
	});
	it('falls back to the original on worker failure and for cross-origin sources',async()=>{
		const {acquireAttachmentThumbnail}=await setup();
		const first=acquireAttachmentThumbnail('/original.png');state.workers[0].onerror();
		expect(await first.ready).toBe('/original.png');first.release();
		const remote=acquireAttachmentThumbnail('https://example.com/photo.png');
		expect(await remote.ready).toBe('https://example.com/photo.png');remote.release();
	});
});
