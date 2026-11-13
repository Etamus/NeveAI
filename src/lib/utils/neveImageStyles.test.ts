import { readFileSync, existsSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

const input = readFileSync('src/lib/components/chat/MessageInput.svelte', 'utf8');
const chat = readFileSync('src/lib/components/chat/Chat.svelte', 'utf8');
describe('Retired Neve Image 1.5', () => {
	it('removes the model and styles without removing the active special modes', () => {
		expect(input).not.toContain('Neve Image 1.5');
		expect(input).not.toContain('image-style-control');
		expect(input).not.toContain('preloadImageStyleThumbnails');
		for (const model of ['qwen_image_2s', 'qwen_image_2_1_official', 'minimax_h3_image']) expect(input).toContain(model);
		expect(input).toContain('<ImageModeSelector');
	});
	it('discards old saved styles and defaults to the active Qwen model', () => {
		expect(chat).toContain("localStorage.removeItem('neveai.imageStyle')");
		expect(chat).toContain("| 'qwen_image_2_1_official' = 'qwen_image_2s'");
	});
	it.each(['realista','espontaneo','minimalista','fantasia','manga','pixelado','poligonal','quadrinhos','arcano'])('removes the exclusive %s preview', name => {
		expect(existsSync(`static/static/${name}.webp`)).toBe(false);
	});
});
