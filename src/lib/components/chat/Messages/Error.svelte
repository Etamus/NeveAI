<script lang="ts">
	import Info from '$lib/components/icons/Info.svelte';
	import { getContext } from 'svelte';
	import type { I18nStore } from '$lib/i18n';
	const i18n = getContext<I18nStore>('i18n');

	export let content: any = '';
</script>

<div class="flex my-2 gap-2.5 border px-4 py-3 border-red-600/10 bg-red-600/10 rounded-lg">
	<div class="self-center shrink-0">
		<Info className="size-5 text-red-700 dark:text-red-400" />
	</div>

	<div class=" self-center text-sm">
		{#if typeof content === 'string'}
			{content === 'Model not found' ? $i18n.t('Model not found') : content}
		{:else if typeof content === 'object' && content !== null}
			{#if content?.error && content?.error?.message}
				{content.error.message}
			{:else if content?.detail}
				{content.detail}
			{:else if content?.message}
				{content.message}
			{:else}
				{JSON.stringify(content)}
			{/if}
		{:else}
			{JSON.stringify(content)}
		{/if}
	</div>
</div>
