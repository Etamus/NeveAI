<script>
	import { getContext } from 'svelte';
	const i18n = getContext('i18n');
	import WebSearchResults from '../WebSearchResults.svelte';
	import GlobeAlt from '$lib/components/icons/GlobeAlt.svelte';
	import Photo from '$lib/components/icons/Photo.svelte';
	import Search from '$lib/components/icons/Search.svelte';
	import { t } from 'i18next';

	export let status = null;
	export let done = false;

	$: statusAction = String(status?.action ?? '').toLowerCase();
	$: statusDescription = String(status?.description ?? '').toLowerCase();
	$: isImageStatus =
		statusAction.includes('image') ||
		statusAction.includes('stable_diffusion') ||
		statusDescription.includes('image') ||
		statusDescription.includes('imagem');
</script>

{#if !status?.hidden}
	<div class="status-description flex items-center gap-2 py-0.5 w-full text-left">
		{#if status?.action === 'web_search' && (status?.urls || status?.items)}
			<WebSearchResults {status} done={done || status?.done}>
				<span class="text-sm">
					{#if status?.description?.includes('{{count}}')}
						{$i18n.t(status?.description, {
							count: (status?.urls || status?.items).length
						})}
					{:else if status?.description === 'No search query generated'}
						{$i18n.t('No search query generated')}
					{:else if status?.description === 'Generating search query'}
						{$i18n.t('Generating search query')}
					{:else}
						{status?.description}
					{/if}
				</span>
			</WebSearchResults>
		{:else if status?.action === 'web_search'}
			<div class="-ml-3 mb-2 w-[calc(100%+0.75rem)] overflow-hidden rounded-xl text-sm transition-all duration-200">
				<div class="flex items-center justify-between gap-3 px-3 py-2">
					<div
						class="flex min-w-0 flex-1 items-center gap-2 text-sm font-medium text-gray-600 transition-colors dark:text-gray-300"
					>
						<span
							class="flex size-5 shrink-0 items-center justify-center rounded-full bg-white text-gray-500 ring-1 ring-gray-200 dark:bg-white/5 dark:text-gray-300 dark:ring-white/10"
						>
							{#if isImageStatus}
								<Photo className="size-3.5" strokeWidth="1.6" />
							{:else}
								<GlobeAlt className="size-3.5" strokeWidth="1.6" />
							{/if}
						</span>

						<span
							class="relative min-w-0 truncate text-sm leading-5 {(done || status?.done) === false
								? 'shimmer'
								: ''}"
						>
							{#if status?.description?.includes('{{searchQuery}}')}
								{$i18n.t(status?.description, {
									searchQuery: status?.query
								})}
							{:else if status?.description === 'No search query generated'}
								{$i18n.t('No search query generated')}
							{:else if status?.description === 'Generating search query'}
								{$i18n.t('Generating search query')}
							{:else if status?.description === 'Searching the web'}
								{$i18n.t('Searching the web')}
							{:else}
								{status?.description}
							{/if}
						</span>
					</div>
				</div>
			</div>
		{:else if status?.action === 'knowledge_search'}
			<div class="flex flex-col justify-center -space-y-0.5">
				<div
					class="flex items-center gap-2 py-0.5 text-sm {(done || status?.done) === false
						? 'shimmer'
						: ''} text-gray-500 dark:text-gray-400 line-clamp-1 text-wrap"
				>
					<Search className="size-4 shrink-0" />
					{$i18n.t(`Searching Knowledge for "{{searchQuery}}"`, {
						searchQuery: status.query
					})}
				</div>
			</div>
		{:else if status?.action === 'web_search_queries_generated' && status?.queries}
			<div
				class="-ml-3 mb-2 w-[calc(100%+0.75rem)] overflow-hidden rounded-xl text-sm transition-all duration-200"
			>
				<div class="flex items-center justify-between gap-3 px-3 py-2">
					<div
						class="flex min-w-0 flex-1 items-center gap-2 text-sm font-medium text-gray-600 transition-colors dark:text-gray-300"
					>
						<span
							class="flex size-5 shrink-0 items-center justify-center rounded-full bg-white text-gray-500 ring-1 ring-gray-200 dark:bg-white/5 dark:text-gray-300 dark:ring-white/10"
						>
							{#if isImageStatus}
								<Photo className="size-3.5" strokeWidth="1.6" />
							{:else}
								<GlobeAlt className="size-3.5" strokeWidth="1.6" />
							{/if}
						</span>
						<span class="relative min-w-0 truncate text-sm leading-5 {(done || status?.done) === false ? 'shimmer' : ''}">{$i18n.t(`Searching`)}</span>
					</div>
				</div>

				<div class="flex flex-wrap gap-1.5 px-3 pb-2.5 pt-1">
					{#each status.queries as query, idx (query)}
						<div
							class="inline-flex items-center gap-1.5 rounded-md border border-gray-200 dark:border-gray-700/60 bg-white dark:bg-gray-900 px-2 py-1 text-xs text-gray-600 dark:text-gray-300"
						>
							<Search className="size-3" />
							<span class="line-clamp-1">{query}</span>
						</div>
					{/each}
				</div>
			</div>
		{:else if status?.action === 'queries_generated' && status?.queries}
			<div
				class="-ml-3 mb-2 w-[calc(100%+0.75rem)] overflow-hidden rounded-xl text-sm transition-all duration-200"
			>
				<div class="flex items-center justify-between gap-3 px-3 py-2">
					<div
						class="flex min-w-0 flex-1 items-center gap-2 text-sm font-medium text-gray-600 transition-colors dark:text-gray-300"
					>
						<span
							class="flex size-5 shrink-0 items-center justify-center rounded-full bg-white text-gray-500 ring-1 ring-gray-200 dark:bg-white/5 dark:text-gray-300 dark:ring-white/10"
						>
							<GlobeAlt className="size-3.5" strokeWidth="1.6" />
						</span>
						<span class="relative min-w-0 truncate text-sm leading-5 {(done || status?.done) === false ? 'shimmer' : ''}">{$i18n.t(`Querying`)}</span>
					</div>
				</div>

				<div class="flex flex-wrap gap-1.5 px-3 pb-2.5 pt-1">
					{#each status.queries as query, idx (query)}
						<div
							class="inline-flex items-center gap-1.5 rounded-md border border-gray-200 dark:border-gray-700/60 bg-white dark:bg-gray-900 px-2 py-1 text-xs text-gray-600 dark:text-gray-300"
						>
							<Search className="size-3" />
							<span class="line-clamp-1">{query}</span>
						</div>
					{/each}
				</div>
			</div>
		{:else if status?.action === 'sources_retrieved' && status?.count !== undefined}
			<div class="-ml-3 mb-2 w-[calc(100%+0.75rem)] overflow-hidden rounded-xl text-sm transition-all duration-200">
				<div class="flex items-center justify-between gap-3 px-3 py-2">
					<div
						class="flex min-w-0 flex-1 items-center gap-2 text-sm font-medium text-gray-600 transition-colors dark:text-gray-300"
					>
						<span
							class="flex size-5 shrink-0 items-center justify-center rounded-full bg-white text-gray-500 ring-1 ring-gray-200 dark:bg-white/5 dark:text-gray-300 dark:ring-white/10"
						>
							<GlobeAlt className="size-3.5" strokeWidth="1.6" />
						</span>

						<span class="relative min-w-0 truncate text-sm leading-5 {(done || status?.done) === false ? 'shimmer' : ''}">
							{#if status.count === 0}
								{$i18n.t('No sources found')}
							{:else if status.count === 1}
								{$i18n.t('Retrieved 1 source')}
							{:else}
								<!-- {$i18n.t('Source')} -->
								<!-- {$i18n.t('No source available')} -->
								<!-- {$i18n.t('No distance available')} -->
								<!-- {$i18n.t('Retrieved {{count}} sources')} -->
								{$i18n.t('Retrieved {{count}} sources', {
									count: status.count
								})}
							{/if}
						</span>
					</div>
			</div>
			</div>
		{:else}
			<div class="-ml-3 mb-2 w-[calc(100%+0.75rem)] overflow-hidden rounded-xl text-sm transition-all duration-200">
				<div class="flex items-center justify-between gap-3 px-3 py-2">
					<div
						class="flex min-w-0 flex-1 items-center gap-2 text-sm font-medium text-gray-600 transition-colors dark:text-gray-300"
					>
						<span
							class="flex size-5 shrink-0 items-center justify-center rounded-full bg-white text-gray-500 ring-1 ring-gray-200 dark:bg-white/5 dark:text-gray-300 dark:ring-white/10"
						>
							{#if isImageStatus}
								<Photo className="size-3.5" strokeWidth="1.6" />
							{:else}
								<GlobeAlt className="size-3.5" strokeWidth="1.6" />
							{/if}
						</span>
						<span class="relative min-w-0 truncate text-sm leading-5 {(done || status?.done) === false ? 'shimmer' : ''}">
					<!-- $i18n.t(`Searching "{{searchQuery}}"`) -->
					{#if status?.description?.includes('{{searchQuery}}')}
						{$i18n.t(status?.description, {
							searchQuery: status?.query
						})}
					{:else if status?.description === 'No search query generated'}
						{$i18n.t('No search query generated')}
					{:else if status?.description === 'Generating search query'}
						{$i18n.t('Generating search query')}
					{:else if status?.description === 'Searching the web'}
						{$i18n.t('Searching the web')}
					{:else}
						{status?.description}
					{/if}
						</span>
					</div>
			</div>
			</div>
		{/if}
	</div>
{/if}
