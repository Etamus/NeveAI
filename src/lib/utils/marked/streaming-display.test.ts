import { describe, expect, it } from 'vitest';
import { lexChatMarkdown } from './chat-lexer';
import { prepareStreamingMarkdown, stabilizeStreamingBlocks } from './streaming-display';

describe('streaming display preparation', () => {
	it.each(['**Analyze', '*Analyze', '~~Analyze', '`Analyze'])('does not close reasoning syntax outside details: %s', text => {
		const source = `<details type="reasoning" done="false">\n<summary>Thinking</summary>\n&gt; ${text}\n</details>`;
		expect(prepareStreamingMarkdown(source)).toBe(source);
	});
	it('repairs the answer independently of a preceding reasoning block', () => {
		const details = '<details type="reasoning" done="false">\n<summary>Thinking</summary>\n&gt; **Analyze\n</details>';
		expect(prepareStreamingMarkdown(details + '\n\n**Answer')).toBe(details + '\n\n**Answer**');
	});
	it('preserves nested details and literal details inside fenced code', () => {
		const nested = '<details type="tool_calls">\n<summary>Tool</summary>\n<details type="reasoning">\n**open\n</details>\n</details>';
		expect(prepareStreamingMarkdown(nested + '\n\n*answer')).toBe(nested + '\n\n*answer*');
		const code = '```html\n<details>\n**literal\n</details>\n```';
		expect(prepareStreamingMarkdown(code)).toBe(code);
	});
	it('does not repair an unfinished custom details block outside its body', () => {
		const source = '<details type="reasoning" done="false">\n<summary>Thinking</summary>\n**open';
		expect(prepareStreamingMarkdown(source)).toBe(source);
	});
	it.each(['**bold', '*italic', '~~deleted', '`code'])('formats an open inline span: %s', source => {
		const tokens = lexChatMarkdown(prepareStreamingMarkdown(source));
		expect(tokens[0].type).toBe('paragraph');
		expect((tokens[0] as any).tokens[0].type).not.toBe('text');
	});
	it.each(['```js\nconst s = "**x"; ', '~~~text\n*literal', '```python\nprint("hello")'])('does not rewrite open code: %s', source => {
		expect(prepareStreamingMarkdown(source)).toBe(source);
	});
	it('preserves whitespace and custom controls', () => {
		expect(prepareStreamingMarkdown('plain ')).toBe('plain ');
		expect(prepareStreamingMarkdown('plain  ')).toBe('plain  ');
		const details = '<details type="reasoning" done="false">\n<summary>Thinking</summary>\nText';
		expect(prepareStreamingMarkdown(details)).toBe(details);
		expect(prepareStreamingMarkdown('$10 and [1] <@user>')).toBe('$10 and [1] <@user>');
	});
	it('waits for a confirmed table header, without changing previous blocks', () => {
		const intro = 'Stable paragraph.\n\n';
		const pending = lexChatMarkdown(intro + '| Name | Value |\n| --');
		const visible = stabilizeStreamingBlocks(pending);
		expect(visible.some(t => t.raw.includes('| Name'))).toBe(false);
		expect(visible[0]).toBe(pending[0]);
		const confirmed = lexChatMarkdown(intro + '| Name | Value |\n| --- | --- |\n| A | 1 |');
		expect(stabilizeStreamingBlocks(confirmed)).toBe(confirmed);
		expect(confirmed.some(t => t.type === 'table')).toBe(true);
	});
	it('holds an unfinished fence language and preserves forward references', () => {
		const pending = lexChatMarkdown('[link][ref]\n\n[ref]: /target\n\n```py');
		const visible = stabilizeStreamingBlocks(pending);
		expect(visible.some(t => t.type === 'code')).toBe(false);
		expect(visible.links).toBe(pending.links);
		const ready = lexChatMarkdown('```python\nprint(1)');
		expect(stabilizeStreamingBlocks(ready)).toBe(ready);
	});
	it('shows an incomplete link label without rendering the temporary URL', () => {
		expect(prepareStreamingMarkdown('[link text](https://example.com')).toBe('link text');
		expect(prepareStreamingMarkdown('[link text](https://example.com)')).toBe('[link text](https://example.com)');
		expect(prepareStreamingMarkdown('![image](https://example.com')).not.toContain('streamdown:');
	});
	it('waits for a complete display-math block instead of showing raw math lines', () => {
		const pending = stabilizeStreamingBlocks(lexChatMarkdown('$$\nx^2 + y^2'));
		expect(pending).toHaveLength(0);
		const ready = lexChatMarkdown('$$\nx^2 + y^2\n$$');
		expect(stabilizeStreamingBlocks(ready)).toBe(ready);
	});
});
