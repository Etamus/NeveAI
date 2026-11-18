import { afterEach, describe, expect, it, vi } from 'vitest';
import hljs from 'highlight.js';
import { createCodeBlockHighlighter, detectCodeLanguage } from './codeBlockHighlight';

afterEach(() => { vi.restoreAllMocks(); });
describe('code block highlighting', () => {
	it.each(['css', 'python', 'js', 'html', 'sql', 'json'])('uses the declared language %s', language => {
		const auto = vi.spyOn(hljs, 'highlightAuto');
		const code = '/* example */ <tag> const value = 42;';
		expect(createCodeBlockHighlighter()(code, language)).toBe(hljs.highlight(code, {language, ignoreIllegals: true}).value);
		expect(auto).not.toHaveBeenCalled();
	});
	it('leaves unknown text to the escaped text node without running detection on the UI thread', () => {
		const auto = vi.spyOn(hljs, 'highlightAuto');
		const highlight = createCodeBlockHighlighter();
		const code = '<script>alert(1)</script>';
		const html = highlight(code, 'unknown-language');
		expect(html).toBeNull();
		expect(highlight(code, 'unknown-language')).toBe(html);
		expect(auto).not.toHaveBeenCalled();
		highlight(code + 'more', 'unknown-language');
		expect(auto).not.toHaveBeenCalled();
		expect(highlight('', 'css')).toBe('');
	});
});

it('coalesces streamed revisions, ignores stale replies, and releases its idle worker', () => {
	vi.useFakeTimers();
	const post = vi.fn(), terminate = vi.fn();
	let worker: { onmessage: (event: { data: string }) => void };
	vi.stubGlobal('Worker', class {
		postMessage = post;
		terminate = terminate;
		onmessage = (_event: { data: string }) => {};
		constructor() { worker = this; }
	});
	try {
		const receive = vi.fn();
		const first = detectCodeLanguage('old', receive);
		first();
		const second = detectCodeLanguage('older', receive);
		vi.advanceTimersByTime(160);
		expect(post.mock.calls).toEqual([['older']]);
		second();
		detectCodeLanguage('current', receive);
		vi.advanceTimersByTime(160);
		worker!.onmessage({ data: 'discard' });
		expect(receive).not.toHaveBeenCalled();
		expect(post.mock.calls.at(-1)).toEqual(['current']);
		worker!.onmessage({ data: 'highlighted' });
		expect(receive.mock.calls).toEqual([['highlighted']]);
		vi.advanceTimersByTime(30000);
		expect(terminate).toHaveBeenCalledTimes(1);
	} finally { vi.useRealTimers(); vi.unstubAllGlobals(); }
});
