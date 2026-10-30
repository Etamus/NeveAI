<script>
	import { getContext } from 'svelte';
	const i18n = getContext('i18n');
	import WebSearchResults from '../WebSearchResults.svelte';
	import ImageIcon from '$lib/components/icons/Image.svelte';
	import ChevronDown from '$lib/components/icons/ChevronDown.svelte';
	import Search from '$lib/components/icons/Search.svelte';
	import MusicNote from '$lib/components/icons/MusicNote.svelte';
	import Video from '$lib/components/icons/Video.svelte';
	import { getWebSearchDisplayQueries } from '$lib/utils/webSearchDisplayQueries';

	export let status = null;
	export let done = false;
	export let expanded = null;

	$: statusAction = String(status?.action ?? '').toLowerCase();
	$: statusLabel =
		status?.description === 'Imagem gerada'
			? $i18n.t('Imagem criada')
			: status?.description === 'Video criado'
				? $i18n.t('Vídeo criado')
				: status?.description
					? $i18n.t(status.description)
					: '';
	$: isDeepSearchStatus = Boolean(status?.deep_search) || statusAction.includes('deep_search');
	$: searchDisplayQueries = getWebSearchDisplayQueries(status?.queries, isDeepSearchStatus);
	$: searchedCount =
		status?.searched_count ??
		(status?.items?.length ? status.items.length : (status?.urls || []).length);
	$: isImageStatus = statusAction.includes('stable_diffusion') || statusAction.includes('image_generation');
	$: isMusicStatus = statusAction.includes('music_generation');
	$: isVideoStatus = statusAction.includes('video_generation');
</script>

{#if !status?.hidden}
	<div class="status-description flex min-w-0 w-full items-center gap-2 text-left text-sm font-normal text-gray-600 dark:text-gray-300">
		{#if status?.action === 'web_search' && (status?.urls || status?.items)}
			<WebSearchResults {status} done={done || status?.done}>
				<span class="text-sm">
					{#if status?.description?.includes('{{count}}')}
						{$i18n.t(status?.description, {
							count: searchedCount
						})}
					{:else if status?.description === 'No search query generated'}
						{$i18n.t('No search query generated')}
					{:else if status?.description === 'Generating search query'}
						{$i18n.t('Generating search query')}
					{:else}
						{statusLabel}
					{/if}
				</span>
			</WebSearchResults>
		{:else if status?.action === 'web_search'}
			<div
				class="mb-2 w-full min-w-0 overflow-hidden text-sm"
			>
				<div class="flex items-center gap-2 pt-1 pb-2">
					<div
						class="flex min-w-0 items-center gap-2 text-sm font-normal text-gray-600 transition-colors dark:text-gray-300"
					>
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
							{statusLabel}
							{/if}
						</span>
						{#if expanded !== null}
							<ChevronDown strokeWidth="2.4" className="size-3.5 shrink-0 translate-y-px text-gray-400 transition-transform duration-200 dark:text-gray-500 {expanded ? 'rotate-180' : 'rotate-0'}" />
						{/if}
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
					<span class="min-w-0">{$i18n.t(`Searching Knowledge for "{{searchQuery}}"`, {
						searchQuery: status.query
					})}</span>
					{#if expanded !== null}
						<ChevronDown strokeWidth="2.4" className="size-3.5 shrink-0 text-gray-400 dark:text-gray-500 {expanded ? 'rotate-180' : 'rotate-0'}" />
					{/if}
				</div>
			</div>
		{:else if status?.action === 'web_search_queries_generated' && status?.queries}
			<div
				class="mb-2 w-full min-w-0 overflow-hidden text-sm"
			>
				<div class="flex items-center gap-2 pt-1 pb-2">
					<div
						class="flex min-w-0 items-center gap-2 text-sm font-normal text-gray-600 transition-colors dark:text-gray-300"
					>
						<span
							class="relative min-w-0 truncate text-sm leading-5 {(done || status?.done) === false
								? 'shimmer'
								: ''}">{$i18n.t(`Searching`)}</span
						>
						{#if expanded !== null}
							<ChevronDown strokeWidth="2.4" className="size-3.5 shrink-0 translate-y-px text-gray-400 transition-transform duration-200 dark:text-gray-500 {expanded ? 'rotate-180' : 'rotate-0'}" />
						{/if}
					</div>
				</div>

				<div class="ml-[7px] flex flex-wrap gap-1.5 border-l border-[#dedede] dark:border-[#292929] px-4 pb-2.5 pt-1">
					{#each searchDisplayQueries as query (query)}
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
				class="mb-2 w-full min-w-0 overflow-hidden text-sm"
			>
				<div class="flex items-center gap-2 pt-1 pb-2">
					<div
						class="flex min-w-0 items-center gap-2 text-sm font-normal text-gray-600 transition-colors dark:text-gray-300"
					>
						<span
							class="relative min-w-0 truncate text-sm leading-5 {(done || status?.done) === false
								? 'shimmer'
								: ''}">{$i18n.t(`Querying`)}</span
						>
						{#if expanded !== null}
							<ChevronDown strokeWidth="2.4" className="size-3.5 shrink-0 translate-y-px text-gray-400 transition-transform duration-200 dark:text-gray-500 {expanded ? 'rotate-180' : 'rotate-0'}" />
						{/if}
					</div>
				</div>

				<div class="ml-[7px] flex flex-wrap gap-1.5 border-l border-[#dedede] dark:border-[#292929] px-4 pb-2.5 pt-1">
					{#each searchDisplayQueries as query (query)}
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
			<div
				class="mb-2 w-full min-w-0 overflow-hidden text-sm"
			>
				<div class="flex items-center gap-2 pt-1 pb-2">
					<div
						class="flex min-w-0 items-center gap-2 text-sm font-normal text-gray-600 transition-colors dark:text-gray-300"
					>
						<span
							class="relative min-w-0 truncate text-sm leading-5 {(done || status?.done) === false
								? 'shimmer'
								: ''}"
						>
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
						{#if expanded !== null}
							<ChevronDown strokeWidth="2.4" className="size-3.5 shrink-0 translate-y-px text-gray-400 transition-transform duration-200 dark:text-gray-500 {expanded ? 'rotate-180' : 'rotate-0'}" />
						{/if}
					</div>
				</div>
			</div>
		{:else}
			<div
				class="mb-2 w-full min-w-0 overflow-hidden text-sm"
			>
				<div class="flex items-center gap-2 pt-1 pb-2">
					<div
						class="flex min-w-0 items-center gap-2 text-sm font-normal text-gray-600 transition-colors dark:text-gray-300"
					>
						{#if isVideoStatus || isMusicStatus || isImageStatus}
						<span
							class="flex size-5 shrink-0 items-center justify-center text-gray-500 dark:text-gray-300"
						>
							{#if isVideoStatus}
								<Video className="size-3.5" strokeWidth="1.6" />
							{:else if isMusicStatus}
								<MusicNote className="size-3.5" strokeWidth="1.6" />
							{:else if isImageStatus}
								<ImageIcon className="size-3.5" strokeWidth="1.6" />
							{/if}
						</span>
						{/if}
						<span
							class="relative min-w-0 truncate text-sm leading-5 {(done || status?.done) === false
								? 'shimmer'
								: ''}"
						>
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
							{statusLabel}
							{/if}
						</span>
						{#if expanded !== null}
							<ChevronDown strokeWidth="2.4" className="size-3.5 shrink-0 translate-y-px text-gray-400 transition-transform duration-200 dark:text-gray-500 {expanded ? 'rotate-180' : 'rotate-0'}" />
						{/if}
					</div>
				</div>
			</div>
		{/if}
	</div>
{/if}
