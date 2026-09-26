<script lang="ts">
	import { getContext, onDestroy } from 'svelte';
	import type { I18nStore } from '$lib/i18n';
	const i18n = getContext<I18nStore>('i18n');
	import XMark from '$lib/components/icons/XMark.svelte';

	export let show = false;
	export let src = '';
	export let initialTime = 0;
	export let autoplay = false;
	export let onDownload: () => void | Promise<void> = () => {};

	let previewElement: HTMLDivElement;
	let videoElement: HTMLVideoElement;
	let mountedInBody = false;
	let playing = false;
	let currentTime = 0;
	let duration = 0;
	let muted = false;

	$: progress = duration > 0 ? Math.min(100, (currentTime / duration) * 100) : 0;

	const formatTime = (seconds: number) => {
		if (!Number.isFinite(seconds) || seconds < 0) return '0:00';
		const minutes = Math.floor(seconds / 60);
		const remainingSeconds = Math.floor(seconds % 60);
		return `${minutes}:${remainingSeconds.toString().padStart(2, '0')}`;
	};

	const togglePlayback = async () => {
		if (!videoElement) return;
		if (videoElement.paused) await videoElement.play();
		else videoElement.pause();
	};

	const seek = (event: Event) => {
		if (!videoElement || duration <= 0) return;
		videoElement.currentTime =
			(Number((event.currentTarget as HTMLInputElement).value) / 100) * duration;
	};

	const toggleMuted = () => {
		if (!videoElement) return;
		videoElement.muted = !videoElement.muted;
		muted = videoElement.muted;
	};

	const close = () => {
		videoElement?.pause();
		show = false;
	};

	const handleKeyDown = (event: KeyboardEvent) => {
		if (event.key === 'Escape') close();
	};

	$: if (show && previewElement && !mountedInBody) {
		document.body.appendChild(previewElement);
		mountedInBody = true;
		window.addEventListener('keydown', handleKeyDown);
		document.body.style.overflow = 'hidden';
	} else if (!show && previewElement && mountedInBody) {
		window.removeEventListener('keydown', handleKeyDown);
		previewElement.remove();
		mountedInBody = false;
		document.body.style.overflow = '';
	}

	onDestroy(() => {
		window.removeEventListener('keydown', handleKeyDown);
		if (mountedInBody) previewElement?.remove();
		document.body.style.overflow = '';
	});
</script>

{#if show}
	<div
		bind:this={previewElement}
		class="modal fixed inset-0 z-9999 flex h-[100dvh] w-full items-center justify-center overflow-hidden bg-black text-white"
		role="dialog"
		aria-modal="true"
		aria-label={$i18n.t('Video preview')}
	>
		<div class="absolute inset-x-0 top-0 z-20 flex items-center justify-between">
			<button type="button" class="p-5 text-white" aria-label={$i18n.t('Close')} title={$i18n.t('Close')} on:click={close}>
				<XMark className="size-6" />
			</button>
			<button
				type="button"
				class="p-5 text-white"
				aria-label={$i18n.t('Download')}
				title={$i18n.t('Download')}
				on:click={() => onDownload()}
			>
				<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" class="size-6" aria-hidden="true">
					<path stroke-linecap="round" stroke-linejoin="round" d="M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2M7 11l5 5 5-5M12 4v12" />
				</svg>
			</button>
		</div>

		<div class="relative flex max-h-[calc(100dvh-7rem)] max-w-[calc(100vw-2rem)] overflow-hidden rounded-lg">
			<!-- Generated clips do not have a caption track available. -->
			<!-- svelte-ignore a11y_media_has_caption -->
			<video
				bind:this={videoElement}
				playsinline
				preload="metadata"
				{src}
				class="block max-h-[calc(100dvh-7rem)] max-w-[calc(100vw-2rem)] object-contain"
				on:loadedmetadata={async () => {
					duration = videoElement.duration || 0;
					currentTime = Math.min(initialTime, duration || initialTime);
					if (currentTime > 0) videoElement.currentTime = currentTime;
					if (autoplay) await videoElement.play().catch(() => undefined);
				}}
				on:durationchange={() => (duration = videoElement.duration || 0)}
				on:timeupdate={() => (currentTime = videoElement.currentTime || 0)}
				on:play={() => (playing = true)}
				on:pause={() => (playing = false)}
				on:ended={() => {
					playing = false;
					currentTime = duration;
				}}
				on:click={togglePlayback}
			></video>

			<div class="absolute inset-x-1 bottom-1 flex h-11 items-center gap-2.5 px-3">
				<button type="button" class="grid size-8 shrink-0 place-items-center p-0 text-white drop-shadow-md" aria-label={$i18n.t(playing ? 'Pause' : 'Play')} title={$i18n.t(playing ? 'Pause' : 'Play')} on:click={togglePlayback}>
					{#if playing}
						<svg viewBox="0 0 24 24" fill="currentColor" class="block size-5" aria-hidden="true"><rect x="6.5" y="5" width="4.25" height="14" rx="0.8" /><rect x="13.25" y="5" width="4.25" height="14" rx="0.8" /></svg>
					{:else}
						<svg viewBox="0 0 24 24" fill="currentColor" class="block size-5" aria-hidden="true"><path d="M8 5.77a.75.75 0 0 1 1.14-.64l10 6.23a.75.75 0 0 1 0 1.28l-10 6.23A.75.75 0 0 1 8 18.23V5.77Z" /></svg>
					{/if}
				</button>
				<span class="w-[2.3rem] shrink-0 text-[0.6875rem] tabular-nums drop-shadow-md">{formatTime(currentTime)}</span>
				<input type="range" min="0" max="100" step="0.1" value={progress} aria-label={$i18n.t('Playback position')} class="preview-progress min-w-0 flex-1 cursor-pointer" style="--preview-progress: {progress}%" on:input={seek} />
				<span class="w-[2.3rem] shrink-0 text-right text-[0.6875rem] tabular-nums drop-shadow-md">{formatTime(duration)}</span>
				<button type="button" class="grid size-8 place-items-center text-white drop-shadow-md" aria-label={$i18n.t(muted ? 'Unmute' : 'Mute')} title={$i18n.t(muted ? 'Unmute' : 'Mute')} on:click={toggleMuted}>
					{#if muted}
						<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" class="size-[1.05rem]" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M11 5 6.8 8.5H4.5v7h2.3L11 19V5Zm5.2 5.2 4 4m0-4-4 4" /></svg>
					{:else}
						<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" class="size-[1.05rem]" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M11 5 6.8 8.5H4.5v7h2.3L11 19V5Zm4.2 3.4a5 5 0 0 1 0 7.2m2.6-9.8a8.5 8.5 0 0 1 0 12.4" /></svg>
					{/if}
				</button>
			</div>
		</div>
	</div>
{/if}

<style>
	.preview-progress { height: 0.875rem; margin: 0; appearance: none; -webkit-appearance: none; background: transparent; }
	.preview-progress::-webkit-slider-runnable-track { height: 0.2rem; border-radius: 9999px; background: linear-gradient(to right, white 0, white var(--preview-progress), rgb(107 114 128) var(--preview-progress), rgb(107 114 128) 100%); }
	.preview-progress::-webkit-slider-thumb { width: 0.75rem; height: 0.75rem; margin-top: -0.275rem; appearance: none; -webkit-appearance: none; border: 2px solid white; border-radius: 9999px; background: white; }
	.preview-progress::-moz-range-track { height: 0.2rem; border-radius: 9999px; background: rgb(107 114 128); }
	.preview-progress::-moz-range-progress { height: 0.2rem; border-radius: 9999px; background: white; }
	.preview-progress::-moz-range-thumb { width: 0.625rem; height: 0.625rem; border: 2px solid white; border-radius: 9999px; background: white; }
</style>
