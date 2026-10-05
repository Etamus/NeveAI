<script lang="ts">
	import { models, settings } from '$lib/stores';
	import { getContext } from 'svelte';
	import Selector from './ModelSelector/Selector.svelte';

	import { toggleModelFavorite } from '$lib/utils/modelFavoriteActions';
	import { toast } from 'svelte-sonner';
	const i18n = getContext('i18n');

	export let selectedModels = [''];
	export let disabled = false;



	const favoriteModelHandler = (modelId: string) => toggleModelFavorite(modelId)
		.catch(() => toast.error($i18n.t('Failed to save favorites')));

	$: if (selectedModels.length > 0 && $models.length > 0) {
		const _selectedModels = selectedModels.map((model) =>
			$models.map((m) => m.id).includes(model) ? model : ''
		);

		if (JSON.stringify(_selectedModels) !== JSON.stringify(selectedModels)) {
			selectedModels = _selectedModels;
		}
	}

</script>

<div class="flex flex-col w-full items-start">
	{#each selectedModels as selectedModel, selectedModelIdx}
		<div class="flex items-center w-full max-w-fit gap-0">
			<div class="overflow-hidden flex-1 min-w-0">
				<div class="max-w-full {($settings?.highContrastMode ?? false) ? 'm-1' : 'mr-0'}">
					<Selector
						id={`${selectedModelIdx}`}
						placeholder={$i18n.t('Select a model')}
						items={$models.map((model) => ({
							value: model.id,
							label: model.name,
							model: model
						}))}
						{favoriteModelHandler}
						bind:value={selectedModel}
					/>
				</div>
			</div>
		</div>
	{/each}
</div>


