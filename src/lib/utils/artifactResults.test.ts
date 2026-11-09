import { describe, it, expect } from 'vitest';
import { extractArtifactResults, getConversationArtifacts } from './artifactResults';

describe('completed artifact results', () => {
	it('detects raw documents without duplicating their scripts or styles', () => {
		const html =
			'<!DOCTYPE html><html lang="pt-BR"><head><style>body{color:red}</style></head><body><script>window.demo=1</script></body></html>';
		expect(extractArtifactResults(html)[0].content).toBe(html);
		expect(extractArtifactResults('<svg viewBox="0 0 10 10"></svg>')[0].type).toBe('svg');
	});
	it('retains only valid explicit previews on the current branch', () => {
		const preview = extractArtifactResults('```html\n<h1>Incomplete</h1>\n```', 'a')[0];
		const history = {
			currentId: 'a',
			messages: {
				a: {
					id: 'a',
					role: 'assistant',
					parentId: null,
					content: '```html\n<h1>Incomplete</h1>\n',
					done: true
				}
			}
		};
		expect(getConversationArtifacts(history, [preview])).toEqual([preview]);
		history.messages.a.content = 'Replaced';
		expect(getConversationArtifacts(history, [preview])).toEqual([]);
	});
	it('combines HTML, CSS and JS into one downloadable preview', () => {
		const [result] = extractArtifactResults(
			'```html\n<h1>Hello</h1>\n```\n```css\nh1{color:red}\n```\n```js\ndocument.title="Demo"\n```',
			'a'
		);
		expect(result.filename).toBe('artifact.html');
		expect(result.content).toContain('<h1>Hello</h1>');
		expect(result.content).toContain('h1{color:red}');
		expect(result.content).toContain('document.title="Demo"');
	});
	it('preserves full documents and inserts dependencies inside them', () => {
		const [result] = extractArtifactResults(
			'```html\n<html lang="pt"><head></head><body>Demo</body></html>\n```\n```css\nbody{color:red}\n```'
		);
		expect(result.content.match(/<html/g)).toHaveLength(1);
		expect(result.content.indexOf('<style>')).toBeLessThan(result.content.indexOf('</head>'));
	});
	it('excludes reasoning, ordinary code and nonvisual responses', () => {
		expect(
			extractArtifactResults(
				'<details type="reasoning"><summary>Thought</summary>\n```html\n<h1>Hidden</h1>\n```\n</details>'
			)
		).toEqual([]);
		for (const content of ['Hello', '```python\nprint("hello")\n```', '```css\nbody{}\n```'])
			expect(extractArtifactResults(content)).toEqual([]);
	});
	it('keeps SVG previews separate', () => {
		const results = extractArtifactResults(
			'```svg\n<svg viewBox="0 0 20 20"></svg>\n```\n```xml\n<svg></svg>\n```',
			'a'
		);
		expect(results).toHaveLength(2);
		expect(results.every((result) => result.type === 'svg')).toBe(true);
		expect(results[0].id).not.toBe(results[1].id);
	});
	it('uses only completed assistant messages on the active branch', () => {
		const code = '```html\n<h1>Demo</h1>\n```';
		const history = {
			currentId: 'b',
			messages: {
				a: { id: 'a', parentId: null, role: 'user', content: code },
				b: { id: 'b', parentId: 'a', role: 'assistant', content: code, done: true },
				c: { id: 'c', parentId: 'a', role: 'assistant', content: code, done: true }
			}
		};
		expect(getConversationArtifacts(history).map((result) => result.id)).toEqual(['b:html']);
		history.messages.b.done = false;
		expect(getConversationArtifacts(history)).toEqual([]);
	});
});
