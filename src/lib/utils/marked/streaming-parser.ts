type SchedulerClock = {
	now: () => number;
	setTimer: (callback: () => void, delay: number) => ReturnType<typeof setTimeout>;
	clearTimer: (timer: ReturnType<typeof setTimeout>) => void;
};

const browserClock: SchedulerClock = {
	now: () => performance.now(),
	setTimer: (callback, delay) => setTimeout(callback, delay),
	clearTimer: (timer) => clearTimeout(timer)
};

// Batch snapshots, not fragments: open blocks and forward references require
// the entire latest document. No guessed boundary is considered stable.
export function createStreamingMarkdownScheduler(
	parse: () => void,
	clock: SchedulerClock = browserClock
) {
	let timer: ReturnType<typeof setTimeout> | undefined;
	let lastEnd = -Infinity;
	let interval = 64;
	let disposed = false;
	let hadContent = false;
	const cancel = () => {
		if (timer !== undefined) clock.clearTimer(timer);
		timer = undefined;
	};
	const flush = () => {
		cancel();
		if (disposed) return;
		const start = clock.now();
		parse();
		lastEnd = clock.now();
		interval = Math.min(200, Math.max(64, (lastEnd - start) * 4));
	};
	return {
		update(immediate = false, hasContent = true) {
			if (disposed) return;
			const firstContent = hasContent && !hadContent;
			hadContent = hasContent;
			if (immediate || firstContent || clock.now() - lastEnd >= interval) flush();
			else if (timer === undefined) {
				timer = clock.setTimer(flush, interval - (clock.now() - lastEnd));
			}
		},
		destroy() {
			cancel();
			disposed = true;
		}
	};
}
