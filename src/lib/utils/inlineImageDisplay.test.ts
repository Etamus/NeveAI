import { afterEach, describe, expect, it, vi } from 'vitest';

afterEach(() => { vi.restoreAllMocks(); vi.resetModules(); });
async function setup() {
	vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:original');
	vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {});
	return import('./inlineImageDisplay');
}

describe('temporary inline image display ownership', () => {
	it('uses the original Blob without decoding or changing its bytes', async () => {
		const { registerInlineImageDisplay, inlineImageDisplaySource } = await setup();
		const blob = new Blob([new Uint8Array([1, 2, 3])], { type: 'image/gif' });
		const owner = registerInlineImageDisplay('data:image/gif;base64,AQID', blob)!;
		expect(URL.createObjectURL).toHaveBeenCalledWith(blob);
		expect(inlineImageDisplaySource('data:image/gif;base64,AQID')).toBe('blob:original');
		expect([...new Uint8Array(await blob.arrayBuffer())]).toEqual([1, 2, 3]);
		owner.release(); await Promise.resolve();
		expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:original');
	});
	it('hands ownership from composer to message and preview without early revocation', async () => {
		const { registerInlineImageDisplay, acquireInlineImageDisplay, inlineImageDisplaySource } = await setup();
		const source = 'data:image/png;base64,AQID';
		const composer = registerInlineImageDisplay(source, new Blob(['original']))!;
		composer.release();
		const message = acquireInlineImageDisplay(source);
		await Promise.resolve();
		expect(URL.revokeObjectURL).not.toHaveBeenCalled();
		const duplicate = acquireInlineImageDisplay(source);
		message.release(); message.release(); await Promise.resolve();
		expect(URL.revokeObjectURL).not.toHaveBeenCalled();
		duplicate.release(); await Promise.resolve();
		expect(URL.revokeObjectURL).toHaveBeenCalledOnce();
		expect(inlineImageDisplaySource(source)).toBe(source);
	});
	it('reuses identical references and releases removed composer images', async () => {
		const { registerInlineImageDisplay } = await setup();
		const source = 'data:image/png;base64,AQID', blob = new Blob(['original']);
		const first = registerInlineImageDisplay(source, blob)!, second = registerInlineImageDisplay(source, blob)!;
		expect(URL.createObjectURL).toHaveBeenCalledOnce();
		first.release(); await Promise.resolve();
		expect(URL.revokeObjectURL).not.toHaveBeenCalled();
		second.release(); await Promise.resolve();
		expect(URL.revokeObjectURL).toHaveBeenCalledOnce();
	});
	it('preserves ordinary URLs and falls back when Blob URLs are unsupported', async () => {
		const { registerInlineImageDisplay, acquireInlineImageDisplay } = await setup();
		expect(registerInlineImageDisplay('/file.png', new Blob())).toBeUndefined();
		expect(acquireInlineImageDisplay('/file.png').url).toBe('/file.png');
		vi.mocked(URL.createObjectURL).mockImplementation(() => { throw Error('Unavailable'); });
		expect(registerInlineImageDisplay('data:image/png;base64,AQID', new Blob())).toBeUndefined();
		expect(acquireInlineImageDisplay('data:image/png;base64,AQID').url).toBe('data:image/png;base64,AQID');
	});
});
