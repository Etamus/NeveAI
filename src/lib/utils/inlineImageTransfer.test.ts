import { describe, expect, it } from 'vitest';
import { packInlineImages, unpackInlineImages } from './inlineImageTransfer';

describe('inline image worker transfer', () => {
	it('shares one Blob handle for repeated images and restores exact JSON', async () => {
		const source = 'data:image/png;base64,' + 'A'.repeat(1024 * 1024);
		const input = { messages: [{ content: [{ image_url: { url: source } }] }], parent_message: { files: [{ url: source }] }, params: { optional: undefined, value: null }, unicode: '\u00e1\u65e5\ud83d\ude42' };
		const packed: any = packInlineImages(input);
		expect(packed.messages[0].content[0].image_url.url).toBeInstanceOf(Blob);
		expect(packed.messages[0].content[0].image_url.url).toBe(packed.parent_message.files[0].url);
		expect(JSON.stringify(await unpackInlineImages(structuredClone(packed)))).toBe(JSON.stringify(input));
		expect(input.parent_message.files[0].url).toBe(source);
	});
	it('preserves key order, special keys, sparse arrays and non-image values', async () => {
		const input = JSON.parse('{"__proto__":{"safe":true},"2":2,"1":1,"last":null}');
		input.sparse = [undefined, , null, -0, Number.NaN];
		input.text = 'ordinary';
		expect(JSON.stringify(await unpackInlineImages(structuredClone(packInlineImages(input))))).toBe(JSON.stringify(input));
		expect(Object.prototype).not.toHaveProperty('safe');
	});
});
