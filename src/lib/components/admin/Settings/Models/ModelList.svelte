<script lang="ts">
	import Sortable from 'sortablejs';

	import { createEventDispatcher, getContext, onDestroy, onMount, tick } from 'svelte';
	const i18n = getContext('i18n');
	const dispatch = createEventDispatcher();

	import { models } from '$lib/stores';
	import EllipsisVertical from '$lib/components/icons/EllipsisVertical.svelte';

	export let modelIds = [];

	let sortable = null;
	let modelListElement = null;

	$: modelNameById = new Map($models.map((model) => [model.id, model.name]));

	const positionChangeHandler = () => {
		if (!modelListElement) return;

		// Read new order from DOM
		const newOrder = Array.from(modelListElement.children).map((child) =>
			child.getAttribute('data-model-id')
		).filter(Boolean);

		if (newOrder.length !== modelIds.length) return;
		if (newOrder.every((id, idx) => id === modelIds[idx])) return;

		modelIds = newOrder;
		dispatch('reorder', modelIds);
	};

	const initSortable = () => {
		if (sortable) {
			sortable.destroy();
			sortable = null;
		}

		if (modelListElement) {
			sortable = new Sortable(modelListElement, {
				animation: 150,
				handle: '.model-item-handle',
				forceFallback: true,
				fallbackOnBody: true,
				onEnd: () => {
					setTimeout(positionChangeHandler, 0);
				}
			});
		}
	};

	onMount(() => {
		// Wait a tick for the {#if} block to render and bind modelListElement
		tick().then(() => {
			initSortable();
		});
	});

	onDestroy(() => {
		if (sortable) {
			sortable.destroy();
		}
	});
</script>

{#if modelIds.length > 0}
	<div class="flex flex-col -translate-x-1" bind:this={modelListElement}>
		{#each modelIds as modelId (modelId)}
			<div class="flex gap-2 w-full justify-between items-center" data-model-id={modelId}>
				<div class="flex items-center gap-1 min-w-0">
					<EllipsisVertical className="size-4 cursor-move model-item-handle shrink-0" />

					<div class="text-sm flex-1 py-1 rounded-lg line-clamp-1 min-w-0">
						{modelNameById.get(modelId) ?? modelId}
					</div>
				</div>
			</div>
		{/each}
	</div>
{:else}
	<div class="text-gray-500 text-xs text-center py-2">
		{$i18n.t('No models found')}
	</div>
{/if}
