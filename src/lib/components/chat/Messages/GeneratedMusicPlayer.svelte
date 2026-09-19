<script lang="ts">
	import { getContext } from 'svelte';
	import { getFileContentById } from '$lib/apis/files';
	import { NEVEAI_BASE_URL } from '$lib/constants';

	export let src = '';
	export let fileId: string | null = null;
	export let name = 'musica.mp3';

	const i18n = getContext('i18n');

	let audioElement: HTMLAudioElement;
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
		if (!audioElement) return;
		if (audioElement.paused) {
			await audioElement.play();
		} else {
			audioElement.pause();
		}
	};

	const seek = (event: Event) => {
		if (!audioElement || duration <= 0) return;
		const target = event.currentTarget as HTMLInputElement;
		audioElement.currentTime = (Number(target.value) / 100) * duration;
	};

	const toggleMuted = () => {
		if (!audioElement) return;
		audioElement.muted = !audioElement.muted;
		muted = audioElement.muted;
	};

	const download = async () => {
		let content: BlobPart | null = null;
		if (fileId) {
			content = await getFileContentById(fileId);
		}
		if (!content) {
			const response = await fetch(resolvedSrc);
			if (!response.ok) return;
			content = await response.blob();
		}

		const blobUrl = URL.createObjectURL(content instanceof Blob ? content : new Blob([content]));
		const anchor = document.createElement('a');
		anchor.href = blobUrl;
		anchor.download = name || 'musica.mp3';
		anchor.style.display = 'none';
		document.body.appendChild(anchor);
		anchor.click();
		anchor.remove();
		setTimeout(() => URL.revokeObjectURL(blobUrl), 1000);
	};
</script>

<div
	class="music-player flex h-[4.25rem] w-full min-w-[18rem] max-w-[28rem] items-center gap-3 rounded-lg border border-gray-200/80 bg-gray-50 px-3.5 text-gray-700 dark:border-gray-700/70 dark:bg-gray-800/55 dark:text-gray-200"
>
	<audio
		bind:this={audioElement}
		src={resolvedSrc}
		preload="metadata"
		playsinline
		on:loadedmetadata={() => (duration = audioElement.duration || 0)}
		on:durationchange={() => (duration = audioElement.duration || 0)}
		on:timeupdate={() => (currentTime = audioElement.currentTime || 0)}
		on:play={() => (playing = true)}
		on:pause={() => (playing = false)}
		on:ended={() => {
			playing = false;
			currentTime = 0;
		}}
	/>

	<button
		type="button"
		class="flex size-9 shrink-0 items-center justify-center rounded-full bg-gray-900 text-white transition-colors hover:bg-gray-700 dark:bg-gray-100 dark:text-gray-900 dark:hover:bg-white"
		aria-label={playing ? 'Pausar' : 'Reproduzir'}
		title={playing ? 'Pausar' : 'Reproduzir'}
		on:click={togglePlayback}
	>
		{#if playing}
			<svg viewBox="0 0 24 24" fill="currentColor" class="size-4" aria-hidden="true">
				<path d="M7.5 5.25A.75.75 0 0 1 8.25 4.5h1.5a.75.75 0 0 1 .75.75v13.5a.75.75 0 0 1-.75.75h-1.5a.75.75 0 0 1-.75-.75V5.25Zm6 0a.75.75 0 0 1 .75-.75h1.5a.75.75 0 0 1 .75.75v13.5a.75.75 0 0 1-.75.75h-1.5a.75.75 0 0 1-.75-.75V5.25Z" />
			</svg>
		{:else}
			<svg viewBox="0 0 24 24" fill="currentColor" class="ml-0.5 size-4" aria-hidden="true">
				<path d="M7.5 5.77a.75.75 0 0 1 1.14-.64l10 6.23a.75.75 0 0 1 0 1.28l-10 6.23a.75.75 0 0 1-1.14-.64V5.77Z" />
			</svg>
		{/if}
	</button>

	<div class="flex min-w-0 flex-1 translate-y-[4px] flex-col gap-1.5">
		<input
			type="range"
			min="0"
			max="100"
			step="0.1"
			value={progress}
			aria-label={$i18n.t('Playback position')}
			class="music-progress translate-y-[9px] w-full cursor-pointer"
			style="--music-progress: {progress}%"
			on:input={seek}
		/>
		<div class="flex justify-between text-[0.6875rem] tabular-nums text-gray-500 dark:text-gray-400">
			<span>{formatTime(currentTime)}</span>
			<span>{formatTime(duration)}</span>
		</div>
	</div>

	<div class="flex shrink-0 items-center gap-1">
		<button
			type="button"
			class="flex size-8 shrink-0 items-center justify-center rounded-md transition-colors hover:bg-black/5 hover:text-gray-950 dark:hover:bg-white/10 dark:hover:text-white"
			aria-label={muted ? 'Desilenciar' : 'Silenciar'}
			title={muted ? 'Desilenciar' : 'Silenciar'}
			on:click={toggleMuted}
		>
			{#if muted}
				<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" class="size-[1.1rem]" aria-hidden="true">
					<path stroke-linecap="round" stroke-linejoin="round" d="M11 5 6.8 8.5H4.5v7h2.3L11 19V5Zm5.2 5.2 4 4m0-4-4 4" />
				</svg>
			{:else}
				<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" class="size-[1.1rem]" aria-hidden="true">
					<path stroke-linecap="round" stroke-linejoin="round" d="M11 5 6.8 8.5H4.5v7h2.3L11 19V5Zm4.2 3.4a5 5 0 0 1 0 7.2m2.6-9.8a8.5 8.5 0 0 1 0 12.4" />
				</svg>
			{/if}
		</button>

		<button
			type="button"
			class="flex size-8 shrink-0 items-center justify-center rounded-md transition-colors hover:bg-black/5 hover:text-gray-950 dark:hover:bg-white/10 dark:hover:text-white"
			aria-label={$i18n.t('Download')}
			title={$i18n.t('Download')}
			on:click={download}
		>
			<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" class="size-[1.1rem]" aria-hidden="true">
				<path stroke-linecap="round" stroke-linejoin="round" d="M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2M7 11l5 5 5-5M12 4v12" />
			</svg>
		</button>
	</div>
</div>

<style>
	.music-player audio {
		display: none;
	}

	.music-progress {
		height: 0.875rem;
		margin: 0;
		appearance: none;
		-webkit-appearance: none;
		background: transparent;
	}

	.music-progress::-webkit-slider-runnable-track {
		height: 0.25rem;
		border-radius: 9999px;
		background: linear-gradient(
			to right,
			rgb(31 41 55) 0,
			rgb(31 41 55) var(--music-progress),
			rgb(209 213 219) var(--music-progress),
			rgb(209 213 219) 100%
		);
	}

	.music-progress::-webkit-slider-thumb {
		width: 0.75rem;
		height: 0.75rem;
		margin-top: -0.25rem;
		appearance: none;
		-webkit-appearance: none;
		border: 2px solid rgb(255 255 255);
		border-radius: 9999px;
		background: rgb(31 41 55);
		box-shadow: 0 0 0 1px rgb(31 41 55 / 0.2);
	}

	:global(.dark) .music-progress::-webkit-slider-runnable-track {
		background: linear-gradient(
			to right,
			rgb(229 231 235) 0,
			rgb(229 231 235) var(--music-progress),
			rgb(75 85 99) var(--music-progress),
			rgb(75 85 99) 100%
		);
	}

	.music-progress::-moz-range-track {
		height: 0.25rem;
		border-radius: 9999px;
		background: rgb(209 213 219);
	}

	.music-progress::-moz-range-progress {
		height: 0.25rem;
		border-radius: 9999px;
		background: rgb(31 41 55);
	}

	.music-progress::-moz-range-thumb {
		width: 0.625rem;
		height: 0.625rem;
		border: 2px solid rgb(255 255 255);
		border-radius: 9999px;
		background: rgb(31 41 55);
	}

	:global(.dark) .music-progress::-moz-range-progress,
	:global(.dark) .music-progress::-moz-range-thumb {
		background: rgb(229 231 235);
	}
</style>
