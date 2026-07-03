<script lang="ts">
	import { onMount } from 'svelte';
	import { DropdownMenu } from 'bits-ui';

	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import Bookmark from '$lib/components/icons/Bookmark.svelte';
	import { flyAndScale } from '$lib/utils/transitions';
	import {
		LOCAL_MODEL_CONTEXT_OPTIONS,
		getCachePreferenceLabel,
		getContextPreferenceLabel,
		getContextShiftPreferenceLabel,
		getLocalModelLoadPreferences,
		getSpeculativePreferenceLabel,
		getStreamPreferenceLabel,
		getTokenPredictionPreferenceLabel,
		getVisionPreferenceLabel,
		setLocalModelCachePreference,
		setLocalModelContextPreference,
		setLocalModelContextShiftPreference,
		setLocalModelSpeculativePreference,
		setLocalModelStreamPreference,
		setLocalModelTokenPredictionPreference,
		setLocalModelVisionPreference,
		type LocalModelCachePreference,
		type LocalModelContextPreference,
		type LocalModelContextShiftPreference,
		type LocalModelSpeculativePreference,
		type LocalModelStreamPreference,
		type LocalModelTokenPredictionPreference,
		type LocalModelVisionPreference
	} from '$lib/utils/llamacppLoadPreferences';

	let show = false;
	let contextPreference: LocalModelContextPreference = 'ask';
	let visionPreference: LocalModelVisionPreference = 'ask';
	let cachePreference: LocalModelCachePreference = 'default';
	let streamPreference: LocalModelStreamPreference = 'default';
	let speculativePreference: LocalModelSpeculativePreference = 'default';
	let tokenPredictionPreference: LocalModelTokenPredictionPreference = 'default';
	let contextShiftPreference: LocalModelContextShiftPreference = 'default';

	const contextOptions: LocalModelContextPreference[] = ['ask', ...LOCAL_MODEL_CONTEXT_OPTIONS];
	const visionOptions: LocalModelVisionPreference[] = ['ask', 'yes', 'no'];
	const cacheOptions: LocalModelCachePreference[] = ['default', 'f16', 'q8_0', 'q4_0'];
	const streamOptions: LocalModelStreamPreference[] = ['default', 'on', 'off'];
	const speculativeOptions: LocalModelSpeculativePreference[] = ['default', 'high', 'low', 'off'];
	const tokenPredictionOptions: LocalModelTokenPredictionPreference[] = [
		'default',
		'on',
		'off'
	];
	const contextShiftOptions: LocalModelContextShiftPreference[] = ['default', 'on', 'off'];

	$: contextOptionIndex =
		typeof contextPreference === 'number'
			? LOCAL_MODEL_CONTEXT_OPTIONS.indexOf(contextPreference)
			: -1;
	$: contextShiftActive = contextShiftPreference === 'on';
	$: tokenPredictionActive = tokenPredictionPreference === 'on';
	$: speculativeLocked = tokenPredictionActive || contextShiftActive;
	$: tokenPredictionLocked = contextShiftActive;
	$: effectiveSpeculativePreference = speculativeLocked ? 'off' : speculativePreference;
	$: effectiveTokenPredictionPreference = tokenPredictionLocked ? 'off' : tokenPredictionPreference;

	const cycleContextPreference = () => {
		const idx = contextOptions.indexOf(contextPreference);
		contextPreference = contextOptions[(idx + 1) % contextOptions.length];
		setLocalModelContextPreference(contextPreference);
	};

	const stepContextPreference = (direction: -1 | 1) => {
		if (contextOptionIndex < 0) return;

		const nextIndex = Math.max(
			0,
			Math.min(LOCAL_MODEL_CONTEXT_OPTIONS.length - 1, contextOptionIndex + direction)
		);
		contextPreference = LOCAL_MODEL_CONTEXT_OPTIONS[nextIndex];
		setLocalModelContextPreference(contextPreference);
	};

	const cycleVisionPreference = () => {
		const idx = visionOptions.indexOf(visionPreference);
		visionPreference = visionOptions[(idx + 1) % visionOptions.length];
		setLocalModelVisionPreference(visionPreference);
	};

	const cycleCachePreference = () => {
		const idx = cacheOptions.indexOf(cachePreference);
		cachePreference = cacheOptions[(idx + 1) % cacheOptions.length];
		setLocalModelCachePreference(cachePreference);
	};

	const cycleStreamPreference = () => {
		const idx = streamOptions.indexOf(streamPreference);
		streamPreference = streamOptions[(idx + 1) % streamOptions.length];
		setLocalModelStreamPreference(streamPreference);
	};

	const cycleSpeculativePreference = () => {
		if (speculativeLocked) return;
		const idx = speculativeOptions.indexOf(speculativePreference);
		speculativePreference = speculativeOptions[(idx + 1) % speculativeOptions.length];
		setLocalModelSpeculativePreference(speculativePreference);
	};

	const cycleTokenPredictionPreference = () => {
		if (tokenPredictionLocked) return;
		const idx = tokenPredictionOptions.indexOf(tokenPredictionPreference);
		tokenPredictionPreference = tokenPredictionOptions[(idx + 1) % tokenPredictionOptions.length];
		setLocalModelTokenPredictionPreference(tokenPredictionPreference);
	};

	const cycleContextShiftPreference = () => {
		const idx = contextShiftOptions.indexOf(contextShiftPreference);
		contextShiftPreference = contextShiftOptions[(idx + 1) % contextShiftOptions.length];
		setLocalModelContextShiftPreference(contextShiftPreference);
	};

	const resetContextPreference = () => {
		contextPreference = 'ask';
		setLocalModelContextPreference(contextPreference);
	};

	const resetVisionPreference = () => {
		visionPreference = 'ask';
		setLocalModelVisionPreference(visionPreference);
	};

	const resetCachePreference = () => {
		cachePreference = 'default';
		setLocalModelCachePreference(cachePreference);
	};

	const resetStreamPreference = () => {
		streamPreference = 'default';
		setLocalModelStreamPreference(streamPreference);
	};

	const resetSpeculativePreference = () => {
		if (speculativeLocked) return;
		speculativePreference = 'default';
		setLocalModelSpeculativePreference(speculativePreference);
	};

	const resetTokenPredictionPreference = () => {
		if (tokenPredictionLocked) return;
		tokenPredictionPreference = 'default';
		setLocalModelTokenPredictionPreference(tokenPredictionPreference);
	};

	const resetContextShiftPreference = () => {
		contextShiftPreference = 'default';
		setLocalModelContextShiftPreference(contextShiftPreference);
	};

	const stopEventPropagation = (event: Event) => {
		event.stopPropagation();
	};

	onMount(() => {
		const preferences = getLocalModelLoadPreferences();
		contextPreference = preferences.context;
		visionPreference = preferences.vision;
		cachePreference = preferences.cache;
		streamPreference = preferences.stream;
		speculativePreference = preferences.speculative;
		tokenPredictionPreference = preferences.tokenPrediction;
		contextShiftPreference = preferences.contextShift;
	});
</script>

<DropdownMenu.Root bind:open={show}>
	<Tooltip content="Predefinições" placement="top">
		<DropdownMenu.Trigger
			class="relative z-20 shrink-0 self-center p-0.5 rounded-md hover:bg-black/5 dark:hover:bg-white/5 transition text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300"
			type="button"
			aria-label="Predefinições"
			on:pointerdown={stopEventPropagation}
			on:click={stopEventPropagation}
		>
			<Bookmark className="w-[18px] h-[18px]" strokeWidth="1.5" />
		</DropdownMenu.Trigger>
	</Tooltip>

	<DropdownMenu.Content
		class="z-50 w-76 rounded-md px-1 py-1 border border-gray-100 dark:border-gray-800 bg-white dark:bg-gray-850 dark:text-white shadow-md outline-hidden"
		style="font-family: 'Segoe UI', sans-serif;"
		transition={flyAndScale}
		side="bottom"
		align="start"
		sideOffset={4}
		alignOffset={6}
	>
		<div class="px-3 pt-2 pb-1.5 text-sm font-semibold text-gray-800 dark:text-gray-100">Predefinições</div>
		<div class="mx-3 mb-1 border-t border-gray-100 dark:border-gray-800"></div>
		<div class="flex flex-col gap-1 text-sm">
			<div class="flex w-full justify-between gap-2 items-center px-3 py-1 rounded-sm">
				{#if contextPreference === 'ask'}
					<div class="text-sm text-gray-700 dark:text-gray-200 whitespace-nowrap">Tamanho do contexto</div>
				{:else}
					<button
						type="button"
						class="text-sm text-gray-700 dark:text-gray-200 underline decoration-dotted underline-offset-2 cursor-pointer hover:text-gray-500 dark:hover:text-gray-400 transition whitespace-nowrap"
						on:click|stopPropagation={resetContextPreference}
					>
						Tamanho do contexto
					</button>
				{/if}
				{#if contextPreference === 'ask'}
					<button
						type="button"
						class="px-2.5 py-0.5 rounded-md border border-gray-200 dark:border-gray-700 text-xs text-center text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-800/50 transition shrink-0 whitespace-nowrap"
						on:click|stopPropagation={cycleContextPreference}
					>
						{getContextPreferenceLabel(contextPreference)}
					</button>
				{:else}
					<div
						class="flex items-center overflow-hidden rounded-md border border-gray-200 dark:border-gray-700 divide-x divide-gray-200 dark:divide-gray-700 shrink-0 text-gray-600 dark:text-gray-400"
					>
						<button
							type="button"
							class="h-7 w-6 flex items-center justify-center hover:bg-gray-100 dark:hover:bg-gray-800 transition disabled:opacity-30"
							on:click|stopPropagation={() => stepContextPreference(-1)}
							disabled={contextOptionIndex <= 0}
							aria-label="Diminuir contexto"
						>
							<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" class="size-3" aria-hidden="true">
								<path stroke-linecap="round" stroke-linejoin="round" d="M5 12h14" />
							</svg>
						</button>
						<div class="h-7 w-14 flex items-center justify-center text-xs tabular-nums whitespace-nowrap">
							{getContextPreferenceLabel(contextPreference)}
						</div>
						<button
							type="button"
							class="h-7 w-6 flex items-center justify-center hover:bg-gray-100 dark:hover:bg-gray-800 transition disabled:opacity-30"
							on:click|stopPropagation={() => stepContextPreference(1)}
							disabled={contextOptionIndex >= LOCAL_MODEL_CONTEXT_OPTIONS.length - 1}
							aria-label="Aumentar contexto"
						>
							<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" class="size-3" aria-hidden="true">
								<path stroke-linecap="round" stroke-linejoin="round" d="M12 5v14M5 12h14" />
							</svg>
						</button>
					</div>
				{/if}
			</div>

			<div class="flex w-full justify-between gap-2 items-center px-3 py-1 rounded-sm">
				{#if visionPreference === 'ask'}
					<div class="text-sm text-gray-700 dark:text-gray-200 whitespace-nowrap">Visão multimodal</div>
				{:else}
					<button
						type="button"
						class="text-sm text-gray-700 dark:text-gray-200 underline decoration-dotted underline-offset-2 cursor-pointer hover:text-gray-500 dark:hover:text-gray-400 transition whitespace-nowrap"
						on:click|stopPropagation={resetVisionPreference}
					>
						Visão multimodal
					</button>
				{/if}
				<button
					type="button"
					class="w-[4.75rem] px-0 py-0.5 rounded-full border border-gray-200 dark:border-gray-700 text-xs text-center text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-800/50 transition shrink-0 whitespace-nowrap"
					on:click|stopPropagation={cycleVisionPreference}
				>
					{getVisionPreferenceLabel(visionPreference)}
				</button>
			</div>

			<div class="flex w-full justify-between gap-2 items-center px-3 py-1 rounded-sm">
				{#if cachePreference === 'default'}
					<div class="text-sm text-gray-700 dark:text-gray-200 whitespace-nowrap">Cache KV quantizado</div>
				{:else}
					<button
						type="button"
						class="text-sm text-gray-700 dark:text-gray-200 underline decoration-dotted underline-offset-2 cursor-pointer hover:text-gray-500 dark:hover:text-gray-400 transition whitespace-nowrap"
						on:click|stopPropagation={resetCachePreference}
					>
						Cache KV quantizado
					</button>
				{/if}
				<button
					type="button"
					class="w-[4.75rem] px-0 py-0.5 rounded-full border border-gray-200 dark:border-gray-700 text-xs text-center text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-800/50 transition shrink-0 whitespace-nowrap"
					on:click|stopPropagation={cycleCachePreference}
				>
					{getCachePreferenceLabel(cachePreference)}
				</button>
			</div>

			<div class="flex w-full justify-between gap-2 items-center px-3 py-1 rounded-sm">
				{#if streamPreference === 'default'}
					<div class="text-sm text-gray-700 dark:text-gray-200 whitespace-nowrap">Stream de resposta</div>
				{:else}
					<button
						type="button"
						class="text-sm text-gray-700 dark:text-gray-200 underline decoration-dotted underline-offset-2 cursor-pointer hover:text-gray-500 dark:hover:text-gray-400 transition whitespace-nowrap"
						on:click|stopPropagation={resetStreamPreference}
					>
						Stream de resposta
					</button>
				{/if}
				<button
					type="button"
					class="w-[4.75rem] px-0 py-0.5 rounded-full border border-gray-200 dark:border-gray-700 text-xs text-center text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-800/50 transition shrink-0 whitespace-nowrap"
					on:click|stopPropagation={cycleStreamPreference}
				>
					{getStreamPreferenceLabel(streamPreference)}
				</button>
			</div>

			<div class="flex w-full justify-between gap-2 items-center px-3 py-1 rounded-sm">
				{#if contextShiftPreference === 'default'}
					<div class="text-sm text-gray-700 dark:text-gray-200 whitespace-nowrap">Deslocamento contextual</div>
				{:else}
					<button
						type="button"
						class="text-sm text-gray-700 dark:text-gray-200 underline decoration-dotted underline-offset-2 cursor-pointer hover:text-gray-500 dark:hover:text-gray-400 transition whitespace-nowrap"
						on:click|stopPropagation={resetContextShiftPreference}
					>
						Deslocamento contextual
					</button>
				{/if}
				<button
					type="button"
					class="w-[4.75rem] px-0 py-0.5 rounded-full border border-gray-200 dark:border-gray-700 text-xs text-center text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-800/50 transition shrink-0 whitespace-nowrap"
					on:click|stopPropagation={cycleContextShiftPreference}
				>
					{getContextShiftPreferenceLabel(contextShiftPreference)}
				</button>
			</div>

			<div
				class="flex w-full justify-between gap-2 items-center px-3 py-1 rounded-sm"
				class:opacity-60={speculativeLocked}
			>
				{#if speculativeLocked || speculativePreference === 'default'}
					<div
						class={`text-sm whitespace-nowrap ${
							speculativeLocked
								? 'text-gray-400 dark:text-gray-500'
								: 'text-gray-700 dark:text-gray-200'
						}`}
					>
						Decodificação especulativa
					</div>
				{:else}
					<button
						type="button"
						class="text-sm text-gray-700 dark:text-gray-200 underline decoration-dotted underline-offset-2 cursor-pointer hover:text-gray-500 dark:hover:text-gray-400 transition whitespace-nowrap"
						on:click|stopPropagation={resetSpeculativePreference}
					>
						Decodificação especulativa
					</button>
				{/if}
				<button
					type="button"
					class="w-[4.75rem] px-0 py-0.5 rounded-full border border-gray-200 dark:border-gray-700 text-xs text-center text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-800/50 transition shrink-0 whitespace-nowrap disabled:cursor-not-allowed disabled:text-gray-400 disabled:dark:text-gray-500 disabled:hover:bg-transparent disabled:dark:hover:bg-transparent"
					on:click|stopPropagation={cycleSpeculativePreference}
					disabled={speculativeLocked}
				>
					{getSpeculativePreferenceLabel(effectiveSpeculativePreference)}
				</button>
			</div>

			<div
				class="flex w-full justify-between gap-2 items-center px-3 py-1 rounded-sm"
				class:opacity-60={tokenPredictionLocked}
			>
				{#if tokenPredictionLocked || tokenPredictionPreference === 'default'}
					<div
						class={`text-sm whitespace-nowrap ${
							tokenPredictionLocked
								? 'text-gray-400 dark:text-gray-500'
								: 'text-gray-700 dark:text-gray-200'
						}`}
					>
						Predição de tokens
					</div>
				{:else}
					<button
						type="button"
						class="text-sm text-gray-700 dark:text-gray-200 underline decoration-dotted underline-offset-2 cursor-pointer hover:text-gray-500 dark:hover:text-gray-400 transition whitespace-nowrap"
						on:click|stopPropagation={resetTokenPredictionPreference}
					>
						Predição de tokens
					</button>
				{/if}
				<button
					type="button"
					class="w-[4.75rem] px-0 py-0.5 rounded-full border border-gray-200 dark:border-gray-700 text-xs text-center text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-800/50 transition shrink-0 whitespace-nowrap disabled:cursor-not-allowed disabled:text-gray-400 disabled:dark:text-gray-500 disabled:hover:bg-transparent disabled:dark:hover:bg-transparent"
					on:click|stopPropagation={cycleTokenPredictionPreference}
					disabled={tokenPredictionLocked}
				>
					{getTokenPredictionPreferenceLabel(effectiveTokenPredictionPreference)}
				</button>
			</div>
		</div>
	</DropdownMenu.Content>
</DropdownMenu.Root>
