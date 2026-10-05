<script lang="ts">
	import { getContext, onMount } from 'svelte';
	import { fly } from 'svelte/transition';
	import type { I18nStore } from '$lib/i18n';
	import {
		getLocalModelLoadPreferences,
		getLocalModelAccelerationMode,
		setLocalModelAccelerationMode,
		type LocalModelAccelerationMode,
		RESPONSE_SPEED_CHANGED
	} from '$lib/utils/llamacppLoadPreferences';
	import { REASONING_LEVELS, type ReasoningLevel } from '$lib/utils/reasoningModes';

	export let level: ReasoningLevel = 2;
	export let show = false;
	export let spacious = false;
	export let ongoing = false;
	export let onLevelChange: (level: ReasoningLevel) => void;
	export let position: (node: HTMLElement) => { destroy?: () => void } | void;
	const i18n = getContext<I18nStore>('i18n');
	$: levelLabel = level === 0 ? $i18n.t(REASONING_LEVELS[level]) : `${$i18n.t('Raciocínio')} ${$i18n.t(REASONING_LEVELS[level])}`;
	let accelerationMode: LocalModelAccelerationMode = 'normal';
	const accelerationModes: LocalModelAccelerationMode[] = ['normal', 'de', 'mtp'];
	$: accelerationLabel = accelerationMode === 'normal' ? $i18n.t('Normal') : accelerationMode === 'de' ? $i18n.t('Rápido') : 'MTP';
	let predictionLocked = false;
	function syncPrediction() {
		const preferences = getLocalModelLoadPreferences();
		accelerationMode = getLocalModelAccelerationMode();
		predictionLocked = preferences.contextShift === 'on';
	}
	onMount(() => {
		syncPrediction();
		window.addEventListener(RESPONSE_SPEED_CHANGED, syncPrediction);
		window.addEventListener('storage', syncPrediction);
		return () => {
			window.removeEventListener(RESPONSE_SPEED_CHANGED, syncPrediction);
			window.removeEventListener('storage', syncPrediction);
		};
	});
	function chooseLevel(value: number) {
		onLevelChange(value as ReasoningLevel);
	}
</script>

<svelte:window
	on:keydown={(e) => {
		if (show && e.key === 'Escape') {
			show = false;
			document.querySelector<HTMLButtonElement>('#thinking-dropdown-container > button')?.focus();
		}
	}}
/>

<div class="relative flex items-center self-center" class:mr-1.5={spacious} id="thinking-dropdown-container">
	<button
		type="button"
		aria-label={levelLabel}
		aria-expanded={show}
		aria-controls="reasoning-dropdown"
		class="flex items-center gap-1.5 px-2.5 py-1.5 rounded-full transition cursor-pointer bg-transparent text-gray-600 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-800"
		style="font-size: 0.79rem; font-family: 'Segoe UI', sans-serif; font-weight: 400;"
		on:click|preventDefault={() => {
			show = !show;
		}}
	>
		<span class="text-gray-700 dark:text-gray-200">
			{#if level === 0}{$i18n.t(REASONING_LEVELS[level])}{:else}
				{$i18n.t('Raciocínio')} <span class="text-gray-500 dark:text-gray-400">{$i18n.t(REASONING_LEVELS[level])}</span>
			{/if}
		</span>
		<svg
			xmlns="http://www.w3.org/2000/svg"
			viewBox="0 0 20 20"
			fill="currentColor"
			class="size-3.5 transition-transform {show ? '' : 'rotate-180'}"
			aria-hidden="true"
			><path
				fill-rule="evenodd"
				d="M14.78 12.78a.75.75 0 0 1-1.06 0L10 9.06l-3.72 3.72a.75.75 0 0 1-1.06-1.06l4.25-4.25a.75.75 0 0 1 1.06 0l4.25 4.25a.75.75 0 0 1 0 1.06Z"
				clip-rule="evenodd"
			/></svg
		>
	</button>
	{#if show}
		<div
			id="reasoning-dropdown"
			use:position
			role="dialog"
			tabindex="-1"
			aria-label={$i18n.t('Raciocínio')}
			class="fixed z-50 w-[15.5rem] overflow-hidden rounded-md border border-gray-100 bg-white p-1 text-sm text-gray-700 shadow-md dark:border-gray-800 dark:bg-gray-850 dark:text-gray-200"
			style="font-family: 'Segoe UI', sans-serif;"
			transition:fly={{ y: ongoing ? 5 : -5, duration: 150 }}
			on:click|stopPropagation
			on:keydown={(e) => {
				if (e.key === 'Escape') {
					e.stopPropagation();
					show = false;
					document
						.querySelector<HTMLButtonElement>('#thinking-dropdown-container > button')
						?.focus();
				}
			}}
		>
			<div class="px-2 pt-2 pb-1">
				<div
					class="mb-2 text-center text-sm leading-5 text-gray-800 dark:text-gray-100"
					data-reasoning-level-label
				>
					{#if level === 0}{$i18n.t(REASONING_LEVELS[level])}{:else}
						{$i18n.t('Raciocínio')} <span class="text-gray-500 dark:text-gray-400">{$i18n.t(REASONING_LEVELS[level])}</span>
					{/if}
				</div>
				<div class="effort-track" style="--effort-progress: {(level / 3) * 100}%">
					<div class="effort-dots" aria-hidden="true">
						{#each REASONING_LEVELS as _, index}<span class:active={index <= level}></span>{/each}
					</div>
					<input
						type="range"
						min="0"
						max="3"
						step="1"
						value={level}
						aria-label={$i18n.t('Raciocínio')}
						aria-valuetext={levelLabel}
						on:input={(e) => chooseLevel(Number(e.currentTarget.value))}
					/>
				</div>
			</div>
			<div class="mx-2 my-1 h-px bg-gray-100 dark:bg-gray-800"></div>
			<div
				class="flex w-full items-center justify-between gap-3 px-2 py-2 text-sm text-gray-700 dark:text-gray-200"
				class:opacity-60={predictionLocked}
			>
				<span id="reasoning-speed-label">{$i18n.t('Velocidade')}</span>
				<button
					id="reasoning-speed-control"
					type="button"
					class="w-[4.625rem] shrink-0 whitespace-nowrap rounded-full px-0 py-[0.1875rem] border border-gray-200 dark:border-gray-700 text-xs text-center text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-800/50 transition disabled:cursor-not-allowed disabled:text-gray-400 disabled:dark:text-gray-500 disabled:hover:bg-transparent disabled:dark:hover:bg-transparent"
					disabled={predictionLocked}
					aria-label={`${$i18n.t('Velocidade')}: ${accelerationLabel}`}
					on:click={() => setLocalModelAccelerationMode(accelerationModes[(accelerationModes.indexOf(accelerationMode) + 1) % accelerationModes.length])}
				>{accelerationLabel}</button>
			</div>
		</div>
	{/if}
</div>

<style>
	.effort-track {
		position: relative;
		height: 26px;
		border-radius: 999px;
		border: 1px solid rgb(229 231 235);
		background: linear-gradient(
			to right,
			rgb(59 130 246) var(--effort-progress),
			rgb(247 247 247) var(--effort-progress)
		);
	}
	:global(.dark) .effort-track {
		border-color: rgb(64 64 64);
		background: linear-gradient(
			to right,
			rgb(37 99 235) var(--effort-progress),
			rgb(52 52 52) var(--effort-progress)
		);
	}
	.effort-dots {
		position: absolute;
		inset: 0 11px;
		display: flex;
		align-items: center;
		justify-content: space-between;
		pointer-events: none;
	}
	.effort-dots span {
		width: 4px;
		height: 4px;
		background: rgb(156 163 175 / 0.5);
		border-radius: 50%;
	}
	.effort-dots span.active {
		background: rgb(240 249 250 / 0.45);
	}
	:global(.dark) .effort-dots span {
		background: rgb(156 163 175 / 0.4);
	}
	:global(.dark) .effort-dots span.active {
		background: rgb(240 249 250 / 0.35);
	}
	input {
		position: absolute;
		inset: 0;
		width: 100%;
		margin: 0;
		background: transparent;
		appearance: none;
		cursor: pointer;
		border-radius: inherit;
	}
	input::-webkit-slider-runnable-track {
		height: 24px;
		background: transparent;
	}
	input::-webkit-slider-thumb {
		appearance: none;
		width: 24px;
		height: 24px;
		border: 2px solid rgb(59 130 246);
		border-radius: 50%;
		background: white;
	}
	input::-moz-range-track {
		height: 24px;
		background: transparent;
	}
	input::-moz-range-thumb {
		width: 20px;
		height: 20px;
		border: 2px solid rgb(59 130 246);
		border-radius: 50%;
		background: white;
	}
	:global(.dark) input::-webkit-slider-thumb {
		border-color: rgb(37 99 235);
	}
	:global(.dark) input::-moz-range-thumb {
		border-color: rgb(37 99 235);
	}
	input:focus-visible {
		outline: 2px solid rgb(59 130 246);
		outline-offset: 3px;
	}
	@media (prefers-reduced-motion: reduce) {
		button {
			transition: none;
		}
	}
</style>
