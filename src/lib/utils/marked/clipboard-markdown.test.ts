import { afterEach, describe, expect, it, vi } from 'vitest';
import { marked } from 'marked';
import { lexChatMarkdown } from './chat-lexer';
import { copyToClipboard } from '../index';

vi.mock('$lib/constants', () => ({ NEVEAI_BASE_URL: 'http://localhost' }));

class TestClipboardItem {
	constructor(public data: Record<string, Blob>) {}
}

function mockClipboard() {
	const write = vi.fn().mockResolvedValue(undefined);
	const writeText = vi.fn().mockResolvedValue(undefined);
	vi.stubGlobal('ClipboardItem', TestClipboardItem);
	vi.stubGlobal('navigator', { clipboard: { write, writeText } });
	return { write, writeText };
}

afterEach(() => {
	vi.unstubAllGlobals();
	vi.restoreAllMocks();
});

describe('formatted Markdown clipboard', () => {
	it('registers only once across concurrent/repeated copies and preserves rendered HTML', async () => {
		const { write } = mockClipboard();
		const source =
			'# Heading\n\n[1][2#part] <@user> $x$\n\n$$y^2$$\n\n| A |\n| - |\n| B |\n\n```js\nconst x = 1;\n```\n\n<details type="reasoning">\n<summary>Thinking</summary>\nBody\n</details>\n\n<span>Raw HTML</span>';
		// Ensure this test exercises the same shared chat extensions as the UI.
		expect(lexChatMarkdown(source).length).toBeGreaterThan(0);
		const expectedHtml = marked.parse(source);
		const use = vi.spyOn(marked, 'use');
		expect(
			await Promise.all(Array.from({ length: 25 }, () => copyToClipboard(source, null, true)))
		).toEqual(Array(25).fill(true));
		expect(use).toHaveBeenCalledTimes(2);
		const inlineCount = marked.defaults.extensions!.inline!.length;
		const blockCount = marked.defaults.extensions!.block!.length;
		const first = write.mock.calls[0][0][0] as TestClipboardItem;
		const html = await first.data['text/html'].text();
		expect(first.data['text/html'].type).toBe('text/html');
		expect(first.data['text/plain'].type).toBe('text/plain');
		expect(await first.data['text/plain'].text()).toBe(source);
		expect(html).toContain(expectedHtml);
		expect(html).toContain('<style>');
		expect(html).toContain('[1][2#part]');
		expect(html).toContain('<details type="reasoning">');
		expect(html).toContain('<span>Raw HTML</span>');
		for (const call of write.mock.calls) {
			expect(await (call[0][0] as TestClipboardItem).data['text/html'].text()).toBe(html);
		}
		await copyToClipboard(source, null, true);
		expect(use).toHaveBeenCalledTimes(2);
		expect(marked.defaults.extensions!.inline).toHaveLength(inlineCount);
		expect(marked.defaults.extensions!.block).toHaveLength(blockCount);
	});

	it('uses supplied HTML verbatim without configuring Markdown', async () => {
		const { write } = mockClipboard();
		const use = vi.spyOn(marked, 'use');
		const html = '<section><strong>Provided</strong></section>';
		expect(await copyToClipboard('Plain', html, true)).toBe(true);
		const item = write.mock.calls[0][0][0] as TestClipboardItem;
		expect(await item.data['text/html'].text()).toBe(html);
		expect(await item.data['text/plain'].text()).toBe('Plain');
		expect(use).not.toHaveBeenCalled();
	});

	it('retains the plain text fallback when rich clipboard writing fails', async () => {
		const { write, writeText } = mockClipboard();
		write.mockRejectedValue(new Error('Clipboard denied'));
		vi.spyOn(console, 'error').mockImplementation(() => {});
		vi.spyOn(console, 'log').mockImplementation(() => {});
		expect(await copyToClipboard('Fallback [1]', '<p>Fallback [1]</p>', true)).toBe(true);
		expect(writeText).toHaveBeenCalledWith('Fallback [1]');
	});
});
