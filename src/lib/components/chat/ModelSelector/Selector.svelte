<script lang="ts">
	import { DropdownMenu } from 'bits-ui';
	import { marked } from 'marked';
	import Fuse from 'fuse.js';
	import Sortable from 'sortablejs';

	import dayjs from '$lib/dayjs';
	import relativeTime from 'dayjs/plugin/relativeTime';
	dayjs.extend(relativeTime);

	import Spinner from '$lib/components/common/Spinner.svelte';
	import { fly } from 'svelte/transition';
	import { cubicOut } from 'svelte/easing';
	import { createEventDispatcher, onDestroy, getContext, tick } from 'svelte';

	import { NEVEAI_API_BASE_URL } from '$lib/constants';

	import { user, models, mobile, settings, config } from '$lib/stores';
	import type { Model } from '$lib/stores';
	import { toast } from 'svelte-sonner';
	import { getModels } from '$lib/apis';
	import { getModelsConfig, setModelsConfig } from '$lib/apis/configs';

	import ChevronDown from '$lib/components/icons/ChevronDownCompact.svelte';
	import SettingsIcon from '$lib/components/icons/Settings.svelte';
	import LocalModelLoadSettings from './LocalModelLoadSettings.svelte';
	import Search from '$lib/components/icons/Search.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import Switch from '$lib/components/common/Switch.svelte';
	import ChatBubbleOval from '$lib/components/icons/ChatBubbleOval.svelte';
	import Home2 from '$lib/components/icons/Home2.svelte';
	import Bookmark from '$lib/components/icons/Bookmark.svelte';

	import ModelItem from './ModelItem.svelte';

	import type { I18nStore } from '$lib/i18n';
	const i18n = getContext<I18nStore>('i18n');
	const dispatch = createEventDispatcher();
	const modelMenuTransition = (node: Element) => fly(node, { y: -8, duration: 200, easing: cubicOut });
	let modelChevronSize = 12;
	const alignModelChevron = (node: HTMLElement, _label: string) => {
		let correction = 0;
		let frame = 0;
		let alive = true;
		const align = () => {
			if (!alive) return;
			const icon = node.querySelector<SVGElement>('svg');
			const size = Math.max(2, Math.round(parseFloat(getComputedStyle(document.documentElement).fontSize) * 0.75 / 2) * 2);
			modelChevronSize = size;
			if (icon) { icon.style.width = `${size}px`; icon.style.height = `${size}px`; }
			const left = node.getBoundingClientRect().left - correction;
			correction = Math.round(left) - left;
			node.style.translate = `${correction}px 0`;
		};
		const schedule = () => {
			if (!alive) return;
			cancelAnimationFrame(frame);
			frame = requestAnimationFrame(align);
			for (const animation of node.closest('[data-sidebar-pane]')?.getAnimations() ?? []) {
				void animation.finished.then(align, () => {});
			}
		};
		const observer = new ResizeObserver(schedule);
		observer.observe(node.parentElement ?? node);
		window.addEventListener('resize', schedule);
		void document.fonts.ready.then(schedule);
		schedule();
		return {
			update: schedule,
			destroy() { alive = false; cancelAnimationFrame(frame); observer.disconnect(); window.removeEventListener('resize', schedule); }
		};
	};

	export let id = '';
	export let value = '';
	export let placeholder = $i18n.t('Select a model');
	export let searchEnabled = true;
	export let searchPlaceholder = $i18n.t('Search...');

	export let items: {
		label: string;
		value: string;
		model: Model;
		// eslint-disable-next-line @typescript-eslint/no-explicit-any
		[key: string]: any;
	}[] = [];

	export let className = 'w-[20rem]';
	export let triggerClassName = 'text-base';

	export let favoriteModelHandler: (modelId: string) => void = () => {};

	let tagsContainerElement;

	let show = false;
	let showLoadSettings = false;
	$: if (!show) showLoadSettings = false;
	let tags = [];

	let selectedModel: (typeof items)[number] | '' = '';
	$: selectedModel = items.find((item) => item.value === value) ?? '';

	const getModelImageVersion = (model: any) =>
		model?.updated_at ?? model?.info?.updated_at ?? model?.meta?.updated_at ?? '';
	const getModelProfileImageUrl = (model: any, lang = '') => {
		const params = new URLSearchParams({ id: model?.id ?? '' });
		if (lang) params.set('lang', lang);
		const version = getModelImageVersion(model);
		if (version) params.set('v', `${version}`);
		return `${NEVEAI_API_BASE_URL}/models/model/profile/image?${params.toString()}`;
	};

	const MAX_MODEL_IMAGE_PRELOAD = 120;
	const preloadedModelImageUrls = new Set<string>();
	let modelProfileImageUrls = new Map<string, string>();

	const preloadModelProfileImages = (sourceItems: any[] = [], lang = '') => {
		if (typeof Image === 'undefined') return;

		const selectedFirstItems = [
			...sourceItems.filter((item) => item.value === value),
			...sourceItems.filter((item) => item.value !== value)
		];
		const urls = [
			...new Set(
				selectedFirstItems
					.filter((item) => item?.model?.id)
					.map((item) => getModelProfileImageUrl(item.model, lang))
			)
		].slice(0, MAX_MODEL_IMAGE_PRELOAD);

		for (const url of urls) {
			if (preloadedModelImageUrls.has(url)) continue;
			preloadedModelImageUrls.add(url);

			const image = new Image();
			image.decoding = 'async';
			image.src = url;
		}
	};

	let searchValue = '';

	let selectedTag = '';
	let modelFilter: 'all' | 'favorites' = 'all';
	$: hasFavorites = items.some((item) => ($settings?.favoriteModels ?? []).includes(item.value));
	$: if (!hasFavorites) modelFilter = 'all';
	$: modelFilters = [
		{ id: 'all', label: 'All models', icon: Home2 },
		{ id: 'favorites', label: 'Favorites', icon: Bookmark }
	] as const;

	let selectedModelIdx = 0;
	let keyboardNavigation = false;

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
			keys: ['label', 'value', 'tags', 'modelName'],
			threshold: 0.28,
			ignoreLocation: true,
			includeScore: true
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

	const normalizeSearchText = (value: any = '') =>
		`${value}`
			.normalize('NFD')
			.replace(/[\u0300-\u036f]/g, '')
			.toLowerCase();

	const getItemSearchText = (item: any) =>
		normalizeSearchText(
			[
				item?.label,
				item?.value,
				item?.model?.id,
				item?.model?.name,
				(item?.model?.tags ?? []).map((tag) => tag.name).join(' ')
			]
				.filter(Boolean)
				.join(' ')
		);

	const isDirectSearchMatch = (item: any, query: string) => {
		const terms = normalizeSearchText(query).split(/\s+/).filter(Boolean);
		if (terms.length === 0) return true;

		const text = getItemSearchText(item);
		return terms.every((term) => text.includes(term));
	};

	const getSearchedItems = (query: string) => {
		const trimmedQuery = query.trim();
		if (!trimmedQuery) return items;

		const directMatches = items.filter((item) => isDirectSearchMatch(item, trimmedQuery));
		if (directMatches.length > 0) return directMatches;

		return fuse
			.search(trimmedQuery)
			.filter((result) => (result.score ?? 1) <= 0.25)
			.map((result) => result.item);
	};

	const passesModelFilters = (item: any, filter: typeof modelFilter, favorites: string[]) => {
		if (filter === 'favorites' && !favorites.includes(item.value)) return false;
		if (
			selectedTag !== '' &&
			!(item.model?.tags ?? [])
				.map((tag) => tag.name.toLowerCase())
				.includes(selectedTag.toLowerCase())
		) {
			return false;
		}

		return true;
	};

	$: if (items) {
		updateFuse();
	}

	$: if (items || $i18n.language) {
		modelProfileImageUrls = new Map(
			items
				.filter((item) => item?.model?.id)
				.map((item) => [item.value, getModelProfileImageUrl(item.model, $i18n.language)])
		);
		preloadModelProfileImages(items, $i18n.language);
	}

	$: filteredItems = (searchValue ? getSearchedItems(searchValue) : items)
		.filter((item) => passesModelFilters(item, modelFilter, $settings?.favoriteModels ?? []))
		.filter((item) => !(item.model?.info?.meta?.hidden ?? false));

	$: if (show && filteredItems) {
		preloadModelProfileImages(filteredItems, $i18n.language);
	}

	$: if (
		selectedTag !== undefined ||
		modelFilter !== undefined ||
		$settings?.favoriteModels !== undefined ||
		searchValue !== undefined
	) {
		resetView();
	}

	const resetView = async () => {
		await tick();
		const selectedIndex = filteredItems.findIndex((item) => item.value === value);
		selectedModelIdx = Math.max(0, selectedIndex);
		keyboardNavigation = false;
		if (listContainer) listContainer.scrollTop = 0;
	};

	const fitLoadSettings = (node: HTMLElement) => {
		let frame = 0;
		const update = () => {
			frame = 0;
			const viewport = window.visualViewport;
			const bottom = viewport ? viewport.offsetTop + viewport.height : window.innerHeight;
			const limit = 14.75 * parseFloat(getComputedStyle(document.documentElement).fontSize);
			const height = Math.max(34, Math.min(limit, bottom - node.getBoundingClientRect().top - 16));
			node.style.maxHeight = `${height}px`;
		};
		const schedule = () => {
			cancelAnimationFrame(frame);
			frame = requestAnimationFrame(update);
		};
		const observer = new ResizeObserver(schedule);
		observer.observe(node);
		window.addEventListener('resize', schedule);
		window.visualViewport?.addEventListener('resize', schedule);
		schedule();
		return { destroy() {
			cancelAnimationFrame(frame);
			observer.disconnect();
			window.removeEventListener('resize', schedule);
			window.visualViewport?.removeEventListener('resize', schedule);
		} };
	};

	const fitModelRows = (node: HTMLElement) => {
		const update = () => {
			const row = node.querySelector<HTMLElement>('[data-model-selector-row]');
			if (!row) return;
			const rowHeight = parseFloat(getComputedStyle(row).height);
			const gap = parseFloat(getComputedStyle(node).rowGap) || 0;
			const available = parseFloat(getComputedStyle(node).getPropertyValue('--bits-dropdown-menu-content-available-height'));
			const root = node.closest('[data-model-selector-content]');
			const headerHeight = root ? node.getBoundingClientRect().top - root.getBoundingClientRect().top + 8 : node.offsetTop + 8;
			const budget = Number.isFinite(available) ? available - headerHeight : window.innerHeight - node.getBoundingClientRect().top - 8;
			const rows = Math.max(1, Math.min(4, Math.floor((budget + gap) / (rowHeight + gap))));
			node.style.maxHeight = `${rows * rowHeight + (rows - 1) * gap}px`;
		};
		const observer = new ResizeObserver(update);
		observer.observe(node);
		update();
		window.addEventListener('resize', update);
		return { destroy() { observer.disconnect(); window.removeEventListener('resize', update); } };
	};

	let listContainer;
	let sortable: Sortable | null = null;
	let sortableElement: HTMLElement | null = null;
	let sortableSignature = '';
	let sortableSyncVersion = 0;
	let sortableDomOrder: ChildNode[] = [];
	let suppressNextModelClick = false;

	$: canReorderModels =
		$user?.role === 'admin' &&
		searchValue === '' &&
		selectedTag === '' &&
		modelFilter === 'all' &&
		filteredItems.length > 1;

	const destroySortable = () => {
		if (sortable) {
			sortable.destroy();
			sortable = null;
		}
		sortableElement = null;
	};

	const getNormalizedModelOrder = (orderedIds: string[]) => {
		const allModelIds = items.map((item) => item.value);
		const orderedExistingIds = orderedIds.filter((id) => allModelIds.includes(id));
		const remainingIds = allModelIds.filter((id) => !orderedExistingIds.includes(id));

		return [...orderedExistingIds, ...remainingIds];
	};

	const applyModelOrderToStore = (orderedIds: string[]) => {
		const order = new Map(orderedIds.map((modelId, idx) => [modelId, idx]));
		const currentModels = [...$models];
		const originalOrder = new Map(currentModels.map((model, idx) => [model.id, idx]));

		models.set(
			currentModels.sort((a, b) => {
				const orderA = order.has(a.id) ? order.get(a.id) : Number.MAX_SAFE_INTEGER;
				const orderB = order.has(b.id) ? order.get(b.id) : Number.MAX_SAFE_INTEGER;
				if (orderA !== orderB) return orderA - orderB;
				return (originalOrder.get(a.id) ?? 0) - (originalOrder.get(b.id) ?? 0);
			})
		);
	};

	const saveModelOrder = async (orderedIds: string[]) => {
		try {
			const currentConfig = await getModelsConfig(localStorage.token);
			const res = await setModelsConfig(localStorage.token, {
				DEFAULT_MODELS: currentConfig?.DEFAULT_MODELS ?? null,
				DEFAULT_PINNED_MODELS: null,
				MODEL_ORDER_LIST: orderedIds,
				DEFAULT_MODEL_METADATA: currentConfig?.DEFAULT_MODEL_METADATA ?? null,
				DEFAULT_MODEL_PARAMS: currentConfig?.DEFAULT_MODEL_PARAMS ?? null
			});

			if (res) {
				config.set({ ...($config ?? {}), ...res });
			}
		} catch (error) {
			console.error(error);
			toast.error($i18n.t('Failed to save models configuration'));
			models.set(
				await getModels(
					localStorage.token,
					$config?.features?.enable_direct_connections && ($settings?.directConnections ?? null)
				)
			);
		}
	};

	const reorderModelHandler = async (event: any) => {
		if (!listContainer || event.oldIndex === event.newIndex) {
			sortableDomOrder = [];
			return;
		}

		const orderedIds = Array.from(
			listContainer.querySelectorAll('[data-model-selector-row="true"]')
		)
			.map((element: Element) => element.getAttribute('data-value'))
			.filter(Boolean) as string[];

		const normalizedOrder = getNormalizedModelOrder(orderedIds);
		// Restore Svelte's keyed-block anchors before its store-driven reorder.
		for (const node of sortableDomOrder) listContainer.appendChild(node);
		sortableDomOrder = [];
		applyModelOrderToStore(normalizedOrder);
		await tick();
		await saveModelOrder(normalizedOrder);
	};

	const syncSortable = async () => {
		const nextSignature = `${show}:${canReorderModels}:${filteredItems
			.map((item) => item.value)
			.join('|')}`;

		if (nextSignature === sortableSignature && sortable && sortableElement === listContainer) return;
		sortableSignature = nextSignature;
		const requestedVersion = ++sortableSyncVersion;
		destroySortable();

		await tick();
		if (requestedVersion !== sortableSyncVersion) return;
		if (!show || !canReorderModels || !listContainer) return;

		sortableElement = listContainer;
		sortable = new Sortable(listContainer, {
			animation: 150,
			dataIdAttr: 'data-value',
			draggable: '[data-model-selector-row="true"]',
			delay: 180,
			delayOnTouchOnly: false,
			fallbackOnBody: true,
			fallbackClass: 'model-selector-drag-fallback',
			forceFallback: true,
			fallbackTolerance: 4,
			ghostClass: 'model-selector-drag-ghost',
			chosenClass: 'model-selector-drag-chosen',
			dragClass: 'model-selector-drag-active',
			onChoose: () => {
				sortableDomOrder = Array.from(listContainer.childNodes);
			},
			onEnd: async (event) => {
				suppressNextModelClick = true;
				await reorderModelHandler(event);
				window.setTimeout(() => {
					suppressNextModelClick = false;
				}, 0);
			}
		});
	};

	$: show, canReorderModels, filteredItems, listContainer, syncSortable();

	onDestroy(() => {
		sortableSyncVersion += 1;
		destroySortable();
	});
</script>

<DropdownMenu.Root
	bind:open={show}
	onOpenChange={async (open) => {
		if (!open) return;
		searchValue = '';
		preloadModelProfileImages(items, $i18n.language);
		window.setTimeout(() => document.getElementById('model-search-input')?.focus(), 0);

		resetView();
	}}
	closeFocus={false}
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
		<DropdownMenu.Trigger
			class="relative flex min-w-0 flex-1 items-center gap-1.5 text-left {($settings?.highContrastMode ?? false)
				? ''
				: 'outline-hidden focus:outline-hidden'}"
			aria-label={selectedModel
				? $i18n.t('Selected model: {{modelName}}', { modelName: selectedModel.label })
				: placeholder}
			id="model-selector-{id}-button"
		>
			<span class="flex min-w-0 flex-1 items-center gap-1.5 truncate">
				{#if selectedModel}
					<span class="min-w-0 -translate-y-px truncate">{selectedModel.label}</span>
				{:else}
					<span class="min-w-0 -translate-y-px truncate">{placeholder}</span>
				{/if}
			</span>
			{#if selectedModel}
				<span aria-hidden="true" use:alignModelChevron={selectedModel.label} class="pointer-events-none flex shrink-0 items-center text-gray-500 dark:text-gray-400 transition-[rotate,transform] duration-200 {show ? 'rotate-180' : ''}">
					<ChevronDown className="size-3" pixelSize={modelChevronSize} />
				</span>
			{/if}
		</DropdownMenu.Trigger>
	</div>

	<DropdownMenu.Content
		data-model-selector-content="true"
		class="z-40 {$mobile
			? `w-full`
			: `${className}`} max-w-[calc(100vw-1rem)] justify-start rounded-lg backdrop-blur-2xl bg-white/95 dark:bg-gray-850/95 dark:text-white border border-gray-200/50 dark:border-gray-700/50 shadow-xl outline-hidden"
		transition={modelMenuTransition}
		side="bottom"
		align={$mobile ? 'center' : 'start'}
		sideOffset={6}
		alignOffset={$mobile ? -1 : -7}
	>
		<slot>
			<div class="flex min-w-0">
				<div class="flex min-w-0 flex-1 flex-col">
			{#if searchEnabled}
				<div class="relative flex items-center gap-3 px-3 py-2 border-b border-gray-100 dark:border-gray-700/60">
					{#if showLoadSettings}
						<span class="min-w-0 flex-1 text-sm font-semibold text-gray-700 dark:text-gray-200">{$i18n.t('Predefinições')}</span>
					{:else}
					<Search className="size-4 shrink-0 text-gray-500 dark:text-gray-400" />
					<input
						id="model-search-input"
						bind:value={searchValue}
						class="min-w-0 flex-1 text-sm bg-transparent outline-hidden placeholder-gray-400 dark:placeholder-gray-500"
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
								keyboardNavigation = true;
								selectedModelIdx = Math.min(selectedModelIdx + 1, filteredItems.length - 1);
							} else if (e.code === 'ArrowUp') {
								e.stopPropagation();
								keyboardNavigation = true;
								selectedModelIdx = Math.max(selectedModelIdx - 1, 0);
							} else {
								// if the user types something, reset to the top selection.
								selectedModelIdx = 0;
							}

							const item = document.querySelector(`[data-arrow-selected="true"]`);
							item?.scrollIntoView({ block: 'center', inline: 'nearest', behavior: 'instant' });
						}}
					/>
					{/if}
					<div class="ml-auto flex shrink-0 items-center gap-1" data-model-selector-tools>
						{#if hasFavorites && !showLoadSettings}
							{#each modelFilters as filter}
								<Tooltip content={$i18n.t(filter.label)}>
									<button type="button" aria-label={$i18n.t(filter.label)} aria-pressed={modelFilter === filter.id}
										class="flex size-7 items-center justify-center rounded-md text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 {modelFilter === filter.id ? 'bg-gray-100 dark:bg-gray-700/60 text-gray-900 dark:text-white' : ''}"
										on:click|stopPropagation={() => { modelFilter = filter.id; }}>
										<svelte:component this={filter.icon} className="size-4" />
									</button>
								</Tooltip>
							{/each}
						{/if}
							<Tooltip content={$i18n.t('Predefinições')}>
								<button type="button" aria-label={$i18n.t('Predefinições')} aria-pressed={showLoadSettings} class="flex size-7 items-center justify-center rounded-md text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800" on:click|stopPropagation={() => { showLoadSettings = !showLoadSettings; }}>
									<SettingsIcon className="size-4" />
								</button>
							</Tooltip>
					</div>
				</div>
			{/if}

			{#if showLoadSettings}
				<div data-model-load-settings use:fitLoadSettings class="max-h-[14.75rem] overflow-y-auto py-1">
					<LocalModelLoadSettings />
				</div>
			{:else}
			<div class="flex min-h-0 flex-1 flex-col px-1.5 group relative py-1">
				{#if filteredItems.length === 0}
					<div class="flex flex-1 items-center justify-center px-3 py-2 text-center text-sm text-gray-700 dark:text-gray-100" role="status">
						{$i18n.t(searchValue.trim() ? 'No models found' : modelFilter === 'favorites' ? 'No favorites yet' : 'No models available')}
					</div>
				{:else}
					<!-- svelte-ignore a11y-no-static-element-interactions -->
					<div
						class="flex flex-col gap-1 max-h-[14.75rem] overflow-y-auto pr-2"
						role="listbox"
						tabindex="-1"
						aria-label={$i18n.t('Available models')}
						bind:this={listContainer}
						use:fitModelRows
						on:mousemove={() => { keyboardNavigation = false; }}
					>
						{#each filteredItems as item, index (item.value)}
							<ModelItem
								{selectedModelIdx}
								{keyboardNavigation}
								{item}
								{index}
								{value}
								profileImageUrl={modelProfileImageUrls.get(item.value) ?? ''}
								reorderEnabled={canReorderModels}
								{favoriteModelHandler}
								onClick={() => {
									if (suppressNextModelClick) return;
									value = item.value;
									selectedModelIdx = index;

									show = false;
								}}
							/>
						{/each}
					</div>
				{/if}

			</div>

			<div class="mb-1"></div>
			{/if}
				</div>
			</div>

			<div class="hidden w-[38rem]" />
			<div class="hidden w-[21rem]" />
		</slot>
	</DropdownMenu.Content>
</DropdownMenu.Root>

<style>
	:global(.model-selector-drag-fallback) {
		opacity: 0 !important;
		pointer-events: none !important;
	}

	:global(.model-selector-drag-ghost) {
		opacity: 0.55;
	}

	:global(.model-selector-drag-chosen),
	:global(.model-selector-drag-active) {
		cursor: grabbing !important;
	}
</style>
