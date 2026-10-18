<script lang="ts">
	import { getContext, onMount } from 'svelte';
	import { fly } from 'svelte/transition';
	import type { I18nStore } from '$lib/i18n';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import Gauge from '$lib/components/icons/Gauge.svelte';
	import Restore from '$lib/components/icons/Restore.svelte';
	import Bolt from '$lib/components/icons/Bolt.svelte';
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
	export let effortBased = false;
	export let onLevelChange: (level: ReasoningLevel) => void;
	export let position: (node: HTMLElement) => { destroy?: () => void } | void;
	const i18n = getContext<I18nStore>('i18n');
	$: firstLevelLabel = effortBased ? `${$i18n.t('Raciocínio')} ${$i18n.t('Leve')}` : $i18n.t(REASONING_LEVELS[0]);
	$: levelLabel = level === 0 ? firstLevelLabel : `${$i18n.t('Raciocínio')} ${$i18n.t(REASONING_LEVELS[level])}`;
	let accelerationMode: LocalModelAccelerationMode = 'normal';
	let fastSweepFinished = false;
	const accelerationModes: LocalModelAccelerationMode[] = ['normal', 'de', 'mtp'];
	$: accelerationLabel = $i18n.t(accelerationMode === 'normal' ? 'Normal' : accelerationMode === 'de' ? 'Rápido' : 'Predição');
	let predictionLocked = false;
	function syncPrediction() {
		const preferences = getLocalModelLoadPreferences();
		const nextMode = getLocalModelAccelerationMode();
		if (nextMode !== accelerationMode) fastSweepFinished = false;
		accelerationMode = nextMode;
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
		if (accelerationMode === 'de') fastSweepFinished = true;
		onLevelChange(value as ReasoningLevel);
	}
	function resetDefinitions() {
		setLocalModelAccelerationMode('normal', { reset: true });
		chooseLevel(0);
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
		{#if accelerationMode !== 'normal' && !predictionLocked}
			<span class="flex shrink-0" data-acceleration-icon aria-hidden="true"><Bolt className="size-3.5" filled={true} /></span>
		{/if}
		<span class="text-gray-700 dark:text-gray-200">
			{#if level === 0 && !effortBased}{firstLevelLabel}{:else}
				<span class="reasoning-mode-name">{$i18n.t('Raciocínio')}{' '}</span><span class="text-gray-500 dark:text-gray-400">{$i18n.t(level === 0 ? 'Leve' : REASONING_LEVELS[level])}</span>
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
			<div class="flex items-center justify-between px-1 pt-1">
				<Tooltip content={`${$i18n.t('Velocidade')}: <span class="text-gray-400">${accelerationLabel}</span>`} tippyOptions={{ hideOnClick: false }}>
					<button
						id="reasoning-speed-control"
						type="button"
						class="reasoning-tool"
						class:accelerated={accelerationMode !== 'normal'}
						disabled={predictionLocked}
						aria-label={`${$i18n.t('Velocidade')}: ${accelerationLabel}`}
						aria-pressed={accelerationMode !== 'normal'}
						data-mode={accelerationMode}
						on:click={() => setLocalModelAccelerationMode(accelerationModes[(accelerationModes.indexOf(accelerationMode) + 1) % accelerationModes.length])}
					>
						<span class="reasoning-tool-icon"><Gauge className="size-[24px]" /></span>
						<span class="acceleration-indicator" class:invisible={accelerationMode === 'normal'} aria-hidden="true">
							<span></span><span class:hidden={accelerationMode !== 'mtp'}></span>
						</span>
					</button>
				</Tooltip>
				<Tooltip content={$i18n.t('Reset')}>
					<button id="reasoning-reset-control" type="button" class="reasoning-tool" aria-label={$i18n.t('Reset')} on:click={resetDefinitions}>
						<Restore className="size-[18px]" />
					</button>
				</Tooltip>
			</div>
			<div class="px-2 -mt-2 pb-4">
				<div
					class="reasoning-level-label mb-3 text-center text-sm leading-5 text-gray-800 dark:text-gray-100"
					data-reasoning-level-label
				>
					{#if level === 0 && !effortBased}{firstLevelLabel}{:else}
						{$i18n.t('Raciocínio')} <span class="text-gray-500 dark:text-gray-400">{$i18n.t(level === 0 ? 'Leve' : REASONING_LEVELS[level])}</span>
					{/if}
				</div>
				<div
					class="effort-track"
					class:fast-flow={level > 0 && accelerationMode === 'de' && !predictionLocked}
					class:fast-settled={fastSweepFinished}
					class:prediction-flow={level > 0 && accelerationMode === 'mtp' && !predictionLocked}
					style="--effort-progress: {(level / 3) * 100}%; --effort-fraction: {level / 3}"
				>
					{#if level > 0 && accelerationMode === 'mtp' && !predictionLocked}
						<!-- Start the complete particle set together when its count changes. -->
						{#key level}
							<div class="effort-fluid" aria-hidden="true">
								{#each Array(level + 1) as _, index}
									<span style="--particle-phase: {0.1 + index / (level + 1)}"></span>
								{/each}
							</div>
						{/key}
					{/if}
					<div class="effort-dots" aria-hidden="true">
						{#each REASONING_LEVELS as _, index}
							<span class:active={index <= level} style="--dot-index: {index}" on:animationend={() => { if (index === level) fastSweepFinished = true; }}></span>
						{/each}
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
		</div>
	{/if}
</div>

<style>
	.reasoning-tool {
		position: relative;
		/* The raised effort label must not cover the buttons' hit areas. */
		z-index: 1;
		display: flex;
		align-items: center;
		justify-content: center;
		width: 30px;
		height: 30px;
		border-radius: 6px;
		color: rgb(107 114 128);
	}
	.reasoning-tool:hover { background: rgb(243 244 246); }
	:global(.dark) .reasoning-tool { color: rgb(163 163 163); }
	:global(.dark) .reasoning-tool:hover { background: rgb(255 255 255 / 0.06); }
	.reasoning-tool.accelerated, :global(.dark) .reasoning-tool.accelerated { color: rgb(59 130 246); }
	.reasoning-tool:disabled { opacity: 0.45; cursor: not-allowed; background: transparent; }
	.reasoning-tool-icon {
		position: absolute;
		inset: 0;
		pointer-events: none;
	}
	.reasoning-tool.accelerated .reasoning-tool-icon,
	.reasoning-tool.accelerated .acceleration-indicator {
		transform: translateY(-1px);
	}
	.reasoning-tool-icon :global(svg) {
		position: absolute;
		top: 2.5px;
		left: 50%;
		transform: translateX(-50%);
		display: block;
	}
	.reasoning-level-label { position: relative; top: -5px; }
	.acceleration-indicator {
		position: absolute;
		bottom: 3px;
		left: 0;
		right: 0;
		display: flex;
		justify-content: center;
		gap: 2px;
		pointer-events: none;
	}
	.acceleration-indicator span {
		width: 3px;
		height: 3px;
		border-radius: 50%;
		background: currentColor;
	}
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
		z-index: 1;
		inset: 0;
		padding-inline: 11px;
		border-radius: inherit;
		overflow: hidden;
		container-type: inline-size;
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
	.fast-flow:not(.fast-settled) .effort-dots span.active {
		animation: effort-dot-flow 0.32s ease-out both;
		animation-delay: calc(var(--dot-index) * 0.025s);
	}
	.fast-flow.fast-settled .effort-dots span.active { opacity: 0; }
	@keyframes effort-dot-flow {
		0% { transform: translateX(0); opacity: 1; }
		60% { opacity: 0.45; }
		100% { transform: translateX(calc(-1 * var(--dot-index) * (100cqw - 4px) / 3 - 4px)); opacity: 0; }
	}
	.prediction-flow .effort-dots span.active { opacity: 0; }
	.effort-fluid {
		--particle-duration: 0.66s;
		position: absolute;
		inset: 0 auto 0 0;
		width: calc(var(--effort-progress) - 24px * var(--effort-fraction));
		border-radius: 999px 0 0 999px;
		overflow: hidden;
		contain: paint;
		container-type: inline-size;
		pointer-events: none;
	}
	.effort-fluid span {
		position: absolute;
		left: 100%;
		top: calc(50% - 2px);
		width: 4px;
		height: 4px;
		border-radius: 50%;
		background: rgb(224 242 254);
		animation: effort-exhaust var(--particle-duration) linear infinite;
		animation-delay: calc(-1 * var(--particle-duration) * var(--particle-phase));
		will-change: transform, opacity;
	}
	@keyframes effort-exhaust {
		0% { transform: translate(-2px, 0); opacity: 0; }
		12% { opacity: 0.5; }
		78% { opacity: 0.4; }
		100% { transform: translate(calc(-96cqw - 2px), 0); opacity: 0; }
	}
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
		.fast-flow:not(.fast-settled) .effort-dots span.active {
			animation-duration: 0.55s;
		}
		.effort-fluid {
			--particle-duration: 1.2s;
		}
		button {
			transition: none;
		}
	}
</style>
