<script lang="ts">
	import { getContext, onDestroy } from 'svelte';
	import type { I18nStore } from '$lib/i18n';
	import XMark from '$lib/components/icons/XMark.svelte';
	import MobileModalTitle from '$lib/components/common/MobileModalTitle.svelte';
	import Spinner from '$lib/components/common/Spinner.svelte';
	const i18n = getContext<I18nStore>('i18n');

	export let show = false;
	export let aspectRatio = 16 / 9;
	export let ready = false;
	export let onDownload: () => void | Promise<void> = () => {};

	let surface: HTMLDivElement;
	let expanded = false;
	let previousOverflow = '';
	let previousFocus: HTMLElement | null = null;
	let closeButton: HTMLButtonElement;
	const close = () => { show = false; };
	const preventBackgroundScroll = (event: WheelEvent | TouchEvent) => {
		if (!show) return;
		event.stopPropagation();
		if (!(event.target instanceof Element && event.target.closest('input[type="range"]')) || event.type === 'wheel') {
			event.preventDefault();
		}
	};
	const keydown = (event: KeyboardEvent) => {
		if (event.key === 'Escape') {
			event.preventDefault();
			close();
		}
	};
	const release = () => {
		if (!expanded) return;
		window.removeEventListener('keydown', keydown);
		surface?.hidePopover?.();
		document.body.style.overflow = previousOverflow;
		previousFocus?.focus({ preventScroll: true });
		expanded = false;
	};

	$: if (surface && show && !expanded) {
		previousOverflow = document.body.style.overflow;
		previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
		// The top layer escapes chat clipping without moving or replacing the playing video.
		surface.showPopover?.();
		document.body.style.overflow = 'hidden';
		window.addEventListener('keydown', keydown);
		expanded = true;
		closeButton?.focus({ preventScroll: true });
	} else if (!show) release();

	onDestroy(release);
</script>

<div bind:this={surface} popover="manual" class="video-preview-surface" class:expanded={show}
	on:wheel|nonpassive={preventBackgroundScroll} on:touchmove|nonpassive={preventBackgroundScroll}
	role={show ? 'dialog' : undefined} aria-modal={show ? 'true' : undefined}
	aria-label={show ? $i18n.t('Video preview') : undefined}>
	{#if show}
		<div class="preview-header absolute inset-x-0 top-0 z-20 flex items-center justify-between text-white">
			<div class="mobile-video-preview-title"><MobileModalTitle onBack={close}>{$i18n.t('Video preview')}</MobileModalTitle></div>
			<button bind:this={closeButton} data-mobile-modal-close type="button" class="video-preview-close p-5" aria-label={$i18n.t('Close')} title={$i18n.t('Close')} on:click={close}>
				<XMark className="size-6" />
			</button>
			<button type="button" class="p-5" aria-label={$i18n.t('Download')} title={$i18n.t('Download')} on:click={() => onDownload()}>
				<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" class="size-6" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2M7 11l5 5 5-5M12 4v12" /></svg>
			</button>
		</div>
	{/if}
	{#if show && !ready}
		<div class="pointer-events-none absolute inset-0 grid place-items-center"><Spinner className="size-6 text-gray-400" /></div>
	{/if}
	<div class="video-preview-frame" class:invisible={show && !ready} style={show ? `aspect-ratio: ${aspectRatio}; width: min(calc(100vw - 2rem), calc((100dvh - 7rem) * ${aspectRatio}));` : ''}>
		<slot />
	</div>
</div>

<style>
	.video-preview-surface { display: block; position: absolute; inset: 0; width: 100%; height: 100%; max-width: none; max-height: none; margin: 0; padding: 0; border: 0; overflow: visible; background: transparent; color: inherit; }
	.video-preview-frame { position: relative; width: 100%; height: 100%; overflow: hidden; border-radius: 0.625rem; }
	.video-preview-surface.expanded { display: grid; place-items: center; position: fixed; inset: 0; width: 100vw; height: 100dvh; background: black; color: white; z-index: 9999; }
	.expanded .video-preview-frame { height: auto; }
	.expanded :global(video) { object-fit: contain; }
	.mobile-video-preview-title { display: none; }
	@media (max-width: 767px) {
		.mobile-video-preview-title { display: block; padding-left: 16px; }
		.video-preview-close { display: none; }
	}
</style>
