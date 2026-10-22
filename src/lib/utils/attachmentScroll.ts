export function attachmentScroller(container: HTMLElement) {
	let frame = 0, target = 0, last = 0, previousTime = 0, direction = 0;
	const stop = () => { cancelAnimationFrame(frame); frame = 0; direction = 0; };
	const animate = (time: number) => {
		if (!container.isConnected || Math.abs(container.scrollLeft - last) > 1) { stop(); return; }
		const delta = Math.max(0, time - previousTime);
		previousTime = time;
		if (!delta) { frame = requestAnimationFrame(animate);return; }
		const remaining = target - container.scrollLeft;
		const before = container.scrollLeft;
		const next = Math.abs(remaining) < .5 ? target : container.scrollLeft + remaining * (1 - Math.exp(-delta / 35));
		container.scrollLeft = next;
		// Some browsers round scroll offsets to whole pixels.
		if (container.scrollLeft === before) container.scrollLeft = before + Math.sign(remaining) * Math.min(1, Math.abs(remaining));
		last = container.scrollLeft;
		if (Math.abs(target - last) <= .5) { container.scrollLeft = target; stop(); }
		else frame = requestAnimationFrame(animate);
	};
	const wheel = (event: WheelEvent) => {
		const max = container.scrollWidth - container.clientWidth;
		if (max <= 0 || event.ctrlKey) return;
		// Leave horizontal trackpad inertia with the browser.
		if (Math.abs(event.deltaX) > Math.abs(event.deltaY)) { stop(); event.stopPropagation(); return; }
		if (!event.deltaY) return;
		const pixels = event.deltaY * (event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? container.clientWidth : 1);
		const rtl = getComputedStyle(container).direction === 'rtl';
		if (!frame || Math.sign(pixels) !== direction || Math.abs(container.scrollLeft - last) > 1) target = container.scrollLeft;
		target = Math.max(rtl ? -max : 0, Math.min(rtl ? 0 : max, target + pixels));
		event.preventDefault();event.stopPropagation();
		if (matchMedia('(prefers-reduced-motion: reduce)').matches) { stop();container.scrollLeft = target;return; }
		direction = Math.sign(pixels);
		if (!frame) { last = container.scrollLeft;previousTime = performance.now();frame = requestAnimationFrame(animate); }
	};
	container.addEventListener('wheel', wheel, { passive: false });
	container.addEventListener('pointerdown', stop, { passive: true });
	container.addEventListener('keydown', stop);
	return { destroy() {
		stop();container.removeEventListener('wheel', wheel);
		container.removeEventListener('pointerdown', stop);container.removeEventListener('keydown', stop);
	} };
}
