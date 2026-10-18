<script lang="ts">
	import { onMount, setContext } from 'svelte';

	export let messageId: string;
	export let enabled = false;
	export let keepMounted = false;

	let row: HTMLDivElement;
	let nearViewport = true;
	let interacted = false;
	let measuredHeight = 0;
	let measurementPending = false;
	let mediaPending = false;
	$: mounted = !enabled || keepMounted || interacted || nearViewport || measuredHeight === 0 || measurementPending || mediaPending;
	$: if (!enabled) nearViewport = true;
	setContext('message-window-restoring', () => enabled && measuredHeight > 0);

	const retainInteraction = () => { interacted = true; };
	const hasRetainedState = () => {
		const selection = window.getSelection();
		const hasSelection = selection && !selection.isCollapsed && (
			row.contains(selection.anchorNode) || row.contains(selection.focusNode)
		);
		const playing = Array.from(row.querySelectorAll('audio, video')).some(
			(media) => !(media as HTMLMediaElement).paused && !(media as HTMLMediaElement).ended
		);
		const editingOrExpanded = row.querySelector(
			'textarea, [contenteditable="true"], [aria-expanded="true"], [data-state="open"], details[open], [id^="reasoning-content-"]'
		);
		const scrolled = Array.from(row.querySelectorAll<HTMLElement>('pre, [class*="overflow-"]')).some(
			(element) => element.scrollTop > 0 || element.scrollLeft > 0
		);
		return Boolean(row.contains(document.activeElement) || hasSelection || playing || editingOrExpanded || scrolled);
	};
	const releaseInteraction = () => queueMicrotask(() => {
		if (row?.isConnected && !nearViewport) interacted = hasRetainedState();
	});
	const measure = (node: HTMLElement) => {
		if (typeof ResizeObserver === 'undefined') return {};
		const update = () => {
			mediaPending = Array.from(node.querySelectorAll('img')).some((image) => !image.complete);
			const height = node.getBoundingClientRect().height;
			if (height > 0 && !mediaPending) measuredHeight = height;
			measurementPending = false;
		};
		const observer = new ResizeObserver(() => {
			update();
		});
		node.addEventListener('load', update, true);
		node.addEventListener('error', update, true);
		observer.observe(node);
		return { destroy() {
			observer.disconnect();
			node.removeEventListener('load', update, true);
			node.removeEventListener('error', update, true);
		} };
	};

	onMount(() => {
		const viewport = row.closest<HTMLElement>('#messages-container');
		if (!viewport || typeof IntersectionObserver === 'undefined' || typeof ResizeObserver === 'undefined') {
			interacted = true;
			return;
		}
		const observer = new IntersectionObserver(([entry]) => {
			if (entry.boundingClientRect.width <= 0) return;
			if (!entry.isIntersecting) interacted = hasRetainedState();
			nearViewport = entry.isIntersecting;
		}, { root: viewport, rootMargin: '1200px 0px' });
		observer.observe(row);
		let width = row.getBoundingClientRect().width;
		const resize = new ResizeObserver(([entry]) => {
			if (Math.abs(entry.contentRect.width - width) <= 1) return;
			width = entry.contentRect.width;
			if (!mounted) {
				measurementPending = true;
			}
		});
		resize.observe(row);
		return () => { observer.disconnect(); resize.disconnect(); };
	});
</script>

<!-- svelte-ignore a11y_no_static_element_interactions -->
<div
	bind:this={row}
	class:contents={!enabled}
	data-message-window={messageId}
	data-message-mounted={mounted}
	data-message-measured={!enabled || (measuredHeight > 0 && !mediaPending && !measurementPending)}
	style:height={!mounted ? `${measuredHeight}px` : undefined}
	style:min-height={enabled && mounted && measuredHeight > 0 ? `${measuredHeight}px` : undefined}
	on:pointerdown|capture={retainInteraction}
	on:focusin={retainInteraction}
	on:focusout={releaseInteraction}
	on:pause|capture={releaseInteraction}
>
	{#if mounted}
		<div class={enabled ? 'flow-root' : 'contents'} use:measure><slot /></div>
	{/if}
</div>
