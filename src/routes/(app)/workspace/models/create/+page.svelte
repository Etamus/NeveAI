<script lang="ts">
	import { toast } from 'svelte-sonner';
	import { goto } from '$app/navigation';
	import { config, models, settings, showSettings, showSettingsTab } from '$lib/stores';
	import { NEVEAI_BASE_URL } from '$lib/constants';

	import { onMount, tick, getContext } from 'svelte';
	import { createNewModel, getModelById } from '$lib/apis/models';
	import { getModels } from '$lib/apis';

	import ModelEditor from '$lib/components/workspace/Models/ModelEditor.svelte';

	const i18n = getContext('i18n');

	const onSubmit = async (modelInfo) => {
		if ($models.find((m) => m.id === modelInfo.id)) {
			toast.error(
				$i18n.t(
					"Error: A model with the ID '{{modelId}}' already exists. Please select a different ID to proceed.",
					{ modelId: modelInfo.id }
				)
			);
			return;
		}

		if (modelInfo.id === '') {
			toast.error($i18n.t('Error: Model ID cannot be empty. Please enter a valid ID to proceed.'));
			return;
		}

		if (modelInfo) {
			const res = await createNewModel(localStorage.token, {
				...modelInfo,
				meta: {
					...modelInfo.meta,
					profile_image_url:
						modelInfo.meta.profile_image_url ?? `${NEVEAI_BASE_URL}/static/favicon.png`,
					suggestion_prompts: modelInfo.meta.suggestion_prompts
						? modelInfo.meta.suggestion_prompts.filter((prompt) => prompt.content !== '')
						: null
				},
				params: { ...modelInfo.params }
			}).catch((error) => {
				toast.error(`${error}`);
				return null;
			});

			if (res) {
				toast.success($i18n.t('Model created successfully!'));
				showSettingsTab.set('admin-models');
				showSettings.set(true);
				await goto('/');
			}
		}
	};

	let model = null;

	onMount(() => {
		const handleMessageEvent = async (event: MessageEvent) => {
			if (
				!['https://github.com/Etamus/NeveAI', 'https://github.com/Etamus', 'http://localhost:9999'].includes(
					event.origin
				)
			) {
				return;
			}

			try {
				let data = JSON.parse(event.data);

				if (data?.info) {
					data = data.info;
				}

				model = data;
			} catch (e) {
				console.error('Failed to parse message data:', e);
			}
		};
		window.addEventListener('message', handleMessageEvent);

		if (window.opener ?? false) {
			window.opener.postMessage('loaded', '*');
		}

		if (sessionStorage.model) {
			model = JSON.parse(sessionStorage.model);
			sessionStorage.removeItem('model');
		}

		return () => {
			window.removeEventListener('message', handleMessageEvent);
		};
	});
</script>

{#key model}
	<ModelEditor {model} {onSubmit} />
{/key}
