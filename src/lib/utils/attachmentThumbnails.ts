import ThumbnailWorker from '$lib/workers/attachment-thumbnail.worker?worker';

type Entry = { references: number; ready: Promise<string>; url?: string };
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

function createPreview(source: string): Promise<string> {
	if (typeof Worker === 'undefined' || typeof OffscreenCanvas === 'undefined') return Promise.resolve(source);
	if (/^https?:/i.test(source) && new URL(source).origin !== location.origin) return Promise.resolve(source);
	return new Promise(resolve => {
		const id = ++sequence;
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
}

export function acquireAttachmentThumbnail(source: string) {
	let entry = cache.get(source);
	if (!entry) {
		entry = { references: 0, ready: Promise.resolve(source) };
		const created = entry;
		entry.ready = createPreview(source).then(url => { created.url = url; trim(); return url; });
		cache.set(source, entry);
	} else { cache.delete(source); cache.set(source, entry); }
	entry.references++;
	let released = false;
	return {
		ready: entry.ready,
		release() { if (!released) { released = true; entry!.references--; trim(); } }
	};
}
