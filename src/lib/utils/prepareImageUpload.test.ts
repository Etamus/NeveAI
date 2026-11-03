import { afterEach, describe, expect, it, vi } from 'vitest';

const state = vi.hoisted(() => ({
	workers: [] as any[],
	canvases: [] as any[],
	compress: vi.fn()
}));
vi.mock('$lib/workers/image-compression.worker?worker', () => ({
	default: class {
		onmessage: any;
		onerror: any;
		postMessage = vi.fn();
		terminate = vi.fn();
		constructor() {
			state.workers.push(this);
		}
	}
}));
vi.mock('$lib/utils', () => ({ compressImage: state.compress }));

afterEach(() => {
	vi.unstubAllGlobals();
	vi.restoreAllMocks();
	vi.useRealTimers();
	vi.resetModules();
	state.workers = [];
	state.canvases = [];
	state.compress.mockReset();
});

async function setup() {
	vi.stubGlobal('Worker', class {});
	vi.stubGlobal(
		'OffscreenCanvas',
		class {
			constructor(
				public width: number,
				public height: number
			) {
				state.canvases.push(this);
			}
			getContext = () => ({ drawImage: vi.fn() });
			transferToImageBitmap = () => ({ close: vi.fn() });
		}
	);
	vi.stubGlobal(
		'Image',
		class {
			naturalWidth = 3840;
			naturalHeight = 2160;
			decode = vi.fn(async () => {});
		}
	);
	vi.stubGlobal('document', {
		createElement: vi.fn(() => ({
			width: 0,
			height: 0,
			getContext: () => ({ drawImage: vi.fn() })
		}))
	});
	vi.stubGlobal(
		'createImageBitmap',
		vi.fn(async () => ({ close: vi.fn() }))
	);
	vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:source');
	vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {});
	state.compress.mockResolvedValue('data:image/png;base64,AA==');
	vi.stubGlobal(
		'fetch',
		vi.fn(async () => ({ blob: async () => new Blob(['compressed'], { type: 'image/png' }) }))
	);
	return import('./prepareImageUpload');
}

describe('image upload preparation', () => {
	it('returns the identical file without any conversion or worker by default', async () => {
		const { prepareImageUpload } = await setup();
		const file = new File(['original'], 'photo.png', { type: 'image/png' });
		expect(await prepareImageUpload(file, null, null)).toBe(file);
		expect(state.workers).toHaveLength(0);
		expect(state.compress).not.toHaveBeenCalled();
		expect(URL.createObjectURL).not.toHaveBeenCalled();
	});
	it('compresses in a worker and preserves name, format and date', async () => {
		const { prepareImageUpload } = await setup();
		const file = new File(['original'], 'photo.jpg', { type: 'image/jpeg', lastModified: 123 });
		const pending = prepareImageUpload(file, 1024, 1024);
		const worker = state.workers[0];
		await vi.waitFor(() => expect(worker.postMessage).toHaveBeenCalledOnce());
		expect(worker.postMessage).toHaveBeenCalledWith(
			{ image: expect.anything(), mimeType: 'image/jpeg' },
			[expect.anything()]
		);
		const canvas = state.canvases[0];
		expect([canvas.width, canvas.height]).toEqual([1024, 576]);
		worker.onmessage({ data: { blob: new Blob(['compressed'], { type: 'image/jpeg' }) } });
		const result = await pending;
		expect([result.name, result.type, result.lastModified]).toEqual([
			'photo.jpg',
			'image/jpeg',
			123
		]);
		expect(await result.text()).toBe('compressed');
		expect(worker.terminate).toHaveBeenCalledOnce();
		expect(state.compress).not.toHaveBeenCalled();
	});
	it('does not re-encode an image already within its bounds', async () => {
		const { prepareImageUpload } = await setup();
		vi.stubGlobal(
			'Image',
			class {
				naturalWidth = 960;
				naturalHeight = 540;
				decode = vi.fn(async () => {});
			}
		);
		const file = new File(['small'], 'small.jpg', { type: 'image/jpeg' });
		const pending = prepareImageUpload(file, 1024, 1024);
		expect(await pending).toBe(file);
		expect(state.workers[0].terminate).toHaveBeenCalledOnce();
		expect(state.workers[0].postMessage).not.toHaveBeenCalled();
	});
	it.each(['unsupported', 'worker-error', 'decode-error', 'timeout'])(
		'retains native fallback for %s',
		async (failure) => {
			const { prepareImageUpload } = await setup();
			vi.useFakeTimers();
			if (failure === 'unsupported') vi.stubGlobal('Worker', undefined);
			const file = new File(['original'], 'photo.png', { type: 'image/png' });
			const pending = prepareImageUpload(file, 1024, 1024);
			if (failure !== 'unsupported') {
				await vi.waitFor(() => expect(state.workers[0].postMessage).toHaveBeenCalledOnce());
			}
			if (failure === 'worker-error') state.workers[0].onerror();
			if (failure === 'decode-error') state.workers[0].onmessage({ data: { failed: true } });
			if (failure === 'timeout') await vi.advanceTimersByTimeAsync(10000);
			expect((await pending).type).toBe('image/png');
			expect(state.compress).toHaveBeenCalledWith('blob:source', 1024, 1024, 'image/png');
			expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:source');
			if (state.workers[0]) expect(state.workers[0].terminate).toHaveBeenCalledOnce();
		}
	);
	it('cleans up the fallback URL even if compression fails', async () => {
		const { prepareImageUpload } = await setup();
		vi.stubGlobal('Worker', undefined);
		state.compress.mockRejectedValue(new Error('decode failed'));
		await expect(prepareImageUpload(new File(['bad'], 'bad.png'), 512, null)).rejects.toThrow(
			'decode failed'
		);
		expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:source');
	});
});
