<script lang="ts">
	import { models, showSettings, settings, user, mobile, config, showModelSettings } from '$lib/stores';
	import { onMount, tick, getContext } from 'svelte';
	import { toast } from 'svelte-sonner';
	import Selector from './ModelSelector/Selector.svelte';
	import LocalModelLoadPreferences from './ModelSelector/LocalModelLoadPreferences.svelte';
	import Tooltip from '../common/Tooltip.svelte';

	import { updateUserSettings } from '$lib/apis/users';
	const i18n = getContext('i18n');

	export let selectedModels = [''];
	export let disabled = false;



	const pinModelHandler = async (modelId) => {
		let pinnedModels = $settings?.pinnedModels ?? [];

		if (pinnedModels.includes(modelId)) {
			pinnedModels = pinnedModels.filter((id) => id !== modelId);
		} else {
			pinnedModels = [...new Set([...pinnedModels, modelId])];
		}

		settings.set({ ...$settings, pinnedModels: pinnedModels });
		await updateUserSettings(localStorage.token, { ui: $settings });
	};

	$: if (selectedModels.length > 0 && $models.length > 0) {
		const _selectedModels = selectedModels.map((model) =>
			$models.map((m) => m.id).includes(model) ? model : ''
		);

		if (JSON.stringify(_selectedModels) !== JSON.stringify(selectedModels)) {
			selectedModels = _selectedModels;
		}
	}

	$: hasLocalFolderModels = $models.some(
		(model) => model?.owned_by === 'llamacpp' && model?.connection_type === 'local' && model?.llamacpp
	);
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
						{pinModelHandler}
						onGearClick={selectedModelIdx === 0 && selectedModel && !disabled ? () => showModelSettings.set(true) : null}
						bind:value={selectedModel}
					/>
				</div>
			</div>
			{#if selectedModelIdx === 0 && selectedModel && !disabled && hasLocalFolderModels}
				<div class="relative z-20 -ml-1.5 flex shrink-0">
					<LocalModelLoadPreferences />
				</div>
			{/if}
		</div>
	{/each}
</div>


