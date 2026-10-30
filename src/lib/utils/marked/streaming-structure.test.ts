import { describe, expect, it } from 'vitest';
import { lexChatMarkdown } from './chat-lexer';
import { prepareStreamingMarkdown } from './streaming-display';
import { changesVisibleStructure } from './streaming-structure';

const parse = (text: string) => lexChatMarkdown(prepareStreamingMarkdown(text));
describe('Reformatting does not replay text fades', () => {
	it.each([
		['Words **', 'Words **bold'],
		['Words *', 'Words *italic'],
		['Words `', 'Words `code'],
		['Words ~~', 'Words ~~deleted'],
		['Words [a label](https://example.com', 'Words [a label](https://example.com)'],
		['1. First item\n2', '1. First item\n2.'],
	])('recognizes structural change from %s to %s', (before, after) => {
		expect(changesVisibleStructure(parse(before), parse(after))).toBe(true);
	});
	it.each([['Words', 'Words more'], ['Words.', 'Words.\n\nNew paragraph.'], ['1. Item', '1. Item extended']])(
		'preserves normal append animations from %s to %s', (before, after) => {
			expect(changesVisibleStructure(parse(before), parse(after))).toBe(false);
		});
});
