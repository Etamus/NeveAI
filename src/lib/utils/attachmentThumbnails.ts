import ThumbnailWorker from '$lib/workers/attachment-thumbnail.worker?worker';

type Entry = { references: number; ready: Promise<string>; url?: string; cancel?: () => void };
const cache = new Map<string, Entry>();
const pending = new Map<number, (blob?: Blob) => void>();
let worker: Worker | undefined;
let sequence = 0;

function trim() {
	for (const [source, entry] of cache) {
		if (cache.size <= 24) break;
		if (entry.references || !entry.url) continue;
		if (entry.url !== source) URL.revokeObjectURL(entry.url);
		cache.delete(source);
	}
}

function createPreview(source: string): { ready: Promise<string>; cancel?: () => void } {
	if (typeof Worker === 'undefined' || typeof OffscreenCanvas === 'undefined') return { ready: Promise.resolve(source) };
	if (/^https?:/i.test(source) && new URL(source).origin !== location.origin) return { ready: Promise.resolve(source) };
	const id = ++sequence;
	const ready = new Promise<string>(resolve => {
		try {
			if (!worker) {
				worker = new ThumbnailWorker();
				worker.onmessage = ({ data }) => {
					pending.get(data.id)?.(data.blob);
					pending.delete(data.id);
				};
				worker.onerror = () => {
					for (const finish of pending.values()) finish();
					pending.clear();worker?.terminate();worker = undefined;
				};
			}
			pending.set(id, blob => resolve(blob ? URL.createObjectURL(blob) : source));
			worker.postMessage({ id, source });
		} catch { pending.delete(id);resolve(source); }
	});
	return { ready, cancel() {
		const finish = pending.get(id);
		if (!finish) return;
		pending.delete(id);
		worker?.postMessage({ cancel: id });
		finish();
	} };
}

export function acquireAttachmentThumbnail(source: string) {
	let entry = cache.get(source);
	if (!entry) {
		entry = { references: 0, ready: Promise.resolve(source) };
		const created = entry;
		const preview = createPreview(source);
		entry.cancel = preview.cancel;
		entry.ready = preview.ready.then(url => { created.url = url; trim(); return url; });
		cache.set(source, entry);
	} else { cache.delete(source); cache.set(source, entry); }
	entry.references++;
	let released = false;
	return {
		ready: entry.ready,
		release() {
			if (released) return;
			released = true;
			entry!.references--;
			trim();
			// A keyed remount in the same update may immediately acquire this source again.
			queueMicrotask(() => {
				if (!entry!.references && !entry!.url && cache.get(source) === entry) {
					cache.delete(source);
					entry!.cancel?.();
				}
			});
		}
	};
}
