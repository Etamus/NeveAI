<script lang="ts">
	import { getContext, onMount } from 'svelte';
	import type { I18nStore } from '$lib/i18n';
	import Minus from '$lib/components/icons/Minus.svelte';
	import Plus from '$lib/components/icons/Plus.svelte';
	import Switch from '$lib/components/common/Switch.svelte';
	import {
		getLocalModelLoadPreferences,
		LOCAL_MODEL_CONTEXT_OPTIONS,
		getVisionPreferenceLabel,
		getCachePreferenceLabel,
		getContextShiftPreferenceLabel,
		setLocalModelContextShiftPreference,
		setLocalModelContextPreference,
		setLocalModelVisionPreference,
		setLocalModelCachePreference,
		RESPONSE_SPEED_CHANGED
	} from '$lib/utils/llamacppLoadPreferences';

	const i18n = getContext<I18nStore>('i18n');
	const labelClass = 'min-w-0 text-left text-[0.8125rem] leading-5 text-gray-700 dark:text-gray-300';
	const resetClass = `${labelClass} setting-reset underline decoration-dotted cursor-pointer hover:text-gray-500 dark:hover:text-gray-400 transition`;
	const controlClass =
		'w-[4.625rem] shrink-0 whitespace-nowrap px-0 py-[0.1875rem] border border-gray-200 dark:border-gray-700 text-xs text-center text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-800/50 transition disabled:cursor-not-allowed disabled:text-gray-400 disabled:dark:text-gray-500 disabled:hover:bg-transparent disabled:dark:hover:bg-transparent';
	const stepClass =
		'h-[1.6875rem] w-6 flex items-center justify-center hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-500 dark:text-gray-400 transition disabled:opacity-30';
	let preferences = getLocalModelLoadPreferences();
	type Preferences = typeof preferences;
	const fields = [
		{
			key: 'cache',
			label: 'Cache KV quantizado',
			options: ['default', 'f16', 'q8_0', 'q4_0'],
			format: getCachePreferenceLabel
		},
		{
			key: 'vision',
			label: 'Visão multimodal',
			options: ['yes', 'no'],
			format: getVisionPreferenceLabel
		},
		{
			key: 'contextShift',
			label: 'Deslocamento contextual',
			options: ['default', 'on', 'off'],
			format: getContextShiftPreferenceLabel
		}
	] as const;
	$: visionEnabled = preferences.vision === 'yes';
	$: contextShiftEnabled = preferences.contextShift === 'on';

	function update<K extends keyof Preferences>(key: K, value: Preferences[K]) {
		if (key === 'contextShift') {
			setLocalModelContextShiftPreference(value as Preferences['contextShift']);
		} else {
			if (key === 'context') setLocalModelContextPreference(value as Preferences['context']);
			else if (key === 'vision') setLocalModelVisionPreference(value as Preferences['vision']);
			else if (key === 'cache') setLocalModelCachePreference(value as Preferences['cache']);
			window.dispatchEvent(new Event(RESPONSE_SPEED_CHANGED));
		}
	}
	function cycle(key: keyof Preferences, options: readonly (string | number)[]) {
		const index = options.indexOf(preferences[key]);
		update(key, options[(index + 1) % options.length] as Preferences[typeof key]);
	}
	$: contextIndex = LOCAL_MODEL_CONTEXT_OPTIONS.indexOf(Number(preferences.context));
	function stepContext(direction: -1 | 1) {
		const value = LOCAL_MODEL_CONTEXT_OPTIONS[contextIndex + direction];
		if (value !== undefined) update('context', value);
	}
	onMount(() => {
		const sync = () => {
			preferences = getLocalModelLoadPreferences();
		};
		sync();
		window.addEventListener(RESPONSE_SPEED_CHANGED, sync);
		window.addEventListener('storage', sync);
		return () => {
			window.removeEventListener(RESPONSE_SPEED_CHANGED, sync);
			window.removeEventListener('storage', sync);
		};
	});
</script>

<div class="load-settings px-4 py-2 text-[0.8125rem] text-gray-700 dark:text-gray-300">
	<div class="space-y-1">
		<div class="setting-row flex min-h-[36px] w-full items-center justify-between gap-3 py-0">
			{#if preferences.context === 'auto'}
				<span class={labelClass}>{$i18n.t('Tamanho do contexto')}</span>
			{:else}
				<button type="button" class={resetClass} on:click={() => update('context', 'auto')}
					>{$i18n.t('Tamanho do contexto')}</button
				>
			{/if}
			{#if preferences.context === 'auto'}
				<button
					id="load-setting-context"
					type="button"
					class={`${controlClass} rounded-full`}
					aria-label={$i18n.t('Tamanho do contexto')}
					on:click={() => cycle('context', ['auto', ...LOCAL_MODEL_CONTEXT_OPTIONS])}
					>{$i18n.t('Dinâmico')}</button
				>
			{:else}
				<div
					class="context-stepper flex shrink-0 items-center overflow-hidden rounded-md border border-gray-200 divide-x divide-gray-200 dark:border-gray-700 dark:divide-gray-700"
				>
					<button
						type="button"
						class={stepClass}
						disabled={contextIndex <= 0}
						aria-label={$i18n.t('Diminuir contexto')}
						on:click={() => stepContext(-1)}><Minus className="size-3" strokeWidth="2.5" /></button
					>
					<span
						id="load-setting-context"
						class="flex h-[1.6875rem] w-[3.625rem] items-center justify-center text-center text-xs tabular-nums"
						style="font-family: 'Segoe UI', system-ui, sans-serif;"
						>{preferences.context.toLocaleString($i18n.language)}</span
					>
					<button
						type="button"
						class={stepClass}
						disabled={contextIndex >= LOCAL_MODEL_CONTEXT_OPTIONS.length - 1}
						aria-label={$i18n.t('Aumentar contexto')}
						on:click={() => stepContext(1)}><Plus className="size-3" strokeWidth="2.5" /></button
					>
				</div>
			{/if}
		</div>
		{#each fields as field}
			<div
				class="setting-row flex min-h-[36px] w-full items-center justify-between gap-3 py-0"
			>
				{#if field.key === 'vision' || field.key === 'contextShift' || preferences[field.key] === field.options[0]}
					<span id={`load-setting-${field.key}-label`} class={labelClass}>{$i18n.t(field.label)}</span>
				{:else}
					<button
						type="button"
						class={resetClass}
						on:click={() => update(field.key, field.options[0])}>{$i18n.t(field.label)}</button
					>
				{/if}
				{#if field.key === 'vision'}
					<div class="shrink-0"><Switch id="load-setting-vision" ariaLabelledbyId="load-setting-vision-label" bind:state={visionEnabled} on:change={(e) => update('vision', e.detail ? 'yes' : 'no')} /></div>
				{:else if field.key === 'contextShift'}
					<div class="shrink-0"><Switch id="load-setting-contextShift" ariaLabelledbyId="load-setting-contextShift-label" bind:state={contextShiftEnabled} on:change={(e) => update('contextShift', e.detail ? 'on' : 'off')} /></div>
				{:else}
				<button
					id={`load-setting-${field.key}`}
					type="button"
					class={`${controlClass} rounded-full`}
					aria-label={$i18n.t(field.label)}
					on:click={() => cycle(field.key, field.options)}
				>
					{$i18n.t(field.format(preferences[field.key] as never))}
				</button>
				{/if}
			</div>
		{/each}
	</div>
</div>
