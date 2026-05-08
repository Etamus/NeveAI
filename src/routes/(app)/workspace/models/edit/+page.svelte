<script>
	import { toast } from 'svelte-sonner';
	import { goto } from '$app/navigation';

	import { onMount, getContext } from 'svelte';
	const i18n = getContext('i18n');

	import { page } from '$app/stores';
	import { config, models, settings, showSettings, showSettingsTab } from '$lib/stores';

	import { getModelById, updateModelById } from '$lib/apis/models';

	import { getModels } from '$lib/apis';
	import ModelEditor from '$lib/components/workspace/Models/ModelEditor.svelte';

	let model = null;

	onMount(async () => {
		const _id = $page.url.searchParams.get('id');
		if (_id) {
			model = await getModelById(localStorage.token, _id, { raw: true }).catch((e) => {
				return null;
			});

			if (!model) {
				goto('/workspace/models');
			}

			if (!model?.write_access) {
				toast.error($i18n.t('You do not have permission to edit this model'));
				goto('/workspace/models');
			}
		} else {
			goto('/workspace/models');
		}
	});

	const onSubmit = async (modelInfo) => {
		await updateModelById(localStorage.token, modelInfo.id, modelInfo);
		toast.success($i18n.t('Model updated successfully'));
		showSettingsTab.set('admin-models');
		showSettings.set(true);
		await goto('/');
	};
</script>

{#if model}
	<ModelEditor edit={true} {model} {onSubmit} />
{/if}
