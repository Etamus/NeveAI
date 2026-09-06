<script lang="ts">
	import { getContext } from 'svelte';
	import type { Readable } from 'svelte/store';
	import Switch from '$lib/components/common/Switch.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import GlobeAlt from '$lib/components/icons/GlobeAlt.svelte';
	import Atom02 from '$lib/components/icons/Atom02.svelte';
	import Photo from '$lib/components/icons/Photo.svelte';
	import ImageIcon from '$lib/components/icons/Image.svelte';
	import MusicNote from '$lib/components/icons/MusicNote.svelte';
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
		stable_diffusion: {
			label: $i18n.t('Criar imagem'),
			description: $i18n.t('Modelo pode gerar imagens usando Stable Diffusion local')
		},
		music_generation: {
			label: $i18n.t('Criar música'),
			description: $i18n.t('Modelo inicia com geração de música por padrão')
		}
	};

	export let availableFeatures = [
		'web_search',
		'deep_search',
		'code_execution',
		'image_generation',
		'stable_diffusion',
		'music_generation'
	];
	export let featureIds: string[] = [];
	export let tooltipsEnabled = true;
	export let insetToggles = false;

	let activeFeatureIds: string[] = [];
	let featureViewState: Record<string, { enabled: boolean; disabled: boolean }> = {};
	const isExclusiveFeature = (feature: string) =>
		availableFeatures.includes(feature);

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
	<div class="flex flex-col mt-3 gap-2">
		{#each availableFeatures as feature}
			{@const featureLabel = getFeatureLabel(feature)}
			{@const featureState = featureViewState[feature] ?? { enabled: false, disabled: false }}
			{#if feature === 'stable_diffusion' && availableFeatures.includes('code_execution')}
				<div class="my-0.5 w-[96%] border-t border-gray-300/50 dark:border-gray-600/30"></div>
			{/if}
			<div
				class="flex w-full items-center justify-between gap-3 transition {featureState.disabled
					? 'opacity-50 text-gray-400 dark:text-gray-500'
					: ''}"
				aria-disabled={featureState.disabled}
			>
				<div class="flex min-w-0 items-center gap-2">
					<div class="flex size-4 shrink-0 items-center justify-center">
						{#if feature === 'web_search'}
							<GlobeAlt />
						{:else if feature === 'deep_search'}
							<Atom02 />
						{:else if feature === 'code_execution'}
							<svg aria-hidden="true" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5" class="size-4">
								<path stroke-linecap="round" stroke-linejoin="round" d="m21 7.5-9-5.25L3 7.5m18 0-9 5.25m9-5.25v9l-9 5.25M3 7.5l9 5.25M3 7.5v9l9 5.25m0-9v9" />
							</svg>
						{:else if feature === 'image_generation'}
							<Photo className="size-4" strokeWidth="1.5" />
						{:else if feature === 'stable_diffusion'}
							<ImageIcon className="size-4" strokeWidth="1.5" />
						{:else if feature === 'music_generation'}
							<MusicNote className="size-4" strokeWidth="1.5" />
						{/if}
					</div>
					<div class="min-w-0 py-0.5 text-sm text-gray-700 dark:text-gray-300">
						<Tooltip content={tooltipsEnabled ? marked.parse(featureLabel.description) : ''}>
							{$i18n.t(featureLabel.label)}
						</Tooltip>
					</div>
				</div>

				<div class="shrink-0 {insetToggles ? 'mr-2' : ''}">
					<Switch
						state={featureState.enabled}
						disabled={featureState.disabled}
						on:change={(e) => {
							setFeatureState(feature, Boolean(e.detail));
						}}
					/>
				</div>
			</div>
		{/each}
	</div>
</div>
