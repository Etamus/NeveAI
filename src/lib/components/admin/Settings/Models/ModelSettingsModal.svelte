<script>
	import { toast } from 'svelte-sonner';

	import { createEventDispatcher, getContext, onDestroy, onMount } from 'svelte';
	const i18n = getContext('i18n');
	const dispatch = createEventDispatcher();

	import { models, config as _config, settings } from '$lib/stores';
	import { DEFAULT_CAPABILITIES } from '$lib/constants';
	import { deleteAllModels, updateModelById } from '$lib/apis/models';
	import { getModelsConfig, setModelsConfig, setDefaultPromptSuggestions } from '$lib/apis/configs';
	import { getBackendConfig } from '$lib/apis';
	import { getModels } from '$lib/apis';

	import Modal from '$lib/components/common/Modal.svelte';
	import ConfirmDialog from '$lib/components/common/ConfirmDialog.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import ModelList from './ModelList.svelte';
	import Spinner from '$lib/components/common/Spinner.svelte';
	import Minus from '$lib/components/icons/Minus.svelte';
	import Plus from '$lib/components/icons/Plus.svelte';
	import ChevronUp from '$lib/components/icons/ChevronUp.svelte';
	import ChevronDown from '$lib/components/icons/ChevronDown.svelte';
	import XMark from '$lib/components/icons/XMark.svelte';
	import ModelSelector from './ModelSelector.svelte';
	import Model from '../Evaluations/Model.svelte';
	import AdvancedParams from '$lib/components/chat/Settings/Advanced/AdvancedParams.svelte';

	import DefaultFeatures from '$lib/components/workspace/Models/DefaultFeatures.svelte';
	import PromptSuggestions from '$lib/components/workspace/Models/PromptSuggestions.svelte';

	import Eye from '$lib/components/icons/Eye.svelte';

	export let show = false;
	export let initHandler = () => {};

	let config = null;
	let initializedForOpen = false;

	let selectedTab = 'defaults';

	let selectedModelId = '';
	let defaultModelIds = [];

	let selectedPinnedModelId = '';
	let defaultPinnedModelIds = [];

	let modelIds = [];
	let saveModelOrderTimer = null;

	let sortKey = '';
	let sortOrder = '';

	let loading = false;
	let showResetModal = false;
	let showDefaultPromptSuggestions = false;

	let defaultCapabilities = {};
	let defaultFeatureIds = [];
	let defaultParams = {};
	let builtinTools = {};
	let promptSuggestions = [];

	$: {
		if (show && !initializedForOpen) {
			initializedForOpen = true;
			init();
		}

		if (!show && initializedForOpen) {
			initializedForOpen = false;
		}
	}
	const init = async () => {
		config = await getModelsConfig(localStorage.token);

		if (config?.DEFAULT_MODELS) {
			defaultModelIds = (config?.DEFAULT_MODELS).split(',').filter((id) => id);
		} else {
			defaultModelIds = [];
		}

		if (config?.DEFAULT_PINNED_MODELS) {
			defaultPinnedModelIds = (config?.DEFAULT_PINNED_MODELS).split(',').filter((id) => id);
		} else {
			defaultPinnedModelIds = [];
		}

		const modelOrderList = config.MODEL_ORDER_LIST || [];
		const allModelIds = $models.map((model) => model.id);

		// Use current $models order (already sorted by backend) as the source of truth
		modelIds = allModelIds;

		sortKey = '';
		sortOrder = '';

		const savedMeta = config?.DEFAULT_MODEL_METADATA;
		if (savedMeta && Object.keys(savedMeta).length > 0) {
			defaultCapabilities = savedMeta.capabilities ?? { ...DEFAULT_CAPABILITIES };
			defaultFeatureIds = savedMeta.defaultFeatureIds ?? [];
			builtinTools = savedMeta.builtinTools ?? {};
		} else {
			defaultCapabilities = { ...DEFAULT_CAPABILITIES };
			defaultFeatureIds = [];
			builtinTools = {};
		}
		defaultParams = config?.DEFAULT_MODEL_PARAMS ?? {};

		promptSuggestions = $_config?.default_prompt_suggestions ?? [];
	};
	const submitHandler = async () => {
		loading = true;

		const metadata = {
			capabilities: defaultCapabilities,
			...(defaultFeatureIds.length > 0 ? { defaultFeatureIds } : {}),
			...(Object.keys(builtinTools).length > 0 ? { builtinTools } : {})
		};

		const res = await setModelsConfig(localStorage.token, {
			DEFAULT_MODELS: defaultModelIds.join(','),
			DEFAULT_PINNED_MODELS: defaultPinnedModelIds.join(','),
			MODEL_ORDER_LIST: modelIds,
			DEFAULT_MODEL_METADATA: metadata,
			DEFAULT_MODEL_PARAMS: Object.fromEntries(
				Object.entries(defaultParams).filter(([_, v]) => v !== null && v !== '' && v !== undefined)
			)
		});

		if (res) {
			promptSuggestions = promptSuggestions.filter((p) => p.content !== '');
			promptSuggestions = await setDefaultPromptSuggestions(localStorage.token, promptSuggestions);
			await _config.set(await getBackendConfig());

			// Apply defaultParams to each selected model individually
			const cleanParams = Object.fromEntries(
				Object.entries(defaultParams).filter(([_, v]) => v !== null && v !== '' && v !== undefined)
			);
			if (Object.keys(cleanParams).length > 0) {
				for (const modelId of defaultModelIds) {
					const model = $models.find((m) => m.id === modelId);
					if (model) {
						try {
							await updateModelById(localStorage.token, modelId, {
								...model,
								params: { ...(model.params || {}), ...cleanParams }
							});
						} catch (e) {
							console.debug(`Skipped updating params for ${modelId}:`, e);
						}
					}
				}
			}

			toast.success($i18n.t('Models configuration saved successfully'));
			models.set(
				await getModels(
					localStorage.token,
					$_config?.features?.enable_direct_connections && ($settings?.directConnections ?? null)
				)
			);
			initHandler();
			show = false;
		} else {
			toast.error($i18n.t('Failed to save models configuration'));
		}

		loading = false;
	};

	const saveModelOrder = async () => {
		await setModelsConfig(localStorage.token, {
			DEFAULT_MODELS: defaultModelIds.join(','),
			DEFAULT_PINNED_MODELS: defaultPinnedModelIds.join(','),
			MODEL_ORDER_LIST: modelIds
		});
	};

	const scheduleSaveModelOrder = () => {
		if (saveModelOrderTimer) {
			clearTimeout(saveModelOrderTimer);
		}

		saveModelOrderTimer = setTimeout(() => {
			saveModelOrderTimer = null;
			saveModelOrder();
		}, 350);
	};

	onMount(async () => {
		init();
	});

	onDestroy(() => {
		if (saveModelOrderTimer) {
			clearTimeout(saveModelOrderTimer);
			saveModelOrder();
		}
	});
</script>

<ConfirmDialog
	title={$i18n.t('Reset All Models')}
	message={$i18n.t('This will delete all models including custom models and cannot be undone.')}
	bind:show={showResetModal}
	onConfirm={async () => {
		const res = deleteAllModels(localStorage.token);
		if (res) {
			toast.success($i18n.t('All models deleted successfully'));
			initHandler();
		}
	}}
/>

<Modal size="md" className="bg-white dark:bg-gray-900 rounded-xl w-[48rem]! h-[62vh]! max-h-[calc(100dvh-2rem)]! max-w-[calc(100vw-2rem)]! flex flex-col" bind:show>
	<div class="flex h-full min-h-0 flex-col">
		<div class="flex justify-between items-center dark:text-gray-100 px-5 pt-4 pb-3 border-b border-gray-200/30 dark:border-gray-700/20 shrink-0">
			<div class="text-lg font-semibold font-primary">
				{$i18n.t('Settings')}
			</div>
			<button
				class="text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 transition"
				on:click={() => {
					show = false;
				}}
			>
				<XMark className={'size-5'} />
			</button>
		</div>

		<div class="flex flex-col md:flex-row w-full dark:text-gray-200 flex-1 min-h-0">
			<div class=" flex flex-col w-full min-h-0">
				{#if config}
					<form
						class="flex flex-col w-full h-full min-h-0"
						on:submit|preventDefault={() => {
							submitHandler();
						}}
					>
						<div class="flex flex-col w-full h-full min-h-0">
									<div class="flex-1 mt-0 flex flex-col min-w-0 min-h-0">
								<div class="w-full h-full overflow-y-auto overflow-x-hidden scrollbar-hidden px-4 py-3">
									{#if true}
									<div class="h-full min-h-0 overflow-hidden">
										<div class="flex gap-0 w-full h-full min-h-0 pl-1">
											<div class="w-[28%] min-w-0 h-full flex flex-col pr-4">
												<button
													class="text-xs font-semibold text-gray-500 dark:text-gray-400 mb-2 py-1 pl-1 pr-2 shrink-0 flex gap-1 items-center text-left hover:text-gray-700 dark:hover:text-gray-300 transition whitespace-nowrap"
													type="button"
													on:click={() => {
														sortKey = 'model';
														if (sortOrder === 'asc') {
															sortOrder = 'desc';
														} else {
															sortOrder = 'asc';
														}
														modelIds = modelIds
															.filter((id) => id !== '')
															.sort((a, b) => {
																const nameA = $models.find((model) => model.id === a)?.name || a;
																const nameB = $models.find((model) => model.id === b)?.name || b;
																return sortOrder === 'desc'
																	? nameA.localeCompare(nameB)
																	: nameB.localeCompare(nameA);
															});
														saveModelOrder();
													}}
												>
													<span>{$i18n.t('Reorder Models')}</span>
													{#if sortKey === 'model'}
														<span class="font-normal self-center shrink-0">
															{#if sortOrder === 'asc'}
																<ChevronUp className="size-3" />
															{:else}
																<ChevronDown className="size-3" />
															{/if}
														</span>
													{:else}
														<span class="invisible shrink-0">
															<ChevronUp className="size-3" />
														</span>
													{/if}
												</button>
												<div class="flex-1 min-h-0 overflow-y-auto pr-2">
													<ModelList bind:modelIds on:reorder={scheduleSaveModelOrder} />
												</div>
											</div>

											<div class="border-l border-gray-300/50 dark:border-gray-600/30"></div>
											<div class="w-[44%] min-w-0 h-full flex flex-col px-4">
												<div class="text-xs font-semibold text-gray-500 dark:text-gray-400 mb-2 py-1 pl-2 pr-5 shrink-0 whitespace-nowrap">
													{$i18n.t('Model Parameters')}
												</div>
												<div class="flex-1 min-h-0 overflow-y-auto pr-3 no-ap-sep">
													<div class="model-settings-default-params">
														<AdvancedParams admin={true} janStyle={true} bind:params={defaultParams} tooltipsEnabled={false} />
													</div>
												</div>
											</div>

											<div class="border-l border-gray-300/50 dark:border-gray-600/30"></div>
											<div class="w-[28%] min-w-0 pl-4 h-full overflow-hidden">
												<div class="text-xs font-semibold text-gray-500 dark:text-gray-400 mb-2 py-1 shrink-0 whitespace-nowrap">
													{$i18n.t('Model Capabilities')}
												</div>
												<DefaultFeatures
													availableFeatures={['web_search', 'code_interpreter', 'code_execution']}
													bind:featureIds={defaultFeatureIds}
													tooltipsEnabled={false}
												/>
											</div>
										</div>
									</div>
								{/if}
							</div>
						</div>
					</div>
					</form>
				{:else}
					<div>
						<Spinner className="size-5" />
					</div>
				{/if}
			</div>
		</div>
	</div>
</Modal>

<style>
	.no-ap-sep :global(hr) {
		display: none;
	}

	.model-settings-default-params :global(.inline-tooltip) {
		margin-left: 0.5rem;
		margin-right: 1rem;
	}

	.model-settings-default-params :global(.flex.w-full.items-center.justify-between) {
		gap: 1rem;
	}
</style>
