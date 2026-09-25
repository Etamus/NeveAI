<script lang="ts">
	import { NEVEAI_BASE_URL } from '$lib/constants';
	import { settings, playingNotificationSound, isLastActiveTab } from '$lib/stores';
	import DOMPurify from 'dompurify';
	import { marked } from 'marked';

	import { createEventDispatcher, onMount } from 'svelte';
	import XMark from '$lib/components/icons/XMark.svelte';

	const dispatch = createEventDispatcher();

	export let onClick: Function = () => {};
	export let title: string = 'HI';
	export let content: string;

	let startX = 0,
		startY = 0;
	let moved = false;
	let closeButtonElement: HTMLButtonElement;
	const DRAG_THRESHOLD_PX = 6;

	const clickHandler = () => {
		onClick();
		dispatch('closeToast');
	};

	const closeHandler = () => {
		dispatch('closeToast');
	};

	function onPointerDown(e: PointerEvent) {
		startX = e.clientX;
		startY = e.clientY;
		moved = false;
		// Ensure we continue to get events even if the toast moves under the pointer.
		(e.currentTarget as HTMLElement).setPointerCapture?.(e.pointerId);
	}

	function onPointerMove(e: PointerEvent) {
		if (moved) return;
		const dx = e.clientX - startX;
		const dy = e.clientY - startY;
		if (dx * dx + dy * dy > DRAG_THRESHOLD_PX * DRAG_THRESHOLD_PX) {
			moved = true;
		}
	}

	function onPointerUp(e: PointerEvent) {
		// Release capture if taken
		(e.currentTarget as HTMLElement).releasePointerCapture?.(e.pointerId);

		// Skip if clicking the close button
		if (
			closeButtonElement &&
			(e.target === closeButtonElement || closeButtonElement.contains(e.target as Node))
		) {
			return;
		}

		// Only treat as a click if there wasn't a drag
		if (!moved) {
			clickHandler();
		}
	}

	onMount(() => {
		if (!navigator.userActivation.hasBeenActive) {
			return;
		}

		if ($settings?.notificationSound ?? true) {
			if (!$playingNotificationSound && $isLastActiveTab) {
				playingNotificationSound.set(true);

				const audio = new Audio(`/audio/notification.mp3`);
				audio.play().finally(() => {
					// Ensure the global state is reset after the sound finishes
					playingNotificationSound.set(false);
				});
			}
		}
	});
</script>

<div
	role="status"
	aria-live="polite"
	class="group relative flex w-[20.75rem] max-w-[calc(100vw-2rem)] -translate-x-1 gap-2.5 rounded-xl border border-gray-200 bg-white px-4 py-3.5 pr-10 text-left text-gray-900 shadow-lg cursor-pointer select-none dark:border-gray-800 dark:bg-gray-900 dark:text-gray-100"
	on:dragstart|preventDefault
	on:pointerdown={onPointerDown}
	on:pointermove={onPointerMove}
	on:pointerup={onPointerUp}
	on:pointercancel={() => (moved = true)}
	on:keydown={(e) => {
		if (e.key === 'Enter' || e.key === ' ') {
			e.preventDefault();
			clickHandler();
		}
	}}
>
	<button
		bind:this={closeButtonElement}
		class="absolute right-2 top-1/2 z-10 grid size-6 -translate-y-1/2 place-items-center rounded-md text-gray-500 transition hover:bg-gray-100 hover:text-gray-900 dark:text-gray-400 dark:hover:bg-gray-800 dark:hover:text-white"
		on:click|stopPropagation={closeHandler}
		aria-label="Fechar notificação"
	>
		<XMark className="size-4" />
	</button>

	<div class="shrink-0 self-top -translate-y-0.5">
		<img src="{NEVEAI_BASE_URL}/static/favicon.png" alt="favicon" class="size-6 rounded-full" />
	</div>

	<div>
		{#if title}
			<div class=" text-[13px] font-medium mb-0.5 line-clamp-1">{title}</div>
		{/if}

		<div class="line-clamp-2 self-center text-xs font-normal text-gray-500 dark:text-gray-400">
			{@html DOMPurify.sanitize(marked(DOMPurify.sanitize(content, { ALLOWED_TAGS: [] })))}
		</div>
	</div>
</div>
