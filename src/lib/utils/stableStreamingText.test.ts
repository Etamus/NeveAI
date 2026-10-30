import { describe, expect, it, vi } from 'vitest';
import { stableStreamingText } from './stableStreamingText';

function fixture(data: string) {
	const text = {
		nodeType: 3, data,
		appendData: vi.fn((suffix: string) => { text.data += suffix; }),
		replaceData: vi.fn((offset: number, count: number, replacement: string) => {
			text.data = text.data.slice(0, offset) + replacement + text.data.slice(offset + count);
		})
	};
	const node = { firstChild: text } as unknown as HTMLElement;
	return { text, action: stableStreamingText(node, data) };
}

describe('Stable streaming text node', () => {
	it('appends only new characters without replacing existing text', () => {
		const { text, action } = fixture('First');
		action.update!('First second');
		expect(text.data).toBe('First second');
		expect(text.appendData).toHaveBeenCalledWith(' second');
		expect(text.replaceData).not.toHaveBeenCalled();
	});
	it.each([
		['One old suffix', 'One new suffix', 4, 3, 'new'],
		['Long text', 'Long', 4, 5, ''],
		['First', '', 0, 5, ''],
		['Old', 'New', 0, 3, 'New']
	])('replaces only changed characters in %s -> %s', (before, after, start, count, replacement) => {
		const { text, action } = fixture(before);
		action.update!(after);
		expect(text.data).toBe(after);
		expect(text.replaceData).toHaveBeenCalledWith(start, count, replacement);
	});
	it('does not write for scroll-only rerenders or completion', () => {
		const { text, action } = fixture('Unchanged');
		action.update!('Unchanged');
		expect(text.appendData).not.toHaveBeenCalled();
		expect(text.replaceData).not.toHaveBeenCalled();
	});
	it('supports an empty initial SSR text node and Unicode appends', () => {
		const { text, action } = fixture('');
		action.update!('Ol\u00e1');
		expect(text.data).toBe('Ol\u00e1');
		expect(text.appendData).toHaveBeenCalledWith('Ol\u00e1');
	});
});
