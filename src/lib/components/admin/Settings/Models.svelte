<script lang="ts">
	import { marked } from 'marked';
	import fileSaver from 'file-saver';
	const { saveAs } = fileSaver;

	import { onMount, getContext, tick } from 'svelte';
	const i18n = getContext('i18n');

	import { WEBUI_NAME, config, mobile, models as _models, settings, user, showSettingsModelId } from '$lib/stores';
	import {
		createNewModel,
		deleteAllModels,
		getBaseModels,
		toggleModelById,
		updateModelById,
		importModels
	} from '$lib/apis/models';
	import { copyToClipboard } from '$lib/utils';
	import { page } from '$app/stores';
	import { updateUserSettings } from '$lib/apis/users';

	import { getModels } from '$lib/apis';
	import Search from '$lib/components/icons/Search.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import Spinner from '$lib/components/common/Spinner.svelte';
	import XMark from '$lib/components/icons/XMark.svelte';

	import ModelEditor from '$lib/components/workspace/Models/ModelEditor.svelte';
	import { toast } from 'svelte-sonner';
	import Badge from '$lib/components/common/Badge.svelte';
	import ConfirmDialog from '$lib/components/common/ConfirmDialog.svelte';
	import Cog6 from '$lib/components/icons/Cog6.svelte';
	import ModelSettingsModal from './Models/ModelSettingsModal.svelte';
	import Wrench from '$lib/components/icons/Wrench.svelte';
	import Download from '$lib/components/icons/Download.svelte';
	import ManageModelsModal from './Models/ManageModelsModal.svelte';
	import ModelMenu from '$lib/components/admin/Settings/Models/ModelMenu.svelte';
	import EllipsisHorizontal from '$lib/components/icons/EllipsisHorizontal.svelte';
	import EyeSlash from '$lib/components/icons/EyeSlash.svelte';
	import Eye from '$lib/components/icons/Eye.svelte';
	import CheckCircle from '$lib/components/icons/CheckCircle.svelte';
	import Minus from '$lib/components/icons/Minus.svelte';
	import { WEBUI_API_BASE_URL, WEBUI_BASE_URL } from '$lib/constants';
	import { goto } from '$app/navigation';
	import { DropdownMenu } from 'bits-ui';
	import { fade } from 'svelte/transition';
	import Dropdown from '$lib/components/common/Dropdown.svelte';
	import AdminViewSelector from './Models/AdminViewSelector.svelte';
	import Pagination from '$lib/components/common/Pagination.svelte';

	let shiftKey = false;

	let modelsImportInProgress = false;
	let importFiles;
	let modelsImportInputElement: HTMLInputElement;

	let models = null;

	let workspaceModels = null;
	let baseModels = null;

	let filteredModels = [];
	let selectedModelId = null;

	let showConfigModal = false;
	let showManageModal = false;

	let viewOption = ''; // '' = All, 'enabled', 'disabled', 'visible', 'hidden'

	const perPage = 30;
	let currentPage = 1;

	const isPublicModel = (model) => {
		return (model?.access_grants ?? []).some(
			(g) => g.principal_type === 'user' && g.principal_id === '*' && g.permission === 'read'
		);
	};

	$: if (models) {
		filteredModels = models
			.filter((m) => searchValue === '' || m.name.toLowerCase().includes(searchValue.toLowerCase()))
			.filter((m) => {
				if (viewOption === 'enabled') return m?.is_active ?? true;
				if (viewOption === 'disabled') return !(m?.is_active ?? true);
				if (viewOption === 'visible') return !(m?.meta?.hidden ?? false);
				if (viewOption === 'hidden') return m?.meta?.hidden === true;
				if (viewOption === 'public') return isPublicModel(m);
				if (viewOption === 'private') return !isPublicModel(m);
				return true; // All
			})
			.sort((a, b) => {
				return (a?.name ?? a?.id ?? '').localeCompare(b?.name ?? b?.id ?? '');
			});
	}

	let searchValue = '';

	$: if (searchValue || viewOption !== undefined) {
		currentPage = 1;
	}

	const enableAllHandler = async () => {
		const modelsToEnable = filteredModels.filter((m) => !(m.is_active ?? true));
		// Optimistic UI update
		modelsToEnable.forEach((m) => (m.is_active = true));
		models = models;
		// Sync with server
		await Promise.all(modelsToEnable.map((model) => toggleModelById(localStorage.token, model.id)));
	};

	const disableAllHandler = async () => {
		const modelsToDisable = filteredModels.filter((m) => m.is_active ?? true);
		// Optimistic UI update
		modelsToDisable.forEach((m) => (m.is_active = false));
		models = models;
		// Sync with server
		await Promise.all(
			modelsToDisable.map((model) => toggleModelById(localStorage.token, model.id))
		);
	};

	const showAllHandler = async () => {
		const modelsToShow = filteredModels.filter((m) => m?.meta?.hidden === true);
		// Optimistic UI update
		modelsToShow.forEach((m) => {
			m.meta = { ...m.meta, hidden: false };
		});
		models = models;
		// Sync with server
		await Promise.all(modelsToShow.map((model) => upsertModelHandler(model, false)));
		toast.success($i18n.t('All models are now visible'));
	};

	const hideAllHandler = async () => {
		const modelsToHide = filteredModels.filter((m) => !(m?.meta?.hidden ?? false));
		// Optimistic UI update
		modelsToHide.forEach((m) => {
			m.meta = { ...m.meta, hidden: true };
		});
		models = models;
		// Sync with server
		await Promise.all(modelsToHide.map((model) => upsertModelHandler(model, false)));
		toast.success($i18n.t('All models are now hidden'));
	};

	const downloadModels = async (models) => {
		let blob = new Blob([JSON.stringify(models)], {
			type: 'application/json'
		});
		saveAs(blob, `models-export-${Date.now()}.json`);
	};

	const init = async () => {
		// Phase 1: show models immediately from store (no spinner)
		baseModels = [...$_models];
		models = (baseModels ?? []).map((m) => ({
			...m,
			id: m.id,
			name: m.name,
			is_active: true
		}));

		// Phase 2: fetch workspace data and re-merge
		try {
			workspaceModels = await getBaseModels(localStorage.token);
		} catch (e) {
			console.error('Failed to load workspace models:', e);
			workspaceModels = [];
		}

		models = (baseModels ?? []).map((m) => {
			const workspaceModel = (workspaceModels ?? []).find((wm) => wm.id === m.id);

			if (workspaceModel) {
				return {
					...m,
					...workspaceModel
				};
			} else {
				return {
					...m,
					id: m.id,
					name: m.name,

					is_active: true
				};
			}
		});
	};

	const upsertModelHandler = async (model, showToast = true) => {
		if (workspaceModels.find((m) => m.id === model.id)) {
			const res = await updateModelById(localStorage.token, model.id, model).catch((error) => {
				return null;
			});

			if (res && showToast) {
				toast.success($i18n.t('Model updated successfully'));
			}
		} else {
			const res = await createNewModel(localStorage.token, {
				meta: {},
				id: model.id,
				name: model.name,
				base_model_id: null,
				params: {},
				access_grants: [],
				...model
			}).catch((error) => {
				return null;
			});

			if (res && !silent) {
				toast.success($i18n.t('Model updated successfully'));
			}
		}
		await init();

		_models.set(
			await getModels(
				localStorage.token,
				$config?.features?.enable_direct_connections && ($settings?.directConnections ?? null)
			)
		);
	};

	const toggleModelHandler = async (model) => {
		if (!Object.keys(model).includes('base_model_id')) {
			await createNewModel(localStorage.token, {
				id: model.id,
				name: model.name,
				base_model_id: null,
				meta: {},
				params: {},
				access_grants: [],
				is_active: model.is_active
			}).catch((error) => {
				return null;
			});
		} else {
			await toggleModelById(localStorage.token, model.id);
		}

		// await init();
		_models.set(
			await getModels(
				localStorage.token,
				$config?.features?.enable_direct_connections && ($settings?.directConnections ?? null)
			)
		);
	};

	const hideModelHandler = async (model) => {
		model.meta = {
			...model.meta,
			hidden: !(model?.meta?.hidden ?? false)
		};

		console.debug(model);

		upsertModelHandler(model, false);

		toast.success(
			model.meta.hidden
				? $i18n.t(`Model {{name}} is now hidden`, {
						name: model.id
					})
				: $i18n.t(`Model {{name}} is now visible`, {
						name: model.id
					})
		);
	};

	const copyLinkHandler = async (model) => {
		const baseUrl = window.location.origin;
		const res = await copyToClipboard(`${baseUrl}/?model=${encodeURIComponent(model.id)}`);

		if (res) {
			toast.success($i18n.t('Copied link to clipboard'));
		} else {
			toast.error($i18n.t('Failed to copy link'));
		}
	};

	const cloneHandler = async (model) => {
		sessionStorage.model = JSON.stringify({
			...model,
			base_model_id: model.id,
			id: `${model.id}-clone`,
			name: `${model.name} (Clone)`
		});
		goto('/workspace/models/create');
	};

	const exportModelHandler = async (model) => {
		let blob = new Blob([JSON.stringify([model])], {
			type: 'application/json'
		});
		saveAs(blob, `${model.id}-${Date.now()}.json`);
	};

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

	onMount(async () => {
		await init();
		const id = $page.url.searchParams.get('id') || $showSettingsModelId;

		if (id) {
			selectedModelId = id;
			showSettingsModelId.set('');
		}

		const onKeyDown = (event) => {
			if (event.key === 'Shift') {
				shiftKey = true;
			}
		};

		const onKeyUp = (event) => {
			if (event.key === 'Shift') {
				shiftKey = false;
			}
		};

		const onBlur = () => {
			shiftKey = false;
		};

		window.addEventListener('keydown', onKeyDown);
		window.addEventListener('keyup', onKeyUp);
		window.addEventListener('blur-sm', onBlur);

		return () => {
			window.removeEventListener('keydown', onKeyDown);
			window.removeEventListener('keyup', onKeyUp);
			window.removeEventListener('blur-sm', onBlur);
		};
	});
</script>

<ModelSettingsModal bind:show={showConfigModal} initHandler={init} />
<ManageModelsModal bind:show={showManageModal} />

{#if models !== null}
	{#if selectedModelId === null}
		<div class="flex flex-col h-full min-h-0">
		<div class="flex flex-col gap-1 mt-1.5 mb-2 shrink-0">
			<div class="flex justify-between items-center">
				<div class="flex items-center md:self-center text-xl font-medium px-0.5 gap-2 shrink-0">
					<div>
						{$i18n.t('Models')}
					</div>

					<div class="text-lg font-medium text-gray-500 dark:text-gray-500">
						{filteredModels.length}
					</div>
				</div>

				<div class="flex w-full justify-end gap-1.5">
					{#if $user?.role === 'admin'}
						<input
							id="models-import-input"
							bind:this={modelsImportInputElement}
							bind:files={importFiles}
							type="file"
							accept=".json"
							hidden
							on:change={() => {
								if (importFiles.length > 0) {
									const reader = new FileReader();
									reader.onload = async (event) => {
										modelsImportInProgress = true;

										try {
											const models = JSON.parse(String(event.target.result));
											const res = await importModels(localStorage.token, models);

											if (res) {
												toast.success($i18n.t('Models imported successfully'));
												await init();
											} else {
												toast.error($i18n.t('Failed to import models'));
											}
										} catch (e) {
											toast.error(e?.detail ?? $i18n.t('Invalid JSON file'));
											console.error(e);
										}

										modelsImportInProgress = false;
									};
									reader.readAsText(importFiles[0]);
								}
							}}
						/>

						<button
							class="flex text-xs items-center space-x-1 px-3 py-1.5 rounded-xl bg-gray-50 hover:bg-gray-100 dark:bg-gray-850 dark:hover:bg-gray-800 dark:text-gray-200 transition"
							disabled={modelsImportInProgress}
							on:click={() => {
								modelsImportInputElement.click();
							}}
						>
							{#if modelsImportInProgress}
								<Spinner className="size-3" />
							{/if}
							<div class=" self-center font-medium line-clamp-1">
								{$i18n.t('Import')}
							</div>
						</button>

						<button
							class="flex text-xs items-center space-x-1 px-3 py-1.5 rounded-xl bg-gray-50 hover:bg-gray-100 dark:bg-gray-850 dark:hover:bg-gray-800 dark:text-gray-200 transition"
							on:click={async () => {
								downloadModels(models);
							}}
						>
							<div class=" self-center font-medium line-clamp-1">
								{$i18n.t('Export')}
							</div>
						</button>
					{/if}



					<button
						class="flex text-xs items-center space-x-1 px-3 py-1.5 rounded-xl bg-black hover:bg-gray-900 text-white dark:bg-white dark:hover:bg-gray-100 dark:text-black transition font-medium"
						type="button"
						on:click={() => {
							showConfigModal = true;
						}}
					>
						<div class=" self-center font-medium line-clamp-1">
							{$i18n.t('Settings')}
						</div>
					</button>
				</div>
			</div>
		</div>

		<div class="overflow-y-auto flex-1 min-h-0">
		<div
			class="py-2 bg-white dark:bg-gray-900 rounded-3xl border border-gray-100/30 dark:border-gray-850/30"
		>
			<div class="px-3.5 flex flex-1 items-center w-full space-x-2 py-0.5 pb-2">
				<div class="flex flex-1 items-center">
					<div class=" self-center ml-1 mr-3">
						<Search className="size-3.5" />
					</div>
					<input
						class=" w-full text-sm py-1 rounded-r-xl outline-hidden bg-transparent"
						bind:value={searchValue}
						placeholder={$i18n.t('Search Models')}
					/>
					{#if searchValue}
						<div class="self-center pl-1.5 translate-y-[0.5px] rounded-l-xl bg-transparent">
							<button
								class="p-0.5 rounded-full hover:bg-gray-100 dark:hover:bg-gray-900 transition"
								on:click={() => {
									searchValue = '';
								}}
							>
								<XMark className="size-3" strokeWidth="2" />
							</button>
						</div>
					{/if}
				</div>
			</div>

			<div class="px-3 flex w-full items-center bg-transparent overflow-x-auto scrollbar-none">
				<div class="flex-1"></div>

				<Dropdown>
					<Tooltip content={$i18n.t('Actions')}>
						<button
							class="p-1 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition"
							type="button"
						>
							<EllipsisHorizontal className="size-4" />
						</button>
					</Tooltip>

					<div slot="content">
						<DropdownMenu.Content
						class="w-full max-w-[170px] rounded-md p-1 border border-gray-100 dark:border-gray-800 z-[10000] bg-white dark:bg-gray-850 dark:text-white shadow-md"
							sideOffset={-2}
							side="bottom"
							align="end"
							transition={(e) => fade(e, { duration: 100 })}
						>
							<DropdownMenu.Item
								class="select-none flex gap-2 items-center px-3 py-1.5 text-sm font-medium cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800 rounded-md"
								on:click={() => {
									enableAllHandler();
								}}
							>
								<CheckCircle className="size-4" />
								<div class="flex items-center">{$i18n.t('Enable All')}</div>
							</DropdownMenu.Item>

							<DropdownMenu.Item
								class="select-none flex gap-2 items-center px-3 py-1.5 text-sm font-medium cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800 rounded-md"
								on:click={() => {
									disableAllHandler();
								}}
							>
								<Minus className="size-4" />
								<div class="flex items-center">{$i18n.t('Disable All')}</div>
							</DropdownMenu.Item>
						</DropdownMenu.Content>
					</div>
				</Dropdown>
			</div>

			<div class="px-3 my-2" id="model-list">
				{#if filteredModels.length > 0}
					{#each filteredModels.slice((currentPage - 1) * perPage, currentPage * perPage) as model, modelIdx (`${model.id}-${model.is_active ?? true}`)}
						<div
							class=" flex space-x-4 cursor-pointer w-full px-3 py-2 dark:hover:bg-white/5 hover:bg-black/5 rounded-xl transition {model
								?.meta?.hidden
								? 'opacity-50 dark:opacity-50'
								: ''}"
							id="model-item-{model.id}"
						>
							<button
								class=" flex flex-1 text-left space-x-3.5 cursor-pointer w-full"
								type="button"
								on:click={() => {
									if (model?.is_active ?? true) selectedModelId = model.id;
								}}
							>
								<div class=" self-center w-9">
									<div
										class=" rounded-full object-cover {(model?.is_active ?? true)
											? ''
											: 'opacity-50 dark:opacity-50'} "
									>
										<img
											src={`${WEBUI_API_BASE_URL}/models/model/profile/image?id=${model.id}`}
											alt="modelfile profile"
											class=" rounded-full w-full h-auto object-cover"
										/>
									</div>
								</div>

								<div
									class=" flex-1 self-center {(model?.is_active ?? true) ? '' : 'text-gray-500'}"
								>
									<Tooltip
										content={marked.parse(
											!!model?.meta?.description
												? model?.meta?.description
												: model?.ollama?.digest
													? `${model?.ollama?.digest} **(${model?.ollama?.modified_at})**`
													: model.id
										)}
										className=" w-fit"
										placement="top-start"
									>
										<div class="font-medium line-clamp-1">
											{model.name}
										</div>
									</Tooltip>
									<div
										class=" text-xs overflow-hidden text-ellipsis line-clamp-1 flex items-center gap-1 text-gray-500"
									>
										<span class=" line-clamp-1">
											{!!model?.meta?.description
												? model?.meta?.description
												: model?.ollama?.digest
													? `${model.id} (${model?.ollama?.digest})`
													: model.id}
										</span>
									</div>
								</div>
							</button>
							<div class="flex flex-row gap-0.5 items-center self-center">
								{#if shiftKey}
									<Tooltip content={model?.meta?.hidden ? $i18n.t('Show') : $i18n.t('Hide')}>
										<button
											class="self-center w-fit text-sm px-2 py-2 dark:text-gray-300 dark:hover:text-white hover:bg-black/5 dark:hover:bg-white/5 rounded-xl"
											type="button"
											on:click={() => {
												hideModelHandler(model);
											}}
										>
											{#if model?.meta?.hidden}
												<EyeSlash />
											{:else}
												<Eye />
											{/if}
										</button>
									</Tooltip>
								{:else}
								{#if (model?.is_active ?? true)}
								<button
									class="self-center w-fit text-sm px-2 py-2 dark:text-gray-300 dark:hover:text-white hover:bg-black/5 dark:hover:bg-white/5 rounded-xl"
									type="button"
									on:click={() => {
										selectedModelId = model.id;
									}}
								>
									<svg
										xmlns="http://www.w3.org/2000/svg"
										fill="none"
										viewBox="0 0 24 24"
										stroke-width="1.5"
										stroke="currentColor"
										class="w-4 h-4"
									>
										<path
											stroke-linecap="round"
											stroke-linejoin="round"
											d="m16.862 4.487 1.687-1.688a1.875 1.875 0 1 1 2.652 2.652L6.832 19.82a4.5 4.5 0 0 1-1.897 1.13l-2.685.8.8-2.685a4.5 4.5 0 0 1 1.13-1.897L16.863 4.487Zm0 0L19.5 7.125"
										/>
									</svg>
								</button>
								{/if}
									<ModelMenu
										user={$user}
										{model}
										exportHandler={() => {
											exportModelHandler(model);
										}}
										pinModelHandler={() => {
											pinModelHandler(model.id);
										}}
										onClose={() => {}}
									>
										<button
											class="self-center w-fit text-sm p-1.5 dark:text-gray-300 dark:hover:text-white hover:bg-black/5 dark:hover:bg-white/5 rounded-xl"
											type="button"
										>
											<EllipsisHorizontal className="size-5" />
										</button>
									</ModelMenu>

									<div class="-ml-0.5">
										<Tooltip
											content={(model?.is_active ?? true)
												? $i18n.t('Enabled')
												: $i18n.t('Disabled')}
										>
										<button
											type="button"
											class="flex h-[1.125rem] min-h-[1.125rem] w-8 shrink-0 cursor-pointer items-center rounded-full px-[2px] mx-[1px] transition-colors outline outline-1 outline-gray-100 dark:outline-gray-800 {(model.is_active ?? true) ? 'bg-emerald-500 dark:bg-emerald-700' : 'bg-gray-200 dark:bg-transparent'}"
											on:click|stopPropagation={() => {
												const newActive = !(model.is_active ?? true);
											const updater = (m) =>
												m.id === model.id ? { ...m, is_active: newActive } : m;
											models = models.map(updater);
											filteredModels = filteredModels.map(updater);
												toggleModelHandler({ ...model, is_active: newActive });
											}}
										>
											<span
												class="pointer-events-none block size-3 shrink-0 rounded-full bg-white shadow-sm transition-transform {(model.is_active ?? true) ? 'translate-x-4' : 'translate-x-0'}"
											></span>
										</button>
										</Tooltip>
									</div>
								{/if}
							</div>
						</div>
					{/each}
				{:else}
					<div class=" w-full h-full flex flex-col justify-center items-center my-16 mb-24">
						<div class="max-w-md text-center">

							<div class=" text-lg font-medium mb-1">{$i18n.t('No models found')}</div>
							<div class=" text-gray-500 text-center text-xs">
								{$i18n.t('Try adjusting your search or filter to find what you are looking for.')}
							</div>
						</div>
					</div>
				{/if}
			</div>

			{#if filteredModels.length > perPage}
				<Pagination bind:page={currentPage} count={filteredModels.length} {perPage} />
			{/if}
		</div>
		</div><!-- end overflow-y-auto wrapper -->
		</div><!-- end h-full wrapper -->
	{:else}
		<div style="height: 62.6vh; min-height: 0; width: 100%; display: flex; flex-direction: column; overflow: hidden;">
			<ModelEditor
				edit
				model={models.find((m) => m.id === selectedModelId)}
				preset={false}
				onSubmit={async (model) => {
					console.log(model);
					await upsertModelHandler(model);
					selectedModelId = null;
				}}
				onBack={async () => {
					selectedModelId = null;
					await init();
				}}
			/>
		</div>
	{/if}
{:else}
	<div class=" h-full w-full flex justify-center items-center">
		<Spinner className="size-5" />
	</div>
{/if}
