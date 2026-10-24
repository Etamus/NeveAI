<script lang="ts">
	import { getContext } from 'svelte';
	import Spinner from '$lib/components/common/Spinner.svelte';
	import CheckCircle from '$lib/components/icons/CheckCircle.svelte';
	import type { I18nStore } from '$lib/i18n';
	import type {
		LocalModelRuntimeAction,
		LocalModelRuntimePhase
	} from '$lib/apis/llamacpp';

	const i18n = getContext<I18nStore>('i18n');

	export let name = 'Modelo';
	export let action: LocalModelRuntimeAction = 'load';
	export let phase: LocalModelRuntimePhase = 'start';
	export let error = '';

	$: title = action === 'load'
		? phase === 'start'
			? $i18n.t('Carregando modelo')
			: phase === 'success'
				? $i18n.t('Modelo carregado')
				: $i18n.t('Falha ao carregar modelo')
		: phase === 'start'
			? $i18n.t('Descarregando modelo')
			: phase === 'success'
				? $i18n.t('Modelo descarregado')
				: $i18n.t('Falha ao descarregar modelo');
</script>

<div
	class="pointer-events-auto flex w-[20.75rem] max-w-[calc(100vw-2rem)] -translate-x-1 translate-y-5 items-center gap-3 rounded-xl border border-gray-200 bg-white px-4 py-3 text-gray-900 shadow-lg dark:border-gray-800 dark:bg-gray-900 dark:text-gray-100"
>
	<div class="grid size-5 shrink-0 place-items-center text-gray-500 dark:text-gray-400" aria-hidden="true">
		{#if phase === 'start'}
			<Spinner className="size-4" />
		{:else if phase === 'success'}
			<CheckCircle className="size-4" strokeWidth="1.8" />
		{:else}
			<svg viewBox="0 0 20 20" fill="none" class="size-4" stroke="currentColor" stroke-width="1.8">
				<path d="M5 5l10 10M15 5L5 15" stroke-linecap="round" />
			</svg>
		{/if}
	</div>
	<div class="min-w-0 flex-1">
		<div class="truncate text-sm font-medium" title={name}>{name}</div>
		<div class="mt-0.5 truncate text-xs text-gray-500 dark:text-gray-400" title={error || title}>
			{error || title}
		</div>
	</div>
</div>
