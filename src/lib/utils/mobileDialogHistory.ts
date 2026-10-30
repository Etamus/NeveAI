type Entry = { id: string; close: () => void; closed: boolean };
type HistoryAdapter = { push: (id: string) => void; back: () => void; current: () => string | undefined };

// Dialogs use shallow history entries, never a chat navigation or a URL change.
export function createMobileDialogHistory(adapter: HistoryAdapter) {
	const entries: Entry[] = [];
	const queued: Entry[] = [];
	const session = Math.random().toString(36).slice(2);
	let serial = 0;
	let leaving: string | null = null;
	const back = (entry: Entry) => { leaving = entry.id; adapter.back(); };
	const flush = () => {
		if (leaving) return;
		const top = entries.at(-1);
		if (top?.closed) {
			if (adapter.current() === top.id) back(top);
			else { entries.pop(); flush(); }
			return;
		}
		for (const entry of queued.splice(0)) {
			if (entry.closed) continue;
			entries.push(entry);
			adapter.push(entry.id);
		}
	};
	return {
		open(close: () => void) {
			const entry = { id: `${session}-${++serial}`, close, closed: false };
			queued.push(entry); flush();
			return () => { entry.closed = true; flush(); };
		},
		synchronize(destination: string | undefined) {
			if (destination === leaving) return;
			leaving = null;
			const index = entries.findIndex(entry => entry.id === destination);
			for (const entry of entries.splice(index + 1).reverse()) {
				const notify = !entry.closed;
				entry.closed = true;
				if (notify) entry.close();
			}
			flush();
		}
	};
}
