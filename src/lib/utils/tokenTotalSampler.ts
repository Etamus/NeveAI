// Keep measured totals at a slower UI cadence without throttling generation speed.
export function createTokenTotalSampler(publish: (total: number) => void, interval = 4000) {
	let key: unknown;
	let initialized = false;
	let displayed = 0;
	let pending = 0;
	let nextAt = 0;
	let timer: ReturnType<typeof setTimeout> | undefined;
	const clear = () => { clearTimeout(timer); timer = undefined; };
	const emit = () => {
		clear();
		nextAt = Date.now() + interval;
		if (!initialized || pending !== displayed) publish(pending);
		displayed = pending;
		initialized = true;
	};
	return {
		update(nextKey: unknown, total: number, active: boolean) {
			pending = total;
			if (!initialized || nextKey !== key || !active) {
				key = nextKey;
				emit();
			} else if (pending !== displayed && !timer) {
				const remaining = nextAt - Date.now();
				if (remaining <= 0) emit();
				else timer = setTimeout(emit, remaining);
			}
		},
		destroy: clear,
	};
}
