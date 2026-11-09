import { describe, expect, it, vi } from 'vitest';
import { Marked, marked, type MarkedExtension } from 'marked';
import { createChatMarkdownParser, lexChatMarkdown } from './chat-lexer';
import detailsExtension from './extension';
import katexExtension from './katex-extension';
import citationExtension from './citation-extension';
import footnoteExtension from './footnote-extension';
import { disableSingleTilde } from './strikethrough-extension';
import { mentionExtension } from './mention-extension';

// Independent reproduction of Markdown.svelte's original registration order.
const reference = new Marked();
const options = { throwOnError: false, breaks: true };
reference.use(katexExtension(options) as MarkedExtension);
reference.use(detailsExtension(options) as MarkedExtension);
reference.use(citationExtension());
reference.use(footnoteExtension());
reference.use(disableSingleTilde as MarkedExtension);
reference.use({
	extensions: ['@', '#', '$'].map((triggerChar) => mentionExtension({ triggerChar }))
});

const documents = [
	'# Heading\n\nParagraph **bold**, ~literal~ and ~~deleted~~.\n\nTitle\n---\n\n> quote\n>\n> - [x] task\n> - item\n',
	'Before [site][ref].\n\n| A | B |\n| :- | -: |\n| [site][ref] | $x$ |\n\n[ref]: https://example.com "Title"\n',
	'```ts\nconst x = "[1] $x$ <@user>";\n\n```\n\n~~~text\nmore\n~~~\n\n    indented\n\n`inline $x$`\n',
	String.raw`Math $x$ and \(y\).

$$
x^2 + y^2
$$

\[z^2\]

\begin{equation}a=b\end{equation}

[1][2,3#part] [^note] <@user|User> <#file/path|File> <$tool|Tool>`,
	'<details type="reasoning">\n<summary>Thinking</summary>\n\n$x$ [1] <@user>\n<details>\nNested\n</details>\n</details>\n\n<details type="tool_calls" calls="[]">\n<summary>Tool</summary>\nBody\n</details>\n',
	'> [!NOTE]\n> $x$ [2] <#file>\n\n<div>\nHTML\n\n</div>\n\n[link](https://example.com)\n'
];

describe('chat Markdown lexer', () => {
	it('recovers missing delimiter pipes as in the saved GOT response', () => {
		const source = '| Temporada | Titulo | Melhor Para | Pontos Fortes | Atencao |\n| :--- | :--- | :--- | :--- :--- |\n| 1 | Inicio | Mundo | **Detalhes**<br>Mais | Ritmo |';
		const tokens = lexChatMarkdown(source);
		expect(tokens[0].type).toBe('table');
		if (tokens[0].type !== 'table') throw new Error('Expected recovered table');
		expect(tokens[0].header).toHaveLength(5);
		expect(tokens[0].rows[0]).toHaveLength(5);
		expect(tokens[0].rows[0][3].text).toBe('**Detalhes**<br>Mais');
		expect(tokens[0].raw).toBe(source);
	});
	it.each([
		'```markdown\n| A | B | C |\n| --- | --- --- |\n| 1 | 2 | 3 |\n```',
		'~~~markdown\n| A | B | C |\n| --- | --- --- |\n~~~',
		'    | A | B | C |\n    | --- | --- --- |\n',
		'<pre>\n| A | B | C |\n| --- | --- --- |\n</pre>\n',
		'| A | B |\n| --- | --- --- |\n| 1 | 2 |',
		'| A | B |\n| not --- | --- --- |',
		'| A | B |\n| --- | --- |\n| literal --- --- | B |'
	])('does not rewrite code or ambiguous/valid Markdown: %s', (source) => {
		expect(lexChatMarkdown(source)).toEqual(reference.lexer(source));
	});
	it.each(['\n', '\r\n'])('recovers tables inside blockquotes without consuming following text (%j)', (newline) => {
		const source = '> | A | B | C |\n> | --- | --- --- |\n> | 1 | 2 | 3 |\n\nAfter the table.'.replaceAll('\n', newline);
		const tokens = lexChatMarkdown(source);
		expect(tokens[0].type).toBe('blockquote');
		if (tokens[0].type !== 'blockquote') throw new Error('Expected blockquote');
		expect(tokens[0].tokens[0].type).toBe('table');
		expect(tokens.at(-1)?.type).toBe('paragraph');
	});
	it.each(documents)('matches original configuration for every streamed prefix: %s', (source) => {
		const parse = createChatMarkdownParser();
		for (let end = 0; end <= source.length; end++) {
			const prefix = source.slice(0, end);
			expect(parse(prefix)).toEqual(reference.lexer(prefix));
		}
		expect(parse(source)).toEqual(reference.lexer(source));
	});

	it('handles replacements, truncations, clearing and replay, not just appends', () => {
		const parse = createChatMarkdownParser();
		for (const source of [...documents, '', '```open\ntext', 'revised', documents[0], '']) {
			expect(parse(source)).toEqual(reference.lexer(source));
		}
	});

	it('invalidates earlier inline tokens when forward definitions change', () => {
		const parse = createChatMarkdownParser();
		const source = '[label][ref]\n\n';
		const before = parse(source);
		const after = parse(source + '[ref]: /first\n');
		expect(after[0].raw).toBe(before[0].raw);
		expect(after[0]).not.toBe(before[0]);
		expect(after).toEqual(reference.lexer(source + '[ref]: /first\n'));
		const revised = parse(source + '[ref]: /second\n');
		expect(revised[0]).not.toBe(after[0]);
		expect(revised.links.ref.href).toBe('/second');
	});

	it('reuses only structurally equal tokens and skips identical source', () => {
		const lexer = vi.fn(lexChatMarkdown);
		const parse = createChatMarkdownParser(lexer);
		const first = parse('# Stable\n\nTail');
		const next = parse('# Stable\n\nTail grows');
		expect(next[0]).toBe(first[0]);
		expect(next[next.length - 1]).not.toBe(first[first.length - 1]);
		expect(parse('# Stable\n\nTail grows')).toBe(next);
		expect(lexer).toHaveBeenCalledTimes(2);
	});

	it('does not grow global extension chains on parser creation (message remounts)', () => {
		const extensions = marked.defaults.extensions!;
		const inline = extensions.inline!.length;
		const block = extensions.block!.length;
		const del = marked.defaults.tokenizer!.del;
		for (let i = 0; i < 100; i++) {
			expect(createChatMarkdownParser()('$x$ [1] <@user>')).toEqual(
				reference.lexer('$x$ [1] <@user>')
			);
		}
		expect(extensions.inline).toHaveLength(inline);
		expect(extensions.block).toHaveLength(block);
		expect(marked.defaults.tokenizer!.del).toBe(del);
	});

	it('keeps reference definitions isolated between concurrent message parsers', () => {
		const a = createChatMarkdownParser();
		const b = createChatMarkdownParser();
		a('[label][ref]\n\n[ref]: /a');
		expect(b('[label][ref]')).toEqual(reference.lexer('[label][ref]'));
		expect(a('[label][ref]\n\n[ref]: /b')).toEqual(reference.lexer('[label][ref]\n\n[ref]: /b'));
	});

	it('isolates the main lexer from other consumers changing global options', () => {
		const gfm = marked.defaults.gfm;
		const source = '| A |\n| - |\n| B |';
		try {
			marked.setOptions({ gfm: false });
			expect(marked.lexer(source)[0].type).not.toBe('table');
			expect(lexChatMarkdown(source)).toEqual(reference.lexer(source));
			expect(lexChatMarkdown(source)[0].type).toBe('table');
		} finally {
			marked.setOptions({ gfm });
		}
	});

	it('preserves custom tokens, including tools, rather than only matching plain Markdown', () => {
		const types = new Set<string>();
		for (const source of documents) {
			reference.walkTokens(lexChatMarkdown(source), (token) => {
				types.add(token.type);
			});
		}
		for (const type of [
			'details',
			'mention',
			'citation',
			'footnote',
			'inlineKatex',
			'blockKatex',
			'table',
			'code'
		]) {
			expect(types.has(type), type).toBe(true);
		}
	});
});
