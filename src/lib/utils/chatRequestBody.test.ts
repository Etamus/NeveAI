import { afterEach, describe, expect, it, vi } from 'vitest';

const state = vi.hoisted(() => ({ workers: [] as any[], mode: 'success' }));
vi.mock('$lib/workers/chat-request.worker?worker', () => ({ default: class {
	onmessage: any; onerror: any; onmessageerror: any;
	terminate = vi.fn();
	constructor() {
		if (state.mode === 'constructor') throw new Error('Worker unavailable');
		state.workers.push(this);
	}
	postMessage(value: object) {
		if (state.mode === 'clone') throw new Error('Cannot clone');
		queueMicrotask(async () => {
			if (state.mode === 'error') this.onerror({ preventDefault: vi.fn() });
			else if (state.mode === 'messageerror') this.onmessageerror();
			else if (state.mode !== 'timeout') {
				const { unpackInlineImages } = await import('./inlineImageTransfer');
				this.onmessage({ data: state.mode === 'failed' ? { failed: true } : { body: new Blob([JSON.stringify(await unpackInlineImages(structuredClone(value)))], { type: 'application/json' }) } });
			}
		});
	}
} }));

afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); vi.resetModules(); state.workers = []; state.mode = 'success'; });
const largeImage = () => ({ messages: [{ role: 'user', content: [{ type: 'text', text: 'Edit' }, { type: 'image_url', image_url: { url: 'data:image/png;base64,' + 'A'.repeat(1024 * 1024) } }] }], parent_message: { content: 'Edit', files: [] }, params: { stop: undefined, temperature: .7 }, features: { stable_diffusion: true } });
async function setup() { vi.stubGlobal('Worker', class {}); return import('./chatRequestBody'); }

describe('large inline image request body', () => {
	it('preserves every JSON byte in a Blob, without HTTP or uploads', async () => {
		const { prepareChatRequestBody } = await setup();
		const input = largeImage(), before = JSON.stringify(input);
		const result = await prepareChatRequestBody(input);
		expect(result).toBeInstanceOf(Blob);
		expect(await (result as Blob).text()).toBe(before);
		expect(JSON.stringify(input)).toBe(before);
		expect(state.workers[0].terminate).toHaveBeenCalledOnce();
	});
	it('keeps text, server URLs and small inline images on the existing path', async () => {
		const { prepareChatRequestBody } = await setup();
		for (const content of ['text', [{ type: 'image_url', image_url: { url: '/api/v1/files/reference/content' } }], [{ type: 'image_url', image_url: { url: 'data:image/png;base64,AA==' } }], [{ type: 'image_url', image_url: { url: 'data:image/svg+xml;utf8,' + '\ud800'.repeat(1024 * 1024) } }]]) {
			const body = { messages: [{ content }] };
			expect(await prepareChatRequestBody(body)).toBe(JSON.stringify(body));
		}
		expect(state.workers).toHaveLength(0);
	});
	it('falls back when workers are unsupported', async () => {
		const { prepareChatRequestBody } = await setup();
		vi.stubGlobal('Worker', undefined);
		const body = largeImage();
		expect(await prepareChatRequestBody(body)).toBe(JSON.stringify(body));
	});
	for (const mode of ['constructor', 'clone', 'error', 'messageerror', 'failed', 'timeout']) {
		it(`falls back safely on ${mode}, before any request is sent`, async () => {
			const { prepareChatRequestBody } = await setup(); state.mode = mode;
			vi.useFakeTimers();
			const body = largeImage(), promise = prepareChatRequestBody(body);
			await vi.runAllTimersAsync();
			expect(await promise).toBe(JSON.stringify(body));
			if (state.workers.length) expect(state.workers[0].terminate).toHaveBeenCalledOnce();
		});
	}
	it('preserves custom toJSON and getter behavior without cloning', async () => {
		const { prepareChatRequestBody } = await setup();
		for (const extra of [{ toJSON() { return 'custom'; } }, new Date(0), new Uint8Array([1, 2])]) {
			const body = { ...largeImage(), extra };
			expect(await prepareChatRequestBody(body)).toBe(JSON.stringify(body));
		}
		const getter = vi.fn(() => []), body = { get messages() { return getter(); } };
		expect(await prepareChatRequestBody(body)).toBe('{"messages":[]}');
		expect(getter).toHaveBeenCalledOnce();
		expect(state.workers).toHaveLength(0);
	});
	it('preserves serialization failures and supports shared plain objects', async () => {
		const { prepareChatRequestBody } = await setup();
		const body: any = largeImage(); body.cycle = body;
		await expect(prepareChatRequestBody(body)).rejects.toThrow();
		delete body.cycle;
		const shared = { text: 'same' }; body.first = shared; body.second = shared;
		expect(await (await prepareChatRequestBody(body) as Blob).text()).toBe(JSON.stringify(body));
	});
});
