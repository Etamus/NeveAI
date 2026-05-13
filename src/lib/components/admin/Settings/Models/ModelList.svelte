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

	const positionChangeHandler = async (event: any) => {
		const oldIndex = event.oldIndex ?? -1;
		const newIndex = event.newIndex ?? -1;
		if (oldIndex === newIndex) return;
		if (oldIndex < 0 || newIndex < 0) return;
		if (oldIndex >= modelIds.length || newIndex >= modelIds.length) return;

		const newOrder = [...modelIds];
		const movedModelId = event.item?.getAttribute('data-model-id') ?? modelIds[oldIndex];
		const currentIndex = newOrder.indexOf(movedModelId);
		if (currentIndex === -1) return;

		newOrder.splice(currentIndex, 1);
		newOrder.splice(newIndex, 0, movedModelId);

		// Sortable mutates DOM directly. Restore the DOM order Svelte still expects,
		// then let Svelte render the new order from state to avoid visual drift.
		sortable?.sort(modelIds, false);
		await tick();

		modelIds = newOrder;
		await tick();
		sortable?.sort(modelIds, false);
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
				dataIdAttr: 'data-model-id',
				handle: '.model-item-handle',
				forceFallback: true,
				fallbackOnBody: true,
				onEnd: (event) => {
					positionChangeHandler(event);
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
