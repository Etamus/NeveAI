<script lang="ts">
	import { getContext } from 'svelte';
	import Checkbox from '$lib/components/common/Checkbox.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import { marked } from 'marked';

	const i18n = getContext('i18n');

	const featureLabels = {
		web_search: {
			label: $i18n.t('Web Search'),
			description: $i18n.t('Model can search the web for information')
		},
		image_generation: {
			label: $i18n.t('Image Generation'),
			description: $i18n.t('Model can generate images based on text prompts')
		},
		code_interpreter: {
			label: $i18n.t('Code Interpreter'),
			description: $i18n.t('Model can execute code and perform calculations')
		},
		code_execution: {
			label: $i18n.t('Code Execution'),
			description: $i18n.t('Enable the Run button in code blocks for this model')
		},
		toggle_reasoning: {
			label: $i18n.t('Toggle Reasoning'),
			description: $i18n.t('Show the Rápido/Raciocínio toggle in the message input bar')
		},
		stable_diffusion: {
			label: $i18n.t('Geração de imagem'),
			description: $i18n.t('Modelo pode gerar imagens usando Stable Diffusion local')
		}
	};

	export let availableFeatures = ['web_search', 'image_generation', 'code_interpreter', 'code_execution', 'stable_diffusion'];
	export let featureIds = [];
	export let tooltipsEnabled = true;
</script>

<div>
	<div class="flex flex-col mt-2 gap-2">
		{#each availableFeatures as feature}
			<div class=" flex items-center gap-2">
				<Checkbox
					state={featureIds.includes(feature) ? 'checked' : 'unchecked'}
					on:change={(e) => {
						if (e.detail === 'checked') {
							featureIds = [...featureIds, feature];
						} else {
							featureIds = featureIds.filter((id) => id !== feature);
						}
					}}
				/>

				<div class=" py-0.5 text-sm">
					<Tooltip content={tooltipsEnabled ? marked.parse(featureLabels[feature].description) : ''}>
						{$i18n.t(featureLabels[feature].label)}
					</Tooltip>
				</div>
			</div>
		{/each}
	</div>
</div>
