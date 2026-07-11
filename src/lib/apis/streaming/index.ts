import { EventSourceParserStream } from 'eventsource-parser/stream';
import type { ParsedEvent } from 'eventsource-parser';

type TextStreamUpdate = {
	done: boolean;
	value: string;
	// eslint-disable-next-line @typescript-eslint/no-explicit-any
	sources?: any;
	// eslint-disable-next-line @typescript-eslint/no-explicit-any
	selectedModelId?: any;
	error?: any;
	usage?: ResponseUsage;
};

type ResponseUsage = {
	/** Including images and tools if any */
	prompt_tokens: number;
	/** The tokens generated */
	completion_tokens: number;
	/** Sum of the above two fields */
	total_tokens: number;
	/** Any other fields that aren't part of the base OpenAI spec */
	[other: string]: unknown;
};

// createOpenAITextStream takes a responseBody with a SSE response,
// and returns an async generator that emits delta updates. Optional smoothing keeps
// large provider chunks feeling live without flooding the UI with tiny updates.
export async function createOpenAITextStream(
	responseBody: ReadableStream<Uint8Array>,
	splitLargeDeltas: boolean
): Promise<AsyncGenerator<TextStreamUpdate>> {
	const eventStream = responseBody
		.pipeThrough(new TextDecoderStream())
		.pipeThrough(new EventSourceParserStream())
		.getReader();
	let iterator = openAIStreamToIterator(eventStream);
	if (splitLargeDeltas) {
		iterator = streamLargeDeltasAsSmoothChunks(iterator);
	}
	return iterator;
}

async function* openAIStreamToIterator(
	reader: ReadableStreamDefaultReader<ParsedEvent>
): AsyncGenerator<TextStreamUpdate> {
	while (true) {
		const { value, done } = await reader.read();
		if (done) {
			yield { done: true, value: '' };
			break;
		}
		if (!value) {
			continue;
		}
		const data = value.data;
		if (data.startsWith('[DONE]')) {
			yield { done: true, value: '' };
			break;
		}

		try {
			const parsedData = JSON.parse(data);

			if (parsedData.error) {
				yield { done: true, value: '', error: parsedData.error };
				break;
			}

			if (parsedData.sources) {
				yield { done: false, value: '', sources: parsedData.sources };
				continue;
			}

			if (parsedData.selected_model_id) {
				yield { done: false, value: '', selectedModelId: parsedData.selected_model_id };
				continue;
			}

			if (parsedData.usage) {
				yield { done: false, value: '', usage: parsedData.usage };
				continue;
			}

			yield {
				done: false,
				value: parsedData.choices?.[0]?.delta?.content ?? ''
			};
		} catch (e) {
			console.error('Error extracting delta from SSE event:', e);
		}
	}
}

const MIN_SMOOTH_CHUNK_SIZE = 5;
const MAX_SMOOTH_CHUNK_SIZE = 12;
const SMOOTH_CHUNK_LOOKAHEAD = 10;
const SMOOTH_CHUNK_DELAY_MS = 6;
const MARKDOWN_MARKER_CHARS = new Set(['*', '_', '`', '~']);

const pickSmoothChunkSize = (content: string) => {
	if (content.length <= MAX_SMOOTH_CHUNK_SIZE) {
		return content.length;
	}

	const target =
		Math.floor(Math.random() * (MAX_SMOOTH_CHUNK_SIZE - MIN_SMOOTH_CHUNK_SIZE + 1)) +
		MIN_SMOOTH_CHUNK_SIZE;
	const maxLookahead = Math.min(content.length, target + SMOOTH_CHUNK_LOOKAHEAD);

	for (let i = target; i < maxLookahead; i++) {
		if (/[\s,.;:!?)}\]]/.test(content[i] ?? '')) {
			return i + 1;
		}
	}

	let chunkSize = Math.min(target, content.length);
	while (
		chunkSize < content.length &&
		MARKDOWN_MARKER_CHARS.has(content[chunkSize]) &&
		content[chunkSize] === content[chunkSize - 1]
	) {
		chunkSize += 1;
	}

	return chunkSize;
};

// Smooth large deltas without splitting the UI into single-character bursts.
// This preserves the live typing feel while reducing Markdown/codeblock reflows.
async function* streamLargeDeltasAsSmoothChunks(
	iterator: AsyncGenerator<TextStreamUpdate>
): AsyncGenerator<TextStreamUpdate> {
	for await (const textStreamUpdate of iterator) {
		if (textStreamUpdate.done) {
			yield textStreamUpdate;
			return;
		}

		if (textStreamUpdate.error) {
			yield textStreamUpdate;
			continue;
		}
		if (textStreamUpdate.sources) {
			yield textStreamUpdate;
			continue;
		}
		if (textStreamUpdate.selectedModelId) {
			yield textStreamUpdate;
			continue;
		}
		if (textStreamUpdate.usage) {
			yield textStreamUpdate;
			continue;
		}

		let content = textStreamUpdate.value;
		if (content.length <= MAX_SMOOTH_CHUNK_SIZE) {
			yield { done: false, value: content };
			continue;
		}
		while (content != '') {
			const chunkSize = pickSmoothChunkSize(content);
			const chunk = content.slice(0, chunkSize);
			yield { done: false, value: chunk };
			// Do not sleep if the tab is hidden
			// Timers are throttled to 1s in hidden tabs
			if (typeof document !== 'undefined' && document.visibilityState !== 'hidden') {
				await sleep(SMOOTH_CHUNK_DELAY_MS);
			}
			content = content.slice(chunkSize);
		}
	}
}

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));
