<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import { DropdownMenu } from 'bits-ui';

	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import Bookmark from '$lib/components/icons/Bookmark.svelte';
	import ChevronRight from '$lib/components/icons/ChevronRight.svelte';
	import { flyAndScale } from '$lib/utils/transitions';
	import {
		LOCAL_MODEL_CONTEXT_OPTIONS,
		getCachePreferenceLabel,
		getContextPreferenceLabel,
		getContextShiftPreferenceLabel,
		getLocalModelLoadPreferences,
		getSpeculativePreferenceLabel,
		getTokenPredictionPreferenceLabel,
		getVisionPreferenceLabel,
		setLocalModelCachePreference,
		setLocalModelContextPreference,
		setLocalModelContextShiftPreference,
		setLocalModelSpeculativePreference,
		setLocalModelTokenPredictionPreference,
		setLocalModelVisionPreference,
		type LocalModelCachePreference,
		type LocalModelContextPreference,
		type LocalModelContextShiftPreference,
		type LocalModelSpeculativePreference,
		type LocalModelTokenPredictionPreference,
		type LocalModelVisionPreference
	} from '$lib/utils/llamacppLoadPreferences';

	let show = false;
	let contextPreference: LocalModelContextPreference = 'ask';
	let visionPreference: LocalModelVisionPreference = 'ask';
	let cachePreference: LocalModelCachePreference = 'default';
	let speculativePreference: LocalModelSpeculativePreference = 'default';
	let tokenPredictionPreference: LocalModelTokenPredictionPreference = 'default';
	let contextShiftPreference: LocalModelContextShiftPreference = 'default';
	type LocalModelPresetId =
		| 'user'
		| 'light'
		| 'balanced'
		| 'quality'
		| 'high_prediction';

	type LocalModelPreset = {
		id: LocalModelPresetId;
		label: string;
		description: string;
		context?: LocalModelContextPreference;
		vision?: LocalModelVisionPreference;
		cache?: LocalModelCachePreference;
		speculative?: LocalModelSpeculativePreference;
		tokenPrediction?: LocalModelTokenPredictionPreference;
		contextShift?: LocalModelContextShiftPreference;
	};

	const presetStorageKey = 'llamacpp_load_preference_preset';
	const userPresetStorageKey = 'llamacpp_load_preference_user_snapshot';
	let selectedPreset: LocalModelPresetId = 'user';
	let showPresetDropdown = false;
	let presetButtonElement: HTMLButtonElement | null = null;
	let presetMenuElement: HTMLDivElement | null = null;

	const presetOptions: LocalModelPreset[] = [
		{
			id: 'user',
			label: 'Usuário',
			description: ''
		},
		{
			id: 'light',
			label: 'Desempenho',
			description: 'Baixo consumo e contexto',
			context: 4096,
			vision: 'no',
			cache: 'q4_0',
			contextShift: 'on',
			speculative: 'off',
			tokenPrediction: 'off'
		},
		{
			id: 'balanced',
			label: 'Equilibrado',
			description: 'Perfil estável para uso geral',
			context: 8192,
			vision: 'ask',
			cache: 'q8_0',
			contextShift: 'off',
			speculative: 'off',
			tokenPrediction: 'off'
		},
		{
			id: 'quality',
			label: 'Qualidade',
			description: 'Focado em máxima fidelidade',
			context: 16384,
			vision: 'yes',
			cache: 'f16',
			contextShift: 'off',
			speculative: 'off',
			tokenPrediction: 'off'
		},
		{
			id: 'high_prediction',
			label: 'Acelerado',
			description: 'Prioriza velocidade de geração',
			context: 8192,
			vision: 'no',
			cache: 'q8_0',
			contextShift: 'off',
			speculative: 'off',
			tokenPrediction: 'on'
		}
	];

	const contextOptions: LocalModelContextPreference[] = ['ask', ...LOCAL_MODEL_CONTEXT_OPTIONS];
	const visionOptions: LocalModelVisionPreference[] = ['ask', 'yes', 'no'];
	const cacheOptions: LocalModelCachePreference[] = ['default', 'f16', 'q8_0', 'q4_0'];
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
	$: presetLocked = selectedPreset !== 'user';
	$: contextShiftActive = contextShiftPreference === 'on';
	$: tokenPredictionActive = tokenPredictionPreference === 'on';
	$: speculativeLocked = tokenPredictionActive || contextShiftActive;
	$: tokenPredictionLocked = contextShiftActive;
	$: effectiveSpeculativePreference = speculativeLocked ? 'off' : speculativePreference;
	$: effectiveTokenPredictionPreference = tokenPredictionLocked ? 'off' : tokenPredictionPreference;
	$: selectedPresetLabel =
		presetOptions.find((preset) => preset.id === selectedPreset)?.label ?? 'Usuário';
	$: if (!show && showPresetDropdown) {
		showPresetDropdown = false;
	}

	const setStoredPreset = (preset: LocalModelPresetId) => {
		if (typeof localStorage === 'undefined') return;
		localStorage.setItem(presetStorageKey, preset);
	};

	const readStoredPreset = (): LocalModelPresetId => {
		if (typeof localStorage === 'undefined') return 'user';
		const stored = localStorage.getItem(presetStorageKey) as LocalModelPresetId | null;
		return presetOptions.some((preset) => preset.id === stored) ? stored! : 'user';
	};

	const getCurrentUserPresetSnapshot = () => ({
		context: contextPreference,
		vision: visionPreference,
		cache: cachePreference,
		speculative: speculativePreference,
		tokenPrediction: tokenPredictionPreference,
		contextShift: contextShiftPreference
	});

	const saveUserPresetSnapshot = () => {
		if (typeof localStorage === 'undefined') return;
		localStorage.setItem(userPresetStorageKey, JSON.stringify(getCurrentUserPresetSnapshot()));
	};

	const restoreUserPresetSnapshot = () => {
		if (typeof localStorage === 'undefined') return;

		let snapshot = null;
		try {
			snapshot = JSON.parse(localStorage.getItem(userPresetStorageKey) ?? 'null');
		} catch {
			snapshot = null;
		}
		if (!snapshot || typeof snapshot !== 'object') return;

		contextPreference = snapshot.context ?? contextPreference;
		visionPreference = snapshot.vision ?? visionPreference;
		cachePreference = snapshot.cache ?? cachePreference;
		speculativePreference = snapshot.speculative ?? speculativePreference;
		tokenPredictionPreference = snapshot.tokenPrediction ?? tokenPredictionPreference;
		contextShiftPreference = snapshot.contextShift ?? contextShiftPreference;

		setLocalModelContextPreference(contextPreference);
		setLocalModelVisionPreference(visionPreference);
		setLocalModelCachePreference(cachePreference);
		setLocalModelSpeculativePreference(speculativePreference);
		setLocalModelTokenPredictionPreference(tokenPredictionPreference);
		setLocalModelContextShiftPreference(contextShiftPreference);
	};

	const applyLocalModelPreset = (presetId: LocalModelPresetId) => {
		const preset = presetOptions.find((item) => item.id === presetId);
		if (!preset) return;
		const wasUserPreset = selectedPreset === 'user';

		if (wasUserPreset && preset.id !== 'user') {
			saveUserPresetSnapshot();
		}

		selectedPreset = preset.id;
		setStoredPreset(preset.id);
		showPresetDropdown = false;

		if (preset.id === 'user') {
			if (wasUserPreset) {
				saveUserPresetSnapshot();
			} else {
				restoreUserPresetSnapshot();
			}
			return;
		}

		if (preset.context !== undefined) {
			contextPreference = preset.context;
			setLocalModelContextPreference(contextPreference);
		}
		if (preset.vision !== undefined) {
			visionPreference = preset.vision;
			setLocalModelVisionPreference(visionPreference);
		}
		if (preset.cache !== undefined) {
			cachePreference = preset.cache;
			setLocalModelCachePreference(cachePreference);
		}
		if (preset.contextShift !== undefined) {
			contextShiftPreference = preset.contextShift;
			setLocalModelContextShiftPreference(contextShiftPreference);
		}
		if (preset.speculative !== undefined) {
			speculativePreference = preset.speculative;
			setLocalModelSpeculativePreference(speculativePreference);
		}
		if (preset.tokenPrediction !== undefined) {
			tokenPredictionPreference = preset.tokenPrediction;
			setLocalModelTokenPredictionPreference(tokenPredictionPreference);
		}
	};

	const cycleContextPreference = () => {
		if (presetLocked) return;
		const idx = contextOptions.indexOf(contextPreference);
		contextPreference = contextOptions[(idx + 1) % contextOptions.length];
		setLocalModelContextPreference(contextPreference);
	};

	const stepContextPreference = (direction: -1 | 1) => {
		if (presetLocked) return;
		if (contextOptionIndex < 0) return;

		const nextIndex = Math.max(
			0,
			Math.min(LOCAL_MODEL_CONTEXT_OPTIONS.length - 1, contextOptionIndex + direction)
		);
		contextPreference = LOCAL_MODEL_CONTEXT_OPTIONS[nextIndex];
		setLocalModelContextPreference(contextPreference);
	};

	const cycleVisionPreference = () => {
		if (presetLocked) return;
		const idx = visionOptions.indexOf(visionPreference);
		visionPreference = visionOptions[(idx + 1) % visionOptions.length];
		setLocalModelVisionPreference(visionPreference);
	};

	const cycleCachePreference = () => {
		if (presetLocked) return;
		const idx = cacheOptions.indexOf(cachePreference);
		cachePreference = cacheOptions[(idx + 1) % cacheOptions.length];
		setLocalModelCachePreference(cachePreference);
	};

	const cycleSpeculativePreference = () => {
		if (presetLocked || speculativeLocked) return;
		const idx = speculativeOptions.indexOf(speculativePreference);
		speculativePreference = speculativeOptions[(idx + 1) % speculativeOptions.length];
		setLocalModelSpeculativePreference(speculativePreference);
	};

	const cycleTokenPredictionPreference = () => {
		if (presetLocked || tokenPredictionLocked) return;
		const idx = tokenPredictionOptions.indexOf(tokenPredictionPreference);
		tokenPredictionPreference = tokenPredictionOptions[(idx + 1) % tokenPredictionOptions.length];
		setLocalModelTokenPredictionPreference(tokenPredictionPreference);
	};

	const cycleContextShiftPreference = () => {
		if (presetLocked) return;
		const idx = contextShiftOptions.indexOf(contextShiftPreference);
		contextShiftPreference = contextShiftOptions[(idx + 1) % contextShiftOptions.length];
		setLocalModelContextShiftPreference(contextShiftPreference);
	};

	const resetContextPreference = () => {
		if (presetLocked) return;
		contextPreference = 'ask';
		setLocalModelContextPreference(contextPreference);
	};

	const resetVisionPreference = () => {
		if (presetLocked) return;
		visionPreference = 'ask';
		setLocalModelVisionPreference(visionPreference);
	};

	const resetCachePreference = () => {
		if (presetLocked) return;
		cachePreference = 'default';
		setLocalModelCachePreference(cachePreference);
	};

	const resetSpeculativePreference = () => {
		if (presetLocked || speculativeLocked) return;
		speculativePreference = 'default';
		setLocalModelSpeculativePreference(speculativePreference);
	};

	const resetTokenPredictionPreference = () => {
		if (presetLocked || tokenPredictionLocked) return;
		tokenPredictionPreference = 'default';
		setLocalModelTokenPredictionPreference(tokenPredictionPreference);
	};

	const resetContextShiftPreference = () => {
		if (presetLocked) return;
		contextShiftPreference = 'default';
		setLocalModelContextShiftPreference(contextShiftPreference);
	};

	const stopEventPropagation = (event: Event) => {
		event.stopPropagation();
	};

	const togglePresetDropdown = (event: MouseEvent) => {
		event.preventDefault();
		event.stopPropagation();
		showPresetDropdown = !showPresetDropdown;
	};

	const handlePresetOutsidePointerDown = (event: PointerEvent) => {
		if (!showPresetDropdown) return;

		const target = event.target as Node | null;
		if (
			target &&
			(presetButtonElement?.contains(target) || presetMenuElement?.contains(target))
		) {
			return;
		}

		showPresetDropdown = false;

		if (
			target instanceof Element &&
			target.closest('[data-local-model-preferences-root]')
		) {
			event.preventDefault();
			event.stopPropagation();
			event.stopImmediatePropagation();
		}
	};

	onMount(() => {
		document.addEventListener('pointerdown', handlePresetOutsidePointerDown, true);
		const preferences = getLocalModelLoadPreferences();
		contextPreference = preferences.context;
		visionPreference = preferences.vision;
		cachePreference = preferences.cache;
		speculativePreference = preferences.speculative;
		tokenPredictionPreference = preferences.tokenPrediction;
		contextShiftPreference = preferences.contextShift;
		selectedPreset = readStoredPreset();
		if (selectedPreset !== 'user') {
			applyLocalModelPreset(selectedPreset);
		}
	});

	onDestroy(() => {
		document.removeEventListener('pointerdown', handlePresetOutsidePointerDown, true);
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
		data-local-model-preferences-root
		class="relative z-50 w-76 rounded-md px-1 py-1 border border-gray-100 dark:border-gray-800 bg-white dark:bg-gray-850 dark:text-white shadow-md outline-hidden"
		style="font-family: 'Segoe UI', sans-serif;"
		transition={flyAndScale}
		side="bottom"
		align="start"
		sideOffset={4}
		alignOffset={6}
	>
		<div class="flex items-center justify-between gap-2 px-3 pt-2 pb-1.5">
			<div class="text-sm font-semibold text-gray-800 dark:text-gray-100">Predefinições</div>
			<button
				bind:this={presetButtonElement}
				type="button"
				class={`inline-flex h-7 max-w-[8.5rem] items-center gap-1 rounded-md bg-gray-50 px-2.5 text-xs font-medium transition-colors hover:text-gray-800 aria-expanded:text-gray-800 dark:bg-gray-800/70 dark:hover:text-gray-100 dark:aria-expanded:text-gray-100 ${
					selectedPreset === 'user'
						? 'text-gray-500 dark:text-gray-400'
						: 'text-gray-800 dark:text-gray-100'
				}`}
				aria-label="Abrir presets de carregamento"
				aria-expanded={showPresetDropdown}
				on:click={togglePresetDropdown}
			>
				<span class="truncate">{selectedPresetLabel}</span>
				<ChevronRight className="size-3 shrink-0" strokeWidth="2" />
			</button>
		</div>
		{#if showPresetDropdown}
			<div
				bind:this={presetMenuElement}
				class="absolute z-[60] w-56 rounded-md border border-gray-100 bg-white p-1 text-sm text-gray-700 shadow-md outline-hidden dark:border-gray-800 dark:bg-gray-850 dark:text-gray-200"
				style="left: calc(100% - 0.80rem); top: 0.5rem; font-family: 'Segoe UI', sans-serif;"
				transition={flyAndScale}
				on:pointerdown|stopPropagation
			>
				{#each presetOptions as preset, presetIndex}
					{#if presetIndex === 1}
						<div class="mx-2 my-1 border-t border-gray-100 dark:border-gray-800"></div>
					{/if}
					<button
						type="button"
						class="flex w-full cursor-pointer select-none items-center gap-2 rounded-sm px-2 py-1.5 text-left outline-hidden transition hover:bg-gray-50 dark:hover:bg-gray-800"
						on:click|stopPropagation={() => applyLocalModelPreset(preset.id)}
					>
						<div class="min-w-0 flex-1">
							<div class="truncate text-sm leading-5">{preset.label}</div>
							{#if preset.description}
								<div class="truncate text-[11px] leading-4 text-gray-400 dark:text-gray-500">
									{preset.description}
								</div>
							{/if}
						</div>
						<div class="flex size-5 shrink-0 items-center justify-center">
							{#if selectedPreset === preset.id}
								<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.7" stroke="currentColor" class="size-4">
									<path stroke-linecap="round" stroke-linejoin="round" d="M9 12.75 11.25 15 15 9.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
								</svg>
							{/if}
						</div>
					</button>
				{/each}
			</div>
		{/if}
		<div class="mx-3 mb-1 border-t border-gray-100 dark:border-gray-800"></div>
		<div
			class="flex flex-col gap-1 text-sm transition"
			class:opacity-60={presetLocked}
			class:pointer-events-none={presetLocked || showPresetDropdown}
			aria-disabled={presetLocked || showPresetDropdown}
		>
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
