type Entry = { url: string; references: number };
const entries = new Map<string, Entry>();

function acquire(source: string, entry: Entry) {
	entry.references++;
	let released = false;
	return { url: entry.url, release() {
		if (released) return;
		released = true;
		entry.references--;
		// The composer and user bubble can exchange ownership in the same Svelte update.
		queueMicrotask(() => {
			if (!entry.references && entries.get(source) === entry) {
				entries.delete(source);
				URL.revokeObjectURL(entry.url);
			}
		});
	} };
}

export function registerInlineImageDisplay(source: string, blob: Blob) {
	if (!source.startsWith('data:image/')) return undefined;
	try {
		let entry = entries.get(source);
		if (!entry) {
			entry = { url: URL.createObjectURL(blob), references: 0 };
			entries.set(source, entry);
		}
		return acquire(source, entry);
	} catch { return undefined; }
}

export function inlineImageDisplaySource(source: string): string {
	return entries.get(source)?.url ?? source;
}

export function acquireInlineImageDisplay(source: string) {
	const entry = entries.get(source);
	return entry ? acquire(source, entry) : { url: source, release() {} };
}
