import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('$lib/constants', () => ({ NEVEAI_BASE_URL: 'http://neve.test' }));
vi.mock('$lib/utils/chatRequestBody', () => ({ prepareChatRequestBody: vi.fn() }));
import { prepareChatRequestBody } from '$lib/utils/chatRequestBody';
import { chatCompletion, generateOpenAIChatCompletion } from './index';

afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });
describe('chat request transport', () => {
	it('does not send a generation stopped while its body was being prepared', async () => {
		let finish!: (value: string) => void;
		vi.mocked(prepareChatRequestBody).mockReturnValueOnce(new Promise(resolve => { finish = resolve; }));
		const fetch = vi.fn(); vi.stubGlobal('fetch', fetch);
		let active = true;
		const request = generateOpenAIChatCompletion('', {}, undefined, () => active);
		active = false; finish('{}');
		expect(await request).toBeNull();
		expect(fetch).not.toHaveBeenCalled();
	});
	it('preserves URL, authorization, cookies and all body bytes with a worker Blob', async () => {
		const input = { messages: [{ role: 'user', content: 'original' }], parent_message: { files: [] } };
		const blob = new Blob([JSON.stringify(input)], { type: 'application/json' });
		vi.mocked(prepareChatRequestBody).mockResolvedValue(blob);
		const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ task_id: 'task' })));
		vi.stubGlobal('fetch', fetch);
		expect(await generateOpenAIChatCompletion('token', input)).toEqual({ task_id: 'task' });
		expect(fetch).toHaveBeenCalledOnce();
		const [url, options] = fetch.mock.calls[0];
		expect(url).toBe('http://neve.test/api/chat/completions');
		expect(options).toMatchObject({ method: 'POST', headers: { Authorization: 'Bearer token', 'Content-Type': 'application/json' }, credentials: 'include', body: blob });
		expect(await options.body.text()).toBe(JSON.stringify(input));
	});
	it('preserves server and network errors without retrying a generation', async () => {
		vi.mocked(prepareChatRequestBody).mockResolvedValue('{}');
		const fetch = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({ detail: 'server error' }), { status: 503 })).mockRejectedValueOnce(new Error('offline'));
		vi.stubGlobal('fetch', fetch);
		await expect(generateOpenAIChatCompletion('', {})).rejects.toBe('server error');
		await expect(generateOpenAIChatCompletion('', {})).rejects.toThrow('offline');
		expect(fetch).toHaveBeenCalledTimes(2);
	});
	it('keeps the separately controlled streaming request and abort signal unchanged', async () => {
		const fetch = vi.fn().mockResolvedValue(new Response('stream'));
		vi.stubGlobal('fetch', fetch);
		const controller = new AbortController();
		const [response, returnedController] = await chatCompletion('token', { stream: true }, 'http://custom.test/api', controller);
		expect(returnedController).toBe(controller);
		expect(response).toBeInstanceOf(Response);
		expect(fetch.mock.calls[0]).toEqual(['http://custom.test/api/chat/completions', expect.objectContaining({ signal: controller.signal, body: '{"stream":true}' })]);
	});
});
