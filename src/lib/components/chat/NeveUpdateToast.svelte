<script lang="ts">
	import { getContext } from 'svelte';
	import XMark from '$lib/components/icons/XMark.svelte';
	import type { I18nStore } from '$lib/i18n';
	const i18n = getContext<I18nStore>('i18n');

	export let version = '';
	export let onClose: () => void = () => {};
	export let onOpen: () => void = () => {};
</script>

<div class="pointer-events-auto grid w-[20.75rem] max-w-[calc(100vw-2rem)] -translate-x-1 translate-y-5 grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 rounded-xl border border-gray-200 bg-white px-4 py-3 text-gray-900 shadow-lg dark:border-gray-800 dark:bg-gray-900 dark:text-gray-100">
	<div class="min-w-0 self-center">
		<div class="text-sm font-medium">{$i18n.t('Update available')}</div>
		<div class="mt-0.5 text-xs text-gray-500 dark:text-gray-400">{$i18n.t('Version')} {version.replace(/^v(?=\d)/i, '')}</div>
	</div>
	<div class="grid -translate-y-0.5 justify-items-end gap-1 self-center">
		<button type="button" class="grid size-6 place-items-center rounded-md text-gray-500 transition hover:bg-gray-100 hover:text-gray-900 dark:text-gray-400 dark:hover:bg-gray-800 dark:hover:text-white" aria-label={$i18n.t('Close notification')} on:click={onClose}>
			<XMark className="size-4" />
		</button>
		<button type="button" class="mr-1 whitespace-nowrap text-xs font-medium text-gray-700 transition hover:text-gray-950 dark:text-gray-200 dark:hover:text-white" on:click={onOpen}>{$i18n.t('Details')}</button>
	</div>
</div>
