<script lang="ts">
	import { DropdownMenu } from 'bits-ui';
	import Fuse from 'fuse.js';

	import { flyAndScale } from '$lib/utils/transitions';
	import { onMount, getContext, tick } from 'svelte';

	import { WEBUI_API_BASE_URL } from '$lib/constants';

	import {
		models,
		mobile,
		settings,
		config
	} from '$lib/stores';
	import { getModels } from '$lib/apis';

	import Pin from '$lib/components/icons/Pin.svelte';
	import PinSlash from '$lib/components/icons/PinSlash.svelte';

	import ModelItem from './ModelItem.svelte';

	const i18n = getContext('i18n');

	export let id = '';
	export let value = '';
	export let placeholder = $i18n.t('Select a model');
	export let searchEnabled = true;
	export let searchPlaceholder = $i18n.t('Search a model');

	export let items: {
		label: string;
		value: string;
		model: Model;
		// eslint-disable-next-line @typescript-eslint/no-explicit-any
		[key: string]: any;
	}[] = [];

	export let className = 'w-[19rem]';
	export let triggerClassName = 'text-base';

	export let pinModelHandler: (modelId: string) => void = () => {};
	export let onGearClick: (() => void) | null = null;

	let tagsContainerElement;

	let show = false;
	let tags = [];

	let selectedModel = '';
	$: selectedModel = items.find((item) => item.value === value) ?? '';

	let searchValue = '';

	let selectedTag = '';
	let selectedConnectionType = '';

	let selectedModelIdx = 0;

	const fuse = new Fuse(
		items.map((item) => {
			const _item = {
				...item,
				modelName: item.model?.name,
				tags: (item.model?.tags ?? []).map((tag) => tag.name).join(' '),
				desc: item.model?.info?.meta?.description
			};
			return _item;
		}),
		{
			keys: ['value', 'tags', 'modelName'],
			threshold: 0.4
		}
	);

	const updateFuse = () => {
		if (fuse) {
			fuse.setCollection(
				items.map((item) => {
					const _item = {
						...item,
						modelName: item.model?.name,
						tags: (item.model?.tags ?? []).map((tag) => tag.name).join(' '),
						desc: item.model?.info?.meta?.description
					};
					return _item;
				})
			);
		}
	};

	$: if (items) {
		updateFuse();
	}

	$: filteredItems = (
		searchValue
			? fuse
					.search(searchValue)
					.map((e) => {
						return e.item;
					})
					.filter((item) => {
						if (selectedTag === '') {
							return true;
						}

						return (item.model?.tags ?? [])
							.map((tag) => tag.name.toLowerCase())
							.includes(selectedTag.toLowerCase());
					})
					.filter((item) => {
						if (selectedConnectionType === '') {
							return true;
						} else if (selectedConnectionType === 'local') {
							return item.model?.connection_type === 'local';
						} else if (selectedConnectionType === 'external') {
							return item.model?.connection_type === 'external';
						} else if (selectedConnectionType === 'direct') {
							return item.model?.direct;
						}
					})
			: items
					.filter((item) => {
						if (selectedTag === '') {
							return true;
						}
						return (item.model?.tags ?? [])
							.map((tag) => tag.name.toLowerCase())
							.includes(selectedTag.toLowerCase());
					})
					.filter((item) => {
						if (selectedConnectionType === '') {
							return true;
						} else if (selectedConnectionType === 'local') {
							return item.model?.connection_type === 'local';
						} else if (selectedConnectionType === 'external') {
							return item.model?.connection_type === 'external';
						} else if (selectedConnectionType === 'direct') {
							return item.model?.direct;
						}
					})
	).filter((item) => !(item.model?.info?.meta?.hidden ?? false));

	$: if (
		selectedTag !== undefined ||
		selectedConnectionType !== undefined ||
		searchValue !== undefined
	) {
		resetView();
	}

	const resetView = async () => {
		await tick();

		const selectedInFiltered = filteredItems.findIndex((item) => item.value === value);

		if (selectedInFiltered >= 0) {
			// The selected model is visible in the current filter
			selectedModelIdx = selectedInFiltered;
		} else {
			// The selected model is not visible, default to first item in filtered list
			selectedModelIdx = 0;
		}

		// Set the virtual scroll position so the selected item is rendered and centered
		const targetScrollTop = Math.max(
			0,
			selectedModelIdx * ITEM_HEIGHT - LIST_VIEWPORT_HEIGHT / 2 + ITEM_HEIGHT / 2
		);
		listScrollTop = targetScrollTop;

		await tick();

		if (listContainer) {
			listContainer.scrollTop = targetScrollTop;
		}

		await tick();
		const item = document.querySelector(`[data-arrow-selected="true"]`);
		item?.scrollIntoView({ block: 'center', inline: 'nearest', behavior: 'instant' });
	};

	onMount(async () => {
		if (items) {
			tags = items
				.filter((item) => !(item.model?.info?.meta?.hidden ?? false))
				.flatMap((item) => item.model?.tags ?? [])
				.map((tag) => tag.name.toLowerCase());
			// Remove duplicates and sort
			tags = Array.from(new Set(tags)).sort((a, b) => a.localeCompare(b));
		}
	});

	const ITEM_HEIGHT = 46;
	const LIST_VIEWPORT_HEIGHT = 272;
	const OVERSCAN = 10;

	let listScrollTop = 0;
	let listContainer;

	$: visibleStart = Math.max(0, Math.floor(listScrollTop / ITEM_HEIGHT) - OVERSCAN);
	$: visibleEnd = Math.min(
		filteredItems.length,
		Math.ceil((listScrollTop + LIST_VIEWPORT_HEIGHT) / ITEM_HEIGHT) + OVERSCAN
	);
</script>

<DropdownMenu.Root
	bind:open={show}
	onOpenChange={async () => {
		searchValue = '';
		listScrollTop = 0;
		window.setTimeout(() => document.getElementById('model-search-input')?.focus(), 0);

		resetView();
	}}
	closeFocus={false}
>
	<DropdownMenu.Trigger
		class="relative w-full {($settings?.highContrastMode ?? false)
			? ''
			: 'outline-hidden focus:outline-hidden'}"
		aria-label={selectedModel
			? $i18n.t('Selected model: {{modelName}}', { modelName: selectedModel.label })
			: placeholder}
		id="model-selector-{id}-button"
	>
		<div
			class="flex w-full items-center text-left px-4 py-1.5 rounded-lg gap-2 {triggerClassName} {($settings?.highContrastMode ??
			false)
				? 'dark:placeholder-gray-100 placeholder-gray-800'
				: ''}"
			on:mouseenter={async () => {
				models.set(
					await getModels(
						localStorage.token,
						$config?.features?.enable_direct_connections && ($settings?.directConnections ?? null)
					)
				);
			}}
		>
			<span class="flex-1 truncate flex items-center gap-1.5">
				{#if selectedModel}
					<div class="relative size-5 shrink-0 group/pin">
						<img
							src={`${WEBUI_API_BASE_URL}/models/model/profile/image?id=${encodeURIComponent(selectedModel.value)}&lang=${$i18n.language}`}
							alt=""
							class="rounded-full size-5 group-hover/pin:opacity-0 transition-opacity"
							loading="lazy"
						/>
						<button
							class="absolute inset-0 size-5 rounded-full flex items-center justify-center opacity-0 group-hover/pin:opacity-100 transition-opacity text-gray-500 dark:text-gray-400"
							type="button"
							on:click|stopPropagation|preventDefault={() => pinModelHandler(selectedModel.value)}
							title={($settings?.pinnedModels ?? []).includes(selectedModel.value) ? 'Desfixar' : 'Fixar'}
						>
							{#if ($settings?.pinnedModels ?? []).includes(selectedModel.value)}
								<PinSlash className="size-3.5" />
							{:else}
								<Pin className="size-3.5" />
							{/if}
						</button>
					</div>
					{selectedModel.label}
				{:else}
					{placeholder}
				{/if}
			</span>
			{#if selectedModel && onGearClick}
				<button
					class="relative z-20 -mr-2 shrink-0 self-center p-0.5 rounded-md hover:bg-black/5 dark:hover:bg-white/5 transition text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300"
					type="button"
					aria-label="Controles"
					on:pointerdown|stopPropagation|preventDefault
					on:click|stopPropagation|preventDefault={() => { show = false; onGearClick(); }}
				>
					<svg
						xmlns="http://www.w3.org/2000/svg"
						viewBox="0 0 24 24"
						fill="none"
						stroke="currentColor"
						stroke-width="1.5"
						class="size-4"
					>
						<path stroke-linecap="round" stroke-linejoin="round" d="M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.325.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 0 1 1.37.49l1.296 2.247a1.125 1.125 0 0 1-.26 1.431l-1.003.827c-.293.241-.438.613-.43.992a7.723 7.723 0 0 1 0 .255c-.008.378.137.75.43.991l1.004.827c.424.35.534.955.26 1.43l-1.298 2.247a1.125 1.125 0 0 1-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.47 6.47 0 0 1-.22.128c-.331.183-.581.495-.644.869l-.213 1.281c-.09.543-.56.94-1.11.94h-2.594c-.55 0-1.019-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 0 1-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 0 1-1.369-.49l-1.297-2.247a1.125 1.125 0 0 1 .26-1.43l1.004-.827c.292-.24.437-.613.43-.991a6.932 6.932 0 0 1 0-.255c.007-.38-.138-.751-.43-.992l-1.004-.827a1.125 1.125 0 0 1-.26-1.43l1.297-2.247a1.125 1.125 0 0 1 1.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.086.22-.128.332-.183.582-.495.644-.869l.214-1.28Z" />
						<path stroke-linecap="round" stroke-linejoin="round" d="M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z" />
					</svg>
				</button>
			{:else if selectedModel}
				<svg
					xmlns="http://www.w3.org/2000/svg"
					viewBox="0 0 24 24"
					fill="none"
					stroke="currentColor"
					stroke-width="2"
					class="size-4 shrink-0 self-center text-gray-400 dark:text-gray-500"
					aria-hidden="true"
				>
					<path stroke-linecap="round" stroke-linejoin="round" d="M19 9l-7 7-7-7" />
				</svg>
			{/if}
		</div>
	</DropdownMenu.Trigger>

	<DropdownMenu.Content
		class="z-40 {$mobile
			? `w-full`
			: `${className}`} max-w-[calc(100vw-1rem)] justify-start rounded-lg backdrop-blur-2xl bg-white/95 dark:bg-gray-850/95 dark:text-white border border-gray-200/50 dark:border-gray-700/50 shadow-xl outline-hidden"
		transition={flyAndScale}
		side={$mobile ? 'bottom' : 'bottom-start'}
		sideOffset={6}
		alignOffset={-1}
	>
		<slot>
			{#if searchEnabled}
				<div class="relative px-3 py-2 border-b border-gray-100 dark:border-gray-700/60">
					<input
						id="model-search-input"
						bind:value={searchValue}
						class="w-full text-sm bg-transparent outline-hidden placeholder-gray-400 dark:placeholder-gray-500"
						placeholder={searchPlaceholder}
						autocomplete="off"
						aria-label={$i18n.t('Search In Models')}
						on:keydown={(e) => {
							if (e.code === 'Enter' && filteredItems.length > 0) {
								value = filteredItems[selectedModelIdx].value;
								show = false;
								return; // dont need to scroll on selection
							} else if (e.code === 'ArrowDown') {
								e.stopPropagation();
								selectedModelIdx = Math.min(selectedModelIdx + 1, filteredItems.length - 1);
							} else if (e.code === 'ArrowUp') {
								e.stopPropagation();
								selectedModelIdx = Math.max(selectedModelIdx - 1, 0);
							} else {
								// if the user types something, reset to the top selection.
								selectedModelIdx = 0;
							}

							const item = document.querySelector(`[data-arrow-selected="true"]`);
							item?.scrollIntoView({ block: 'center', inline: 'nearest', behavior: 'instant' });
						}}
					/>
				</div>
			{/if}

			<div class="px-1.5 group relative py-1">
				{#if filteredItems.length === 0}
					{#if items.length === 0}
						<div class="flex flex-col items-start justify-center py-6 px-4 text-start">
							<div class="text-sm font-medium text-gray-900 dark:text-gray-100 mb-1">
								{$i18n.t('No models available')}
							</div>
							<div class="text-xs text-gray-500 dark:text-gray-400">
								{$i18n.t('Load a model to start chatting')}
							</div>
						</div>
					{:else}
						<div class="">
							<div class="block px-3 py-2 text-sm text-gray-700 dark:text-gray-100">
								{$i18n.t('No results found')}
							</div>
						</div>
					{/if}
				{:else}
					<!-- svelte-ignore a11y-no-static-element-interactions -->
					<div
						class="max-h-[17rem] overflow-y-auto pr-2"
						role="listbox"
						aria-label={$i18n.t('Available models')}
						bind:this={listContainer}
						on:scroll={() => {
							listScrollTop = listContainer.scrollTop;
						}}
					>
						<div style="height: {visibleStart * ITEM_HEIGHT}px;" />
						{#each filteredItems.slice(visibleStart, visibleEnd) as item, i (item.value)}
							{@const index = visibleStart + i}
							<ModelItem
								{selectedModelIdx}
								{item}
								{index}
								{value}
								{pinModelHandler}
								onClick={() => {
									value = item.value;
									selectedModelIdx = index;

									show = false;
								}}
							/>
						{/each}
						<div style="height: {(filteredItems.length - visibleEnd) * ITEM_HEIGHT}px;" />
					</div>
				{/if}
			</div>

			<div class="mb-1"></div>

			<div class="hidden w-[38rem]" />
			<div class="hidden w-[19rem]" />
		</slot>
	</DropdownMenu.Content>
</DropdownMenu.Root>
