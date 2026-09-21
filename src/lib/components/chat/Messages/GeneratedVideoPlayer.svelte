<script lang="ts">
	import { getContext } from 'svelte';
	import { getFileContentById } from '$lib/apis/files';
	import { NEVEAI_BASE_URL } from '$lib/constants';

	export let src = '';
	export let fileId: string | null = null;
	export let name = 'video.mp4';

	const i18n = getContext('i18n');
	let playerElement: HTMLDivElement;
	let videoElement: HTMLVideoElement;
	let playing = false;
	let currentTime = 0;
	let duration = 0;
	let muted = false;

	$: resolvedSrc = src.startsWith('/') ? `${NEVEAI_BASE_URL}${src}` : src;
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

	const toggleFullscreen = async () => {
		if (!playerElement) return;
		if (document.fullscreenElement) await document.exitFullscreen();
		else await playerElement.requestFullscreen();
	};

	const download = async () => {
		let content: BlobPart | null = null;
		if (fileId) content = await getFileContentById(fileId);
		if (!content) {
			const response = await fetch(resolvedSrc, { credentials: 'include' });
			if (!response.ok) return;
			content = await response.blob();
		}

		const objectUrl = URL.createObjectURL(content instanceof Blob ? content : new Blob([content]));
		const anchor = document.createElement('a');
		anchor.href = objectUrl;
		anchor.download = name || 'video.mp4';
		anchor.style.display = 'none';
		document.body.appendChild(anchor);
		anchor.click();
		anchor.remove();
		setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
	};
</script>

<div
	bind:this={playerElement}
	class="video-player relative aspect-video w-full max-w-[32rem] self-start overflow-hidden rounded-lg bg-transparent text-gray-700 dark:text-gray-200"
>
	<!-- Generated clips do not have a caption track available. -->
	<!-- svelte-ignore a11y_media_has_caption -->
	<video
		bind:this={videoElement}
		playsinline
		preload="metadata"
		src={resolvedSrc}
		class="absolute inset-0 block size-full object-cover"
		on:loadedmetadata={() => (duration = videoElement.duration || 0)}
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

	<div class="video-controls absolute inset-x-1 bottom-1 flex h-11 items-center gap-2.5 rounded-md bg-white/10 px-3 backdrop-blur-[3px] dark:bg-black/10">
		<button
			type="button"
			class="grid size-8 shrink-0 place-items-center rounded-full bg-gray-100 p-0 text-gray-900 transition-colors hover:bg-gray-200 dark:bg-gray-100 dark:hover:bg-white"
			aria-label={playing ? 'Pausar' : 'Reproduzir'}
			title={playing ? 'Pausar' : 'Reproduzir'}
			on:click={togglePlayback}
		>
			{#if playing}
				<svg viewBox="0 0 24 24" fill="currentColor" class="block size-3.5" aria-hidden="true"><rect x="7.25" y="5" width="3.5" height="14" rx="0.75" /><rect x="13.25" y="5" width="3.5" height="14" rx="0.75" /></svg>
			{:else}
				<svg viewBox="0 0 24 24" fill="currentColor" class="block size-3.5" aria-hidden="true"><path d="M8 5.77a.75.75 0 0 1 1.14-.64l10 6.23a.75.75 0 0 1 0 1.28l-10 6.23A.75.75 0 0 1 8 18.23V5.77Z" /></svg>
			{/if}
		</button>

		<span class="w-[2.3rem] shrink-0 text-[0.6875rem] tabular-nums text-white drop-shadow-md dark:text-gray-200">{formatTime(currentTime)}</span>
		<input
			type="range"
			min="0"
			max="100"
			step="0.1"
			value={progress}
			aria-label={$i18n.t('Playback position')}
			class="video-progress min-w-0 flex-1 cursor-pointer"
			style="--video-progress: {progress}%"
			on:input={seek}
		/>
		<span class="w-[2.3rem] shrink-0 text-right text-[0.6875rem] tabular-nums text-white drop-shadow-md dark:text-gray-200">{formatTime(duration)}</span>

		<div class="flex shrink-0 items-center gap-0.5">
			<button type="button" class="grid size-8 place-items-center rounded-md p-0 text-white drop-shadow-md transition-colors hover:bg-white/15 hover:text-white dark:text-gray-200 dark:hover:bg-white/10 dark:hover:text-white" aria-label={muted ? 'Desilenciar' : 'Silenciar'} title={muted ? 'Desilenciar' : 'Silenciar'} on:click={toggleMuted}>
				{#if muted}
					<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" class="size-[1.05rem]" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M11 5 6.8 8.5H4.5v7h2.3L11 19V5Zm5.2 5.2 4 4m0-4-4 4" /></svg>
				{:else}
					<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" class="size-[1.05rem]" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M11 5 6.8 8.5H4.5v7h2.3L11 19V5Zm4.2 3.4a5 5 0 0 1 0 7.2m2.6-9.8a8.5 8.5 0 0 1 0 12.4" /></svg>
				{/if}
			</button>
			<button type="button" class="grid size-8 place-items-center rounded-md p-0 text-white drop-shadow-md transition-colors hover:bg-white/15 hover:text-white dark:text-gray-200 dark:hover:bg-white/10 dark:hover:text-white" aria-label="Tela cheia" title="Tela cheia" on:click={toggleFullscreen}>
				<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" class="size-[1.05rem]" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3" /></svg>
			</button>
			<button type="button" class="grid size-8 place-items-center rounded-md p-0 text-white drop-shadow-md transition-colors hover:bg-white/15 hover:text-white dark:text-gray-200 dark:hover:bg-white/10 dark:hover:text-white" aria-label={$i18n.t('Download')} title={$i18n.t('Download')} on:click={download}>
				<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" class="size-[1.05rem]" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2M7 11l5 5 5-5M12 4v12" /></svg>
			</button>
		</div>
	</div>
</div>

<style>
	.video-player:fullscreen {
		position: fixed !important;
		inset: 0 !important;
		width: 100dvw !important;
		height: 100dvh !important;
		min-width: 100dvw;
		min-height: 100dvh;
		max-width: none;
		aspect-ratio: auto;
		overflow: hidden;
		margin: 0 !important;
		padding: 0 !important;
		border: 0;
		border-radius: 0;
		clip-path: none;
		background: transparent;
	}

	.video-player {
		border-radius: 0.5rem;
		clip-path: inset(0 round 0.5rem);
	}

	.video-player > video {
		margin: 0 !important;
		border-radius: inherit;
		transform: none;
	}

	.video-player:fullscreen video {
		position: absolute;
		inset: 0;
		width: 100%;
		height: 100%;
		border-radius: 0;
		object-fit: cover;
		transform: none;
	}

	.video-progress {
		height: 0.875rem;
		margin: 0;
		appearance: none;
		-webkit-appearance: none;
		background: transparent;
	}

	.video-progress::-webkit-slider-runnable-track {
		height: 0.25rem;
		border-radius: 9999px;
		background: linear-gradient(to right, rgb(31 41 55) 0, rgb(31 41 55) var(--video-progress), rgb(156 163 175) var(--video-progress), rgb(156 163 175) 100%);
	}

	.video-progress::-webkit-slider-thumb {
		width: 0.75rem;
		height: 0.75rem;
		margin-top: -0.25rem;
		appearance: none;
		-webkit-appearance: none;
		border: 2px solid white;
		border-radius: 9999px;
		background: rgb(31 41 55);
	}

	:global(.dark) .video-progress::-webkit-slider-runnable-track {
		background: linear-gradient(to right, rgb(229 231 235) 0, rgb(229 231 235) var(--video-progress), rgb(75 85 99) var(--video-progress), rgb(75 85 99) 100%);
	}

	:global(.dark) .video-progress::-webkit-slider-thumb { background: rgb(229 231 235); }
	.video-progress::-moz-range-track { height: 0.25rem; border-radius: 9999px; background: rgb(156 163 175); }
	.video-progress::-moz-range-progress { height: 0.25rem; border-radius: 9999px; background: rgb(31 41 55); }
	.video-progress::-moz-range-thumb { width: 0.625rem; height: 0.625rem; border: 2px solid white; border-radius: 9999px; background: rgb(31 41 55); }
	:global(.dark) .video-progress::-moz-range-progress,
	:global(.dark) .video-progress::-moz-range-thumb { background: rgb(229 231 235); }
</style>
