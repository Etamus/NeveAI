import remend, { isWithinCodeBlock } from 'remend';
import type { TokensList } from 'marked';
import { findMatchingClosingTag } from './extension';

function repairMarkdown(source: string): string {
	// Leave code and the project's custom HTML/details syntax entirely to the existing lexer.
	if (isWithinCodeBlock(source, source.length - 1)) return source;
	const repaired = remend(source, {
		htmlTags: false, comparisonOperators: false, singleTilde: false,
		// Remend 1.4 shares its link/image handler; don't create image placeholder URLs.
		links: !source.includes('!['), images: false, linkMode: 'text-only', inlineKatex: false, katex: false
	});
	return source.endsWith(' ') && !source.endsWith('  ') ? repaired + ' ' : repaired;
}

export function prepareStreamingMarkdown(source: string): string {
	// A details body has its own Markdown renderer. Completing its delimiters at
	// the end of the outer document would leak literal markers below the tool.
	const details = /^<details(?:\s[^>]*)?>\r?\n/gm;
	let cursor = 0;
	let result = '';
	let match: RegExpExecArray | null;
	while ((match = details.exec(source))) {
		if (isWithinCodeBlock(source, match.index)) continue;
		// A structured block ends the preceding segment. Repair only the live tail:
		// balancing completed text can insert a delimiter immediately before <details>.
		result += source.slice(cursor, match.index);
		const length = findMatchingClosingTag(source.slice(match.index), '<details', '</details>');
		if (length < 0) return result + source.slice(match.index);
		cursor = match.index + length;
		result += source.slice(match.index, cursor);
		details.lastIndex = cursor;
	}
	return result + repairMarkdown(source.slice(cursor));
}

export function stabilizeStreamingBlocks(tokens: TokensList, originalSource?: string): TokensList {
	const last = tokens.at(-1);
	if (!last) return tokens;
	const raw = last.raw ?? '';
	const pendingTable = (last.type === 'paragraph' || last.type === 'text') && /^ {0,3}\|/.test(raw);
	const pendingFence = last.type === 'code' && /^ {0,3}(`{3,}|~{3,})/.test(raw) && !raw.includes('\n');
	const pendingMath = (last.type === 'paragraph' || last.type === 'text') && /^ {0,3}(\$\$|\\\[|\\begin\{equation\})/.test(raw);
	// A live `*   **` can still become a bold list item, not a thematic break.
	const pendingRule = last.type === 'hr' && !/\n[\t \r]*$/.test(originalSource ?? raw);
	if (!pendingTable && !pendingFence && !pendingMath && !pendingRule) return tokens;
	// An unfinished table header/fence must not first appear as a normal paragraph.
	const visible = tokens.slice(0, -1) as TokensList;
	visible.links = tokens.links;
	return visible;
}
