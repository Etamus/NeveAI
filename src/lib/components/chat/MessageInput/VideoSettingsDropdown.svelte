<script lang="ts">
	import { createEventDispatcher, getContext } from 'svelte';
	import type { I18nStore } from '$lib/i18n';

	const i18n = getContext<I18nStore>('i18n');
	const dispatch = createEventDispatcher();
	export let resolution: '480p' | '672p' = '480p';
	export let duration: '5s' | '8s' = '5s';
	export let open = false;
	export let positionDropdown: (node: HTMLElement) => { destroy(): void } | void;
	let trigger: HTMLButtonElement;

	$: selected = (resolution === '672p' ? 2 : 0) + (duration === '8s' ? 1 : 0);
	function selectCombination(index: number) {
		resolution = index >= 2 ? '672p' : '480p';
		duration = index % 2 ? '8s' : '5s';
		localStorage.setItem('neveai.videoResolution', resolution);
		localStorage.setItem('neveai.videoDuration', duration);
	}
</script>

<svelte:window on:keydown={(event) => {
	if (open && event.key === 'Escape') {
		open = false;
		trigger?.focus();
	}
}} />

	<button
		bind:this={trigger}
		type="button"
		class="flex items-center gap-1.5 px-2 py-[7px] text-[0.8125rem] text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-full whitespace-nowrap"
		aria-label={`${$i18n.t('Video resolution')}, ${$i18n.t('Video duration')}`}
		aria-expanded={open}
		aria-controls={open ? 'video-settings-panel' : undefined}
		on:click|preventDefault={() => {
			const next = !open;
			dispatch('open');
			open = next;
		}}
	>
		<span>{resolution}<span class="mx-1 text-gray-400 dark:text-gray-500">•</span>{duration}</span>
		<svg viewBox="0 0 20 20" fill="currentColor"
			class="size-3.5 shrink-0 transition-transform duration-150 {open ? '' : 'rotate-180'}" aria-hidden="true">
			<path fill-rule="evenodd" d="M14.78 12.78a.75.75 0 0 1-1.06 0L10 9.06l-3.72 3.72a.75.75 0 0 1-1.06-1.06l4.25-4.25a.75.75 0 0 1 1.06 0l4.25 4.25a.75.75 0 0 1 0 1.06Z" clip-rule="evenodd" />
		</svg>
	</button>
	{#if open}
		<div
			id="video-settings-panel"
			use:positionDropdown
			class="fixed z-50 w-[15.5rem] overflow-hidden rounded-md border border-gray-100 bg-white p-1 text-sm text-gray-700 shadow-md dark:border-gray-800 dark:bg-gray-850 dark:text-gray-200"
			style="font-family: 'Segoe UI', sans-serif;"
		>
			<div class="px-2 pt-3 pb-4">
				<div class="mb-3 text-center text-sm leading-5 text-gray-800 dark:text-gray-100" data-video-combination>
					{resolution} <span class="text-gray-500 dark:text-gray-400">• {duration}</span>
				</div>
				<div class="effort-track" style="--effort-progress: {(selected / 3) * 100}%">
					<div class="effort-dots" aria-hidden="true">
						{#each [0, 1, 2, 3] as index}
							<span class:active={index <= selected}></span>
					{/each}
					</div>
					<input type="range" min="0" max="3" step="1" value={selected}
						aria-label={`${$i18n.t('Video resolution')}, ${$i18n.t('Video duration')}`}
						aria-valuetext={`${resolution} • ${duration}`}
						on:input={(event) => selectCombination(Number(event.currentTarget.value))} />
				</div>
			</div>
		</div>
	{/if}

<style>
	.effort-track {
		position: relative;
		height: 26px;
		border-radius: 999px;
		border: 1px solid rgb(229 231 235);
		background: linear-gradient(to right, rgb(59 130 246) var(--effort-progress), rgb(247 247 247) var(--effort-progress));
	}
	:global(.dark) .effort-track {
		border-color: rgb(64 64 64);
		background: linear-gradient(to right, rgb(37 99 235) var(--effort-progress), rgb(52 52 52) var(--effort-progress));
	}
	.effort-dots {
		position: absolute;
		z-index: 1;
		inset: 0;
		padding-inline: 11px;
		border-radius: inherit;
		overflow: hidden;
		display: flex;
		align-items: center;
		justify-content: space-between;
		pointer-events: none;
	}
	.effort-dots span { width: 4px; height: 4px; background: rgb(156 163 175 / 0.5); border-radius: 50%; }
	.effort-dots span.active { background: rgb(240 249 250 / 0.45); }
	:global(.dark) .effort-dots span { background: rgb(156 163 175 / 0.4); }
	:global(.dark) .effort-dots span.active { background: rgb(240 249 250 / 0.35); }
	input {
		position: absolute;
		z-index: 2;
		inset: 0;
		width: 100%;
		margin: 0;
		background: transparent;
		appearance: none;
		cursor: pointer;
		border-radius: inherit;
	}
	input::-webkit-slider-runnable-track { height: 24px; background: transparent; }
	input::-webkit-slider-thumb {
		appearance: none;
		width: 24px;
		height: 24px;
		border: 2px solid rgb(59 130 246);
		border-radius: 50%;
		background: white;
	}
	input::-moz-range-track { height: 24px; background: transparent; }
	input::-moz-range-thumb {
		width: 20px;
		height: 20px;
		border: 2px solid rgb(59 130 246);
		border-radius: 50%;
		background: white;
	}
	:global(.dark) input::-webkit-slider-thumb { border-color: rgb(37 99 235); }
	:global(.dark) input::-moz-range-thumb { border-color: rgb(37 99 235); }
	input:focus-visible { outline: 2px solid rgb(59 130 246); outline-offset: 3px; }
</style>
