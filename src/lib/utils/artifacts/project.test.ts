import { describe, expect, it } from 'vitest';
import { artifactEntry, artifactFiles, normalizeArtifactPath, isReactFile } from './project';
import { extractArtifactResults, getConversationArtifacts } from '../artifactResults';

describe('artifact projects', () => {
	it('does not interpret HTML text, JSON or CSS as executable React code', () => {
		for (const language of ['html', 'css', 'json'])
			expect(
				isReactFile({ path: 'example', language, content: 'React.useState, React.createElement' })
			).toBe(false);
		expect(
			isReactFile({ path: 'App.js', language: 'js', content: 'export default()=> <h1>JSX</h1>' })
		).toBe(true);
	});
	it('reads complete or explicitly live fenced code without leaking reasoning', () => {
		const source =
			'<details type="reasoning"><summary>Thought</summary>\n```tsx\nsecret\n```\n</details>\n```tsx App.tsx\nexport default()=> <div>Hello</div>';
		expect(artifactFiles(source)).toEqual([]);
		expect(artifactFiles(source, true)).toEqual([
			{ path: 'App.tsx', language: 'tsx', content: 'export default()=> <div>Hello</div>' }
		]);
	});
	it('handles filename metadata, headings, aliases and multiple files', () => {
		const files = artifactFiles(
			'### src/App.tsx\n```tsx\nexport default()=> <main/>\n```\n```typescript src/helpers.ts\nexport const value:number=1;\n```\n```css title="styles.css"\nmain{color:blue}\n```'
		);
		expect(files.map((file) => file.path)).toEqual(['src/App.tsx', 'src/helpers.ts', 'styles.css']);
		expect(artifactEntry(files)?.path).toBe('src/App.tsx');
	});
	it('bounds virtual paths and prevents filesystem traversal', () => {
		expect(normalizeArtifactPath('@/components/../App.tsx')).toBe('src/App.tsx');
		expect(() => normalizeArtifactPath('../../secret')).toThrow();
		expect(artifactFiles('```html ../../secret.html\n<h1>Ignored</h1>\n```')).toEqual([]);
	});
	it('creates completed React and TypeScript artifact cards', () => {
		for (const language of ['jsx', 'tsx', 'react']) {
			const result = extractArtifactResults(
				'```' + language + '\nexport default function App(){return <h1>Hi</h1>}\n```',
				'reply'
			);
			expect(result).toHaveLength(1);
			expect(result[0].id).toBe('reply:html');
			expect(result[0].files?.[0].content).toContain('<h1>');
		}
	});
	it('preserves real HTML accordions but excludes unfinished reasoning', () => {
		const source = '```html\n<details><summary>Open</summary>Real content</details>\n```';
		expect(extractArtifactResults(source, 'accordion')[0].files![0].content).toContain(
			'Real content'
		);
		expect(
			artifactFiles(
				'<details type="reasoning"><summary>Thought</summary>\n\n```html\n<h1>Hidden</h1>',
				true
			)
		).toEqual([]);
	});
	it('updates only an explicitly opened streaming artifact, never another branch', () => {
		const source = '```tsx App.tsx\nexport default()=> <h1>One</h1>';
		const history = {
			currentId: 'a',
			messages: { a: { id: 'a', role: 'assistant', content: source, done: false, parentId: null } }
		};
		expect(getConversationArtifacts(history)).toEqual([]);
		const first = getConversationArtifacts(history, [], 'a:html');
		expect(first[0].live).toBe(true);
		history.messages.a.content = source.replace('One', 'Two');
		expect(getConversationArtifacts(history, first, 'a:html')[0].files![0].content).toContain(
			'Two'
		);
		expect(getConversationArtifacts(history, [], 'another:html')).toEqual([]);
	});
	it('reuses unchanged messages but invalidates same-length edits and completion', () => {
		const history = {
			currentId: 'cache-test',
			messages: {
				'cache-test': {
					id: 'cache-test',
					role: 'assistant',
					content: '```html\n<h1>One</h1>\n```',
					done: true,
					parentId: null
				}
			}
		};
		const first = getConversationArtifacts(history);
		expect(getConversationArtifacts(history)[0]).toBe(first[0]);
		history.messages['cache-test'].content = history.messages['cache-test'].content.replace(
			'One',
			'Two'
		);
		expect(getConversationArtifacts(history)[0]).not.toBe(first[0]);
	});
});
