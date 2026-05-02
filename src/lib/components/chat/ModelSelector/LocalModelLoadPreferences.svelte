<script lang="ts">
	import { onMount } from 'svelte';
	import { DropdownMenu } from 'bits-ui';

	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import Bookmark from '$lib/components/icons/Bookmark.svelte';
	import { flyAndScale } from '$lib/utils/transitions';
	import {
		LOCAL_MODEL_CONTEXT_OPTIONS,
		getContextPreferenceLabel,
		getLocalModelLoadPreferences,
		getVisionPreferenceLabel,
		setLocalModelContextPreference,
		setLocalModelVisionPreference,
		type LocalModelContextPreference,
		type LocalModelVisionPreference
	} from '$lib/utils/llamacppLoadPreferences';

	let show = false;
	let contextPreference: LocalModelContextPreference = 'ask';
	let visionPreference: LocalModelVisionPreference = 'ask';

	const contextOptions: LocalModelContextPreference[] = ['ask', ...LOCAL_MODEL_CONTEXT_OPTIONS];
	const visionOptions: LocalModelVisionPreference[] = ['ask', 'yes', 'no'];

	$: contextOptionIndex =
		typeof contextPreference === 'number'
			? LOCAL_MODEL_CONTEXT_OPTIONS.indexOf(contextPreference)
			: -1;

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

	const resetContextPreference = () => {
		contextPreference = 'ask';
		setLocalModelContextPreference(contextPreference);
	};

	const resetVisionPreference = () => {
		visionPreference = 'ask';
		setLocalModelVisionPreference(visionPreference);
	};

	const stopEventPropagation = (event: Event) => {
		event.stopPropagation();
	};

	onMount(() => {
		const preferences = getLocalModelLoadPreferences();
		contextPreference = preferences.context;
		visionPreference = preferences.vision;
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
		</div>
	</DropdownMenu.Content>
</DropdownMenu.Root>
