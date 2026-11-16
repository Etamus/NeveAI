<script lang="ts">
	import { getContext } from 'svelte';
	import type { I18nStore } from '$lib/i18n';
	import XCircle from '$lib/components/icons/XCircle.svelte';
	import Spinner from '$lib/components/common/Spinner.svelte';
	import Pause from '$lib/components/icons/Pause.svelte';

	const i18n = getContext<I18nStore>('i18n');

	export let name = 'Modelo';
	export let progress = 0;
	export let label = '';
	export let cancelling = false;
	export let onCancel: () => void = () => {};
	export let onPause: () => void = () => {};

	$: percent = Math.min(100, Math.max(0, Math.round((progress || 0) * 100)));
</script>

<div
	data-model-download-toast
	class="pointer-events-auto w-[20.75rem] max-w-[calc(100vw-2rem)] -translate-x-1 translate-y-5 rounded-xl border border-gray-200 bg-white px-4 py-3 text-gray-900 shadow-lg dark:border-gray-800 dark:bg-gray-900 dark:text-gray-100"
>
	<div class="flex min-w-0 items-center gap-3">
		<div class="min-w-0 flex-1">
			<div class="truncate text-sm font-medium">{name}</div>
		</div>

		<div class="flex shrink-0 items-center gap-1">
		<button data-toast-pause-download type="button" title={$i18n.t('Pause')} aria-label={$i18n.t('Pause')} disabled={cancelling} class="grid size-7 shrink-0 place-items-center rounded-md text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800 disabled:opacity-40" on:click={onPause}><Pause /></button>
		<button
			data-toast-cancel-download
			type="button"
			aria-label={$i18n.t('Cancel')}
			title={$i18n.t('Cancel')}
			class="grid size-7 shrink-0 place-items-center rounded-md text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800 disabled:opacity-40"
			disabled={cancelling}
			on:click={onCancel}
		>
			{#if cancelling}<Spinner className="size-4" />{:else}<XCircle />{/if}
		</button>
		</div>
	</div>

	<div data-toast-progress-bar class="mt-2 h-1.5 overflow-hidden rounded-full bg-gray-100 dark:bg-gray-800">
		<div class="h-full rounded-full bg-black transition-all dark:bg-white" style="width: {percent}%"></div>
	</div>
	<div data-toast-progress-label class="mt-2 flex items-center justify-between gap-3 text-xs text-gray-500 dark:text-gray-400">
		<span class="truncate">{label}</span>
		<span class="shrink-0 text-right">{percent}%</span>
	</div>
</div>
