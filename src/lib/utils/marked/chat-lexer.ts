import { Marked, marked, type MarkedExtension, type TokensList } from 'marked';
import detailsExtension from './extension';
import katexExtension from './katex-extension';
import citationExtension from './citation-extension';
import footnoteExtension from './footnote-extension';
import { disableSingleTilde } from './strikethrough-extension';
import { isWithinCodeBlock } from 'remend';
import { mentionExtension } from './mention-extension';

function extensions(): MarkedExtension[] {
	const options = { throwOnError: false, breaks: true };
	return [
		katexExtension(options),
		detailsExtension(options),
		citationExtension(),
		footnoteExtension(),
		disableSingleTilde,
		{ extensions: ['@', '#', '$'].map((triggerChar) => mentionExtension({ triggerChar })) }
	] as MarkedExtension[];
}

// Nested details/alert renderers still use global marked. Configure compatibility
// once per module, never once per mounted message.
marked.use(...extensions());

// Other consumers can mutate global marked without affecting the main lexer.
const chatMarked = new Marked(...extensions());
export const lexChatMarkdown = (source: string): TokensList => {
	// Structured output is a separate block, not a lazy continuation of a list.
	// Keep literal examples inside code untouched, including unfinished fences.
	const separated = source.replace(/^<details\s+type="(?:reasoning|tool_calls|code_interpreter)"[^>]*>\r?\n/gm,
		(tag, offset) => offset > 0 && !source.slice(0, offset).endsWith('\n\n') &&
			!isWithinCodeBlock(source, offset) ? '\n' + tag : tag);
	return chatMarked.lexer(separated);
};

function equalToken(a: unknown, b: unknown): boolean {
	if (a === b) return true;
	if (!a || !b || typeof a !== 'object' || typeof b !== 'object') return false;
	if (Array.isArray(a) !== Array.isArray(b)) return false;
	const keys = Object.keys(a);
	const left = a as Record<string, unknown>;
	const right = b as Record<string, unknown>;
	return (
		keys.length === Object.keys(b).length &&
		keys.every(
			(key) => Object.prototype.hasOwnProperty.call(b, key) && equalToken(left[key], right[key])
		)
	);
}

export function createChatMarkdownParser(lexer = lexChatMarkdown) {
	let previousSource: string | undefined;
	let previous: TokensList | undefined;
	return (source: string): TokensList => {
		if (source === previousSource && previous) return previous;
		const next = lexer(source);
		// Raw equality misses forward link definitions changing nested inline tokens.
		if (previous) {
			for (let i = 0; i < next.length; i++) {
				if (equalToken(previous[i], next[i])) next[i] = previous[i];
			}
		}
		previousSource = source;
		previous = next;
		return next;
	};
}
