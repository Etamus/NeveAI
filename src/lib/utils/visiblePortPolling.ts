type Target = { url: string; key: string };

export function createPortPolling<T>(
	read: (url: string, key: string, signal: AbortSignal) => Promise<T[]>,
	show: (ports: T[]) => void,
	loading: (active: boolean) => void
) {
	let snapshot: Target | undefined;
	let controller: AbortController | undefined;
	let timer: ReturnType<typeof setTimeout> | undefined;

	function stop() {
		clearTimeout(timer);
		controller?.abort();
		controller = undefined;
		loading(false);
	}

	function update(url: string, key: string, expanded: boolean, visible: boolean, force = false) {
		stop();
		if (snapshot && (snapshot.url !== url || snapshot.key !== key)) {
			snapshot = undefined;
			show([]);
		}
		if (!visible || !url || (!force && !expanded && snapshot)) return;
		const task = new AbortController();
		controller = task;
		const refresh = async () => {
			loading(true);
			try {
				const result = await read(url, key, task.signal);
				if (!task.signal.aborted) {
					snapshot = { url, key };
					show(result);
				}
			} catch {
				// A transient failure leaves the last successful reading intact.
			} finally {
				if (!task.signal.aborted) {
					loading(false);
					if (expanded) timer = setTimeout(refresh, 5000);
				}
			}
		};
		void refresh();
	}

	return { update, stop };
}
