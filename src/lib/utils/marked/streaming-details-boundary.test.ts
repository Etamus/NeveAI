import { describe, expect, it } from 'vitest';
import { lexChatMarkdown } from './chat-lexer';
import { prepareStreamingMarkdown } from './streaming-display';

const reasoning = '<details type="reasoning" done="false">\n<summary>Pensando...</summary>\n&gt; Thinking Process:\n&gt; **Analyze the request**\n</details>\n';

describe('Structured blocks after already-generated Markdown', () => {
	it.each([
		'### **Story**\n\nPrevious answer.\n\n***\n\nFinal paragraph?\n',
		'Intro.\n\n### **Story**\n\nA remembered *"quotation"*.\n\n***\n\nFinal paragraph?\n',
		'Previous answer.\n\n***\n\nFinal paragraph?\n',
		'Previous answer.\n\n___\n\nFinal paragraph?\n',
		'Previous answer.\n\n---\n\nFinal paragraph?\n',
		'Previous **bold** and *italic* answer.\n',
		'| Name | Value |\n| --- | --- |\n| One | Two |\n',
		'```html\n<details>literal example</details>\n```\n',
		'Inline `code` and $x^2$.\n',
		'An incomplete **format\n'
	])('does not rewrite the completed prefix or corrupt the following reasoning: %s', prefix => {
		const prepared = prepareStreamingMarkdown(prefix + reasoning);
		expect(prepared).toBe(prefix + reasoning);
		const tokens = lexChatMarkdown(prepared);
		expect(tokens.filter(token => token.type === 'details')).toHaveLength(1);
		expect(tokens.filter(token => token.type !== 'details').some(token => token.raw.includes('Thinking Process'))).toBe(false);
	});

	it('keeps consecutive reasoning/tool boundaries intact and repairs only the current answer', () => {
		const first = reasoning.replace('done="false"', 'done="true"');
		const tool = '<details type="tool_calls" name="search" done="true">\n<summary>Search</summary>\nResult\n</details>\n';
		const prefix = first + '\n### **Story**\n\n***\n\nFinal paragraph?\n';
		const prepared = prepareStreamingMarkdown(prefix + reasoning + tool + '\n**New answer');
		expect(prepared).toBe(prefix + reasoning + tool + '\n**New answer**');
		expect(lexChatMarkdown(prepared).filter(token => token.type === 'details')).toHaveLength(3);
	});
});
