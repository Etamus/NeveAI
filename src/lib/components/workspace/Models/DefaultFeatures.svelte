<script lang="ts">
	import { getContext } from 'svelte';
	import type { Readable } from 'svelte/store';
	import Switch from '$lib/components/common/Switch.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import { marked } from 'marked';

	type I18nStore = Readable<{ t: (key: string) => string }>;

	const i18n = getContext<I18nStore>('i18n');

	const featureLabels = {
		web_search: {
			label: $i18n.t('Busca na web'),
			description: $i18n.t('Modelo pode buscar informações na web')
		},
		image_generation: {
			label: $i18n.t('Criar imagem'),
			description: $i18n.t('Modelo inicia com geração de imagem por padrão')
		},
		code_execution: {
			label: $i18n.t('Artefatos'),
			description: $i18n.t('Modelo pode abrir artefatos por padrão')
		},
		deep_search: {
			label: $i18n.t('Pesquisa profunda'),
			description: $i18n.t('Modelo inicia com pesquisa profunda por padrão')
		},
		toggle_reasoning: {
			label: $i18n.t('Ajustar raciocínio'),
			description: $i18n.t('Show the Rápido/Raciocínio toggle in the message input bar')
		},
		stable_diffusion: {
			label: $i18n.t('Criar imagem'),
			description: $i18n.t('Modelo pode gerar imagens usando Stable Diffusion local')
		}
	};

	export let availableFeatures = [
		'web_search',
		'deep_search',
		'code_execution',
		'image_generation',
		'toggle_reasoning'
	];
	export let featureIds: string[] = [];
	export let tooltipsEnabled = true;

	let activeFeatureIds: string[] = [];
	let featureViewState: Record<string, { enabled: boolean; disabled: boolean }> = {};
	const independentFeatures = new Set(['toggle_reasoning']);

	const isExclusiveFeature = (feature: string) =>
		availableFeatures.includes(feature) && !independentFeatures.has(feature);

	const getFeatureLabel = (feature: string) =>
		featureLabels[feature as keyof typeof featureLabels] ?? {
			label: feature,
			description: feature
		};

	const normalizeFeatureIds = (ids: string[]) => {
		const supportedIds = ids.filter((id) => id !== 'code_interpreter');
		const selectedExclusiveFeature = [...supportedIds]
			.reverse()
			.find((id) => isExclusiveFeature(id));

		return supportedIds.filter(
			(id) => !isExclusiveFeature(id) || id === selectedExclusiveFeature
		);
	};

	const setFeatureState = (feature: string, enabled: boolean) => {
		if (enabled) {
			if (
				isExclusiveFeature(feature) &&
				activeFeatureIds.some((id) => isExclusiveFeature(id) && id !== feature)
			) return;
			featureIds = activeFeatureIds.includes(feature)
				? activeFeatureIds
				: [...activeFeatureIds, feature];
		} else {
			featureIds = activeFeatureIds.filter((id) => id !== feature);
		}
	};

	$: {
		const normalizedFeatureIds = normalizeFeatureIds(featureIds);
		const selectedExclusiveFeature = normalizedFeatureIds.find((id) => isExclusiveFeature(id));
		activeFeatureIds = normalizedFeatureIds;
		featureViewState = Object.fromEntries(
			availableFeatures.map((feature) => {
				const disabled = Boolean(
					isExclusiveFeature(feature) &&
					selectedExclusiveFeature &&
					selectedExclusiveFeature !== feature
				);

				return [
					feature,
					{
						enabled: normalizedFeatureIds.includes(feature) && !disabled,
						disabled
					}
				];
			})
		);

		if (normalizedFeatureIds.join('\u0000') !== featureIds.join('\u0000')) {
			featureIds = normalizedFeatureIds;
		}
	}
</script>

<div>
	<div class="flex flex-col mt-2 gap-2">
		{#each availableFeatures as feature}
			{#if feature === 'toggle_reasoning' && availableFeatures.includes('deep_search')}
				<div class="ml-1 mr-auto my-0.5 w-[92%] border-t border-gray-200/80 dark:border-gray-700/50"></div>
			{/if}
			{@const featureLabel = getFeatureLabel(feature)}
			{@const featureState = featureViewState[feature] ?? { enabled: false, disabled: false }}
			<div
				class="flex items-center gap-2 transition {featureState.disabled
					? 'opacity-50 text-gray-400 dark:text-gray-500'
					: ''}"
				aria-disabled={featureState.disabled}
			>
				<Switch
					state={featureState.enabled}
					disabled={featureState.disabled}
					on:change={(e) => {
						setFeatureState(feature, Boolean(e.detail));
					}}
				/>

				<div class="py-0.5 text-sm min-w-0">
					<Tooltip content={tooltipsEnabled ? marked.parse(featureLabel.description) : ''}>
						{$i18n.t(featureLabel.label)}
					</Tooltip>
				</div>
			</div>
		{/each}
	</div>
</div>
