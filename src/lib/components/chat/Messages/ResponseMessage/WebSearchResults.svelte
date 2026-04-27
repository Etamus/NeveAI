<script lang="ts">
	import { getContext, onMount } from 'svelte';
	const i18n = getContext('i18n');

	import ChevronDown from '$lib/components/icons/ChevronDown.svelte';
	import GlobeAlt from '$lib/components/icons/GlobeAlt.svelte';

	import { slide } from 'svelte/transition';
	import { quintOut } from 'svelte/easing';

	export let status: any = { urls: [], query: '' };
	export let done: boolean = false;

	let open = false;
	let expanded = false;
	let maxVisible = 8;

	// Extract domain from URL
	function extractDomain(url: string): string {
		try {
			return new URL(url).hostname.replace(/^www\./, '');
		} catch {
			return url;
		}
	}

	// Get items list (items take priority over urls)
	$: items = status?.items
		? status.items.map((item: any) => ({
				url: item.link,
				title: item.title || extractDomain(item.link)
			}))
		: status?.urls
			? status.urls.map((url: string) => ({
					url,
					title: extractDomain(url)
				}))
			: [];

	$: isSearching = !done && !status?.done;

	// Auto-open while searching, auto-close when done
	$: if (isSearching && items.length > 0) {
		open = true;
	}

	$: visibleItems = expanded ? items : items.slice(0, maxVisible);
	$: hiddenCount = items.length - maxVisible;
</script>

<!-- svelte-ignore a11y-no-static-element-interactions -->
<!-- svelte-ignore a11y-click-events-have-key-events -->
<div
	class="web-search-block -ml-3 mb-2 w-[calc(100%+0.75rem)] overflow-hidden rounded-xl text-sm transition-all duration-200 {open && items.length > 0
		? 'border border-gray-200/80 bg-gray-50/70 shadow-[0_1px_2px_rgba(15,23,42,0.04)] dark:border-white/10 dark:bg-white/[0.035] dark:shadow-none'
		: ''}"
>
	<!-- Trigger -->
	<div
		class="flex items-center justify-between gap-3 px-3 py-2 cursor-pointer group/ws-trigger"
		on:pointerup|stopPropagation={() => {
			open = !open;
		}}
		on:click|stopPropagation
	>
		<div
			class="flex min-w-0 flex-1 items-center gap-2 text-sm font-medium text-gray-600 transition-colors hover:text-gray-800 dark:text-gray-300 dark:hover:text-gray-100"
		>
			<span
				class="flex size-5 shrink-0 items-center justify-center rounded-full bg-white text-gray-500 ring-1 ring-gray-200 dark:bg-white/5 dark:text-gray-300 dark:ring-white/10"
			>
				<GlobeAlt className="size-3.5" strokeWidth="1.6" />
			</span>

			<span class="relative min-w-0 truncate text-sm leading-5">
				{#if isSearching}
					<span class="shimmer text-sm leading-5">
						{#if status?.query}
							{$i18n.t('Searching for "{{query}}"', { query: status.query })}
						{:else}
							{$i18n.t('Searching the web...')}
						{/if}
					</span>
				{:else}
					<slot />
				{/if}
			</span>

			<ChevronDown
				strokeWidth="2.5"
				className="size-3.5 shrink-0 translate-y-px text-gray-400 transition-transform duration-200 dark:text-gray-500 {open
					? 'rotate-0'
					: '-rotate-90'}"
			/>
		</div>
	</div>

	<!-- Results content -->
	{#if open && items.length > 0}
		<div
			class="border-t border-gray-200/70 bg-white/55 px-3 py-2.5 dark:border-white/10 dark:bg-black/10"
			transition:slide={{ duration: 200, easing: quintOut, axis: 'y' }}
		>
			<div class="flex flex-wrap gap-1.5">
				{#each visibleItems as item}
					<a
						href={item.url}
						target="_blank"
						rel="noopener noreferrer"
						class="inline-flex items-center gap-1.5 rounded-md border border-gray-200 dark:border-gray-700/60 bg-white dark:bg-gray-900 px-2 py-1 text-xs text-gray-700 dark:text-gray-300 no-underline! font-normal! transition-colors hover:bg-gray-50 dark:hover:bg-gray-800 hover:border-gray-300 dark:hover:border-gray-600"
						title={item.url}
					>
						<img
							src="https://www.google.com/s2/favicons?sz=32&domain={item.url}"
							alt=""
							class="size-3 shrink-0 rounded-sm"
							on:error={(e) => {
								e.currentTarget.style.display = 'none';
							}}
						/>
						<span class="max-w-[150px] truncate">{item.title}</span>
					</a>
				{/each}

				{#if !expanded && hiddenCount > 0}
					<button
						class="inline-flex items-center rounded-md border border-gray-200 dark:border-gray-700/60 px-2 py-1 text-xs text-gray-500 dark:text-gray-400 transition-colors hover:text-gray-700 dark:hover:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800 cursor-pointer"
						on:pointerup|stopPropagation={() => {
							expanded = true;
						}}
					>
						+{hiddenCount} mais
					</button>
				{/if}

				{#if expanded && hiddenCount > 0}
					<button
						class="inline-flex items-center rounded-md border border-gray-200 dark:border-gray-700/60 px-2 py-1 text-xs text-gray-500 dark:text-gray-400 transition-colors hover:text-gray-700 dark:hover:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800 cursor-pointer"
						on:pointerup|stopPropagation={() => {
							expanded = false;
						}}
					>
						Mostrar menos
					</button>
				{/if}
			</div>
		</div>
	{/if}
</div>
