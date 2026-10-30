import { EventSourceParserStream } from 'eventsource-parser/stream';
import { Marked } from 'marked';

const lexer = new Marked();
const opening = /<(think|thinking|thought|reason|reasoning|analysis)\b[^>]*>|(?:<\|start\|>\s*(?:assistant|model)\s*)?<\|channel\|>\s*(analysis|thought|thinking|reasoning|reason)\b\s*(?:<\|(?:message|content)\|>)?/i;
const finalChannel = /(?:<\|end\|>\s*)?(?:<\|start\|>\s*(?:assistant|model)\s*)?<\|channel\|>\s*(?:final|answer|response)\b\s*(?:<\|(?:message|content)\|>)?/i;
const controlPrefixes = ['<think>', '<thinking>', '<thought>', '<reason>', '<reasoning>', '<analysis>', '<|channel|>analysis<|message|>', '<|start|>assistant<|channel|>analysis<|message|>'];

// Use the Markdown lexer to leave literal reasoning markers in code untouched.
function maskCode(source: string) {
	let masked = source;
	lexer.walkTokens(lexer.lexer(source), (token) => {
		if ((token.type === 'code' || token.type === 'codespan') && token.raw) {
			masked = masked.replaceAll(token.raw, token.raw.replace(/[^\r\n]/g, ' '));
		}
	});
	return masked;
}

function reasoningBlock(text: string, done: boolean) {
	if (!text.trim()) return '';
	const escaped = text.replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;');
	return `<details type="reasoning" done="${done}">\n<summary></summary>\n\n${escaped.split('\n').map(line => `> ${line}`).join('\n')}\n</details>\n\n`;
}

export function formatSelectionActionResponse(content: string, reasoning = '', done = false) {
	let remaining = content;
	let result = reasoningBlock(reasoning, done || Boolean(content.trim()));
	while (remaining) {
		const masked = maskCode(remaining);
		const start = opening.exec(masked);
		if (!start) {
			if (!done) {
				const index = masked.lastIndexOf('<');
				const tail = index >= 0 ? masked.slice(index).toLowerCase() : '';
				if (tail && controlPrefixes.some(prefix => prefix.startsWith(tail))) remaining = remaining.slice(0, index);
			}
			return result + remaining;
		}
		result += remaining.slice(0, start.index);
		const offset = start.index + start[0].length;
		const body = remaining.slice(offset);
		const bodyMask = maskCode(body);
		const end = (start[1] ? new RegExp(`</${start[1]}\\s*>`, 'i') : finalChannel).exec(bodyMask);
		result += (result ? '\n\n' : '') + reasoningBlock(end ? body.slice(0, end.index) : body, done || Boolean(end));
		if (!end) return result;
		remaining = body.slice(end.index + end[0].length);
	}
	return result;
}

// This endpoint has no message ID and returns raw provider SSE, unlike the main chat.
export async function* createSelectionActionStream(body: ReadableStream<Uint8Array>) {
	const reader = body.pipeThrough(new TextDecoderStream() as unknown as ReadableWritablePair<string, Uint8Array>)
		.pipeThrough(new EventSourceParserStream()).getReader();
	try {
		while (true) {
			const event = await reader.read();
			if (event.done || event.value?.data?.startsWith('[DONE]')) {
				yield { done: true, value: '', reasoning: '' };
				return;
			}
			if (!event.value?.data) continue;
			let data;
			try { data = JSON.parse(event.value.data); }
			catch { continue; }
			if (data.error) throw new Error(data.error.message ?? String(data.error));
			const delta = data.choices?.[0]?.delta ?? {};
			const reasoning = delta.reasoning_content || delta.reasoning || delta.thinking || '';
			yield { done: false, value: typeof delta.content === 'string' ? delta.content : '', reasoning: typeof reasoning === 'string' ? reasoning : '' };
		}
	} finally {
		await reader.cancel().catch(() => {});
		reader.releaseLock();
	}
}
