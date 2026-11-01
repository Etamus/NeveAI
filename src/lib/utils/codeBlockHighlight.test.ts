import { afterEach, describe, expect, it, vi } from 'vitest';
import hljs from 'highlight.js';
import { createCodeBlockHighlighter } from './codeBlockHighlight';

afterEach(() => { vi.restoreAllMocks(); });
describe('code block highlighting', () => {
	it.each(['css', 'python', 'js', 'html', 'sql', 'json'])('uses the declared language %s', language => {
		const auto = vi.spyOn(hljs, 'highlightAuto');
		const code = '/* example */ <tag> const value = 42;';
		expect(createCodeBlockHighlighter()(code, language)).toBe(hljs.highlight(code, {language, ignoreIllegals: true}).value);
		expect(auto).not.toHaveBeenCalled();
	});
	it('keeps unknown language detection, escapes HTML, and caches only unchanged input', () => {
		const auto = vi.spyOn(hljs, 'highlightAuto');
		const highlight = createCodeBlockHighlighter();
		const code = '<script>alert(1)</script>';
		const html = highlight(code, 'unknown-language');
		expect(html).not.toContain('<script>');
		expect(highlight(code, 'unknown-language')).toBe(html);
		expect(auto).toHaveBeenCalledTimes(1);
		highlight(code + 'more', 'unknown-language');
		expect(auto).toHaveBeenCalledTimes(2);
		expect(highlight('', 'css')).toBe('');
	});
});
