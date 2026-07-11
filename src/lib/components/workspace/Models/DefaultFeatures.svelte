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
			label: $i18n.t('Geração de imagem'),
			description: $i18n.t('Modelo inicia com geração de imagem por padrão')
		},
		code_interpreter: {
			label: $i18n.t('Intérprete de código'),
			description: $i18n.t('Modelo pode executar código e cálculos')
		},
		code_execution: {
			label: $i18n.t('Mostrar artefatos'),
			description: $i18n.t('Modelo pode abrir artefatos por padrão')
		},
		deep_search: {
			label: $i18n.t('Pesquisa profunda'),
			description: $i18n.t('Modelo inicia com pesquisa profunda por padrão')
		},
		toggle_reasoning: {
			label: $i18n.t('Alternar raciocínio'),
			description: $i18n.t('Show the Rápido/Raciocínio toggle in the message input bar')
		},
		stable_diffusion: {
			label: $i18n.t('Geração de imagem'),
			description: $i18n.t('Modelo pode gerar imagens usando Stable Diffusion local')
		}
	};

	export let availableFeatures = [
		'web_search',
		'code_interpreter',
		'code_execution',
		'deep_search',
		'image_generation',
		'toggle_reasoning'
	];
	export let featureIds: string[] = [];
	export let tooltipsEnabled = true;

	let activeFeatureIds: string[] = [];
	let featureViewState: Record<string, { enabled: boolean; disabled: boolean }> = {};

	const getFeatureLabel = (feature: string) =>
		featureLabels[feature as keyof typeof featureLabels] ?? {
			label: feature,
			description: feature
		};

	const exclusiveFeatures = new Map([
		['web_search', 'code_interpreter'],
		['code_interpreter', 'web_search']
	]);

	const normalizeFeatureIds = (ids: string[]) => {
		if (!ids.includes('web_search') || !ids.includes('code_interpreter')) {
			return ids;
		}

		const keepFeature =
			ids.lastIndexOf('code_interpreter') > ids.lastIndexOf('web_search')
				? 'code_interpreter'
				: 'web_search';
		const removeFeature = exclusiveFeatures.get(keepFeature);

		return ids.filter((id) => id !== removeFeature);
	};

	const setFeatureState = (feature: string, enabled: boolean) => {
		const lockedByFeature = exclusiveFeatures.get(feature);
		if (lockedByFeature && activeFeatureIds.includes(lockedByFeature)) return;

		if (enabled) {
			const exclusiveFeature = exclusiveFeatures.get(feature);
			const nextFeatureIds = exclusiveFeature
				? activeFeatureIds.filter((id) => id !== exclusiveFeature)
				: activeFeatureIds;

			featureIds = nextFeatureIds.includes(feature)
				? nextFeatureIds
				: [...nextFeatureIds, feature];
		} else {
			featureIds = activeFeatureIds.filter((id) => id !== feature);
		}
	};

	$: {
		const normalizedFeatureIds = normalizeFeatureIds(featureIds);
		activeFeatureIds = normalizedFeatureIds;
		featureViewState = Object.fromEntries(
			availableFeatures.map((feature) => {
				const exclusiveFeature = exclusiveFeatures.get(feature);
				const disabled = Boolean(
					exclusiveFeature && normalizedFeatureIds.includes(exclusiveFeature)
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
