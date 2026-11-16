import RequestWorker from '$lib/workers/chat-request.worker?worker';
import { isLargeInlineImage, packInlineImages } from './inlineImageTransfer';

function ownValue(value: unknown, key: string): any {
	return value !== null && typeof value === 'object' ? Object.getOwnPropertyDescriptor(value, key)?.value : undefined;
}

function hasLargeInlineImage(body: object): boolean {
	const messages = ownValue(body, 'messages');
	if (!Array.isArray(messages)) return false;
	for (let index = 0; index < messages.length; index++) {
		const content = ownValue(ownValue(messages, String(index)), 'content');
		if (!Array.isArray(content)) continue;
		for (let part = 0; part < content.length; part++) {
			const source = ownValue(ownValue(ownValue(content, String(part)), 'image_url'), 'url');
			if (isLargeInlineImage(source)) return true;
		}
	}
	return false;
}

// Custom prototypes/getters/toJSON can change JSON semantics when cloned to a worker.
function isPlainData(value: unknown, seen = new WeakSet<object>()): boolean {
	if (value === null || typeof value !== 'object') return typeof value !== 'function' && typeof value !== 'symbol';
	if (seen.has(value)) return false;
	seen.add(value);
	const prototype = Object.getPrototypeOf(value);
	if (prototype !== Object.prototype && prototype !== Array.prototype && prototype !== null) return false;
	if (Object.getOwnPropertyDescriptor(value, 'toJSON')) return false;
	for (const key of Object.keys(value)) {
		const descriptor = Object.getOwnPropertyDescriptor(value, key)!;
		if (descriptor.get || descriptor.set || !isPlainData(descriptor.value, seen)) return false;
	}
	seen.delete(value);
	return true;
}

export async function prepareChatRequestBody(body: object): Promise<string | Blob | undefined> {
	if (typeof Worker === 'undefined' || !hasLargeInlineImage(body) || !isPlainData(body)) return JSON.stringify(body);
	const encoded = await new Promise<Blob | undefined>(resolve => {
		let worker: Worker | undefined;
		let timer: ReturnType<typeof setTimeout> | undefined;
		const finish = (result?: Blob) => {
			clearTimeout(timer);
			worker?.terminate();
			resolve(result);
		};
		try {
			worker = new RequestWorker();
			worker.onmessage = ({ data }) => finish(data?.body instanceof Blob ? data.body : undefined);
			worker.onerror = event => { event.preventDefault(); finish(); };
			worker.onmessageerror = () => finish();
			timer = setTimeout(() => finish(), 2000);
			worker.postMessage(packInlineImages(body));
		} catch { finish(); }
	});
	// No HTTP request is made by the worker, so fallback cannot duplicate a generation.
	return encoded ?? JSON.stringify(body);
}
