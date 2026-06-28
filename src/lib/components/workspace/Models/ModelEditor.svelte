<script lang="ts">
	import { toast } from 'svelte-sonner';
	import { hideAll as tippyHideAll } from 'tippy.js';

	import { onMount, onDestroy, getContext, tick } from 'svelte';
	import { models, tools, functions, user } from '$lib/stores';
	import { NEVEAI_BASE_URL, DEFAULT_CAPABILITIES } from '$lib/constants';

	import { getTools } from '$lib/apis/tools';
	import { getFunctions } from '$lib/apis/functions';

	import AdvancedParams from '$lib/components/chat/Settings/Advanced/AdvancedParams.svelte';
	import Tags from '$lib/components/common/Tags.svelte';
	import Knowledge from '$lib/components/workspace/Models/Knowledge.svelte';
	import ToolsSelector from '$lib/components/workspace/Models/ToolsSelector.svelte';
	import SkillsSelector from '$lib/components/workspace/Models/SkillsSelector.svelte';
	import FiltersSelector from '$lib/components/workspace/Models/FiltersSelector.svelte';
	import ActionsSelector from '$lib/components/workspace/Models/ActionsSelector.svelte';
	import Capabilities from '$lib/components/workspace/Models/Capabilities.svelte';
	import Textarea from '$lib/components/common/Textarea.svelte';
	import AccessControl from '../common/AccessControl.svelte';
	import Spinner from '$lib/components/common/Spinner.svelte';
	import XMark from '$lib/components/icons/XMark.svelte';
	import DefaultFiltersSelector from './DefaultFiltersSelector.svelte';
	import DefaultFeatures from './DefaultFeatures.svelte';
	import BuiltinTools from './BuiltinTools.svelte';
	import PromptSuggestions from './PromptSuggestions.svelte';
	import AccessControlModal from '../common/AccessControlModal.svelte';
	import LockClosed from '$lib/components/icons/LockClosed.svelte';
	import { updateModelAccessGrants } from '$lib/apis/models';

	const i18n = getContext('i18n');

	export let onSubmit: Function;
	export let onBack: null | Function = null;

	export let model = null;
	export let edit = false;

	export let preset = true;

	let loading = false;
	let success = false;

	let filesInputElement;
	let inputFiles;

	let showAdvanced = false;
	let showAccessControlModal = false;

	let loaded = false;
	let autoSaveTimer: any = null;
	let initialized = false;
	let savingOnClose = false;

	function debouncedSave() {
		if (!initialized || !edit) return;
		if (knowledge.some((item: any) => item.status === 'uploading')) return;
		clearTimeout(autoSaveTimer);
		autoSaveTimer = setTimeout(submitHandler, 300);
	}

	function updateProfileImageUrl(url: string) {
		info.meta.profile_image_url = url;
		debouncedSave();
	}

	onDestroy(() => {
		if (autoSaveTimer) {
			clearTimeout(autoSaveTimer);
		}
		if (initialized && edit && !savingOnClose) {
			submitHandler();
		}
	});

	$: system, params, capabilities, defaultFeatureIds, filterIds, defaultFilterIds, actionIds, toolIds, skillIds, builtinTools, name, knowledge, tts, accessGrants, baseModelId, description, debouncedSave();

	// ///////////
	// model
	// ///////////

	let id = '';
	let name = '';
	let description = '';
	let baseModelId: string | null = null;

	let enableDescription = true;

	$: if (!edit) {
		if (name) {
			id = name
				.replace(/\s+/g, '-')
				.replace(/[^a-zA-Z0-9-]/g, '')
				.toLowerCase();
		}
	}

	let system = '';
	let showSystemPromptField = false;
	$: if (system !== '') showSystemPromptField = true;
	const DEFAULT_MODEL_PROFILE_IMAGE_URL = `${NEVEAI_BASE_URL}/static/favicon.png`;
	let info = {
		id: '',
		base_model_id: null,
		name: '',
		meta: {
			profile_image_url: DEFAULT_MODEL_PROFILE_IMAGE_URL,
			description: '',
			suggestion_prompts: null,
			tags: []
		},
		params: {
			system: ''
		}
	};

	let params = {
		system: ''
	};

	let knowledge = [];
	let toolIds = [];
	let skillIds = [];

	let filterIds = [];
	let defaultFilterIds = [];

	let capabilities = { ...DEFAULT_CAPABILITIES };
	let defaultFeatureIds = [];
	let builtinTools = {};

	let actionIds = [];
	let accessGrants = [];
	let tts = { voice: '' };

	const submitHandler = async () => {
		loading = true;

		info.id = id;
		info.name = name;

		if (id === '') {
			toast.error($i18n.t('Model ID is required.'));
			loading = false;

			return;
		}

		if (name === '') {
			toast.error($i18n.t('Model Name is required.'));
			loading = false;

			return;
		}

		if (knowledge.some((item) => item.status === 'uploading')) {
			toast.error($i18n.t('Please wait until all files are uploaded.'));
			loading = false;

			return;
		}

		info.params = { ...info.params, ...params };

		info.base_model_id = baseModelId;
		info.access_grants = accessGrants;
		info.meta.capabilities = { ...DEFAULT_CAPABILITIES };
		info.meta.capabilities.toggle_reasoning = defaultFeatureIds.includes('toggle_reasoning');

		if (description.trim() !== '') {
			info.meta.description = description;
		} else {
			info.meta.description = null;
		}

		if (knowledge.length > 0) {
			info.meta.knowledge = knowledge;
		} else {
			if (info.meta.knowledge) {
				delete info.meta.knowledge;
			}
		}

		if (toolIds.length > 0) {
			info.meta.toolIds = toolIds;
		} else {
			if (info.meta.toolIds) {
				delete info.meta.toolIds;
			}
		}

		if (skillIds.length > 0) {
			info.meta.skillIds = skillIds;
		} else {
			if (info.meta.skillIds) {
				delete info.meta.skillIds;
			}
		}

		if (filterIds.length > 0) {
			info.meta.filterIds = filterIds;
		} else {
			if (info.meta.filterIds) {
				delete info.meta.filterIds;
			}
		}

		if (defaultFilterIds.length > 0) {
			info.meta.defaultFilterIds = defaultFilterIds;
		} else {
			if (info.meta.defaultFilterIds) {
				delete info.meta.defaultFilterIds;
			}
		}

		if (actionIds.length > 0) {
			info.meta.actionIds = actionIds;
		} else {
			if (info.meta.actionIds) {
				delete info.meta.actionIds;
			}
		}

		if (defaultFeatureIds.length > 0) {
			info.meta.defaultFeatureIds = defaultFeatureIds;
		} else {
			if (info.meta.defaultFeatureIds) {
				delete info.meta.defaultFeatureIds;
			}
		}

		if (Object.keys(builtinTools).length > 0) {
			info.meta.builtinTools = builtinTools;
		} else {
			if (info.meta.builtinTools) {
				delete info.meta.builtinTools;
			}
		}

		if (tts.voice !== '') {
			if (!info.meta.tts) info.meta.tts = {};
			info.meta.tts.voice = tts.voice;
		} else {
			if (info.meta.tts?.voice) {
				delete info.meta.tts.voice;
				if (Object.keys(info.meta.tts).length === 0) {
					delete info.meta.tts;
				}
			}
		}

		info.params.system = system.trim() === '' ? null : system;
		info.params.stop = params.stop
			? (typeof params.stop === 'string' ? params.stop.split(',') : params.stop).filter((s) =>
					s.trim()
				)
			: null;
		delete info.params.cache_type;
		delete info.params.stream_response;
		Object.keys(info.params).forEach((key) => {
			if (info.params[key] === '' || info.params[key] === null) {
				delete info.params[key];
			}
		});

		try {
			await onSubmit(info);
			success = true;
		} catch (e) {
			console.error('onSubmit error:', e);
		} finally {
			loading = false;
		}
	};

	const refreshModelEditorResources = async () => {
		const [toolsResult, functionsResult] = await Promise.allSettled([
			getTools(localStorage.token),
			getFunctions(localStorage.token)
		]);

		if (toolsResult.status === 'fulfilled') {
			await tools.set(toolsResult.value);
		}
		if (functionsResult.status === 'fulfilled') {
			await functions.set(functionsResult.value);
		}
	};

	onMount(async () => {
		const resourcesReady = Array.isArray($tools) && Array.isArray($functions);
		const resourcesPromise = refreshModelEditorResources();
		if (!resourcesReady) {
			await resourcesPromise;
		}

		// Scroll to top 'workspace-container' element
		const workspaceContainer = document.getElementById('workspace-container');
		if (workspaceContainer) {
			workspaceContainer.scrollTop = 0;
		}

		if (model) {
			name = model.name;
			await tick();

			id = model.id;

			description = model?.meta?.description ?? '';

			if (model.base_model_id) {
				const base_model = $models
					.filter((m) => !m?.preset && !(m?.arena ?? false))
					.find((m) => [model.base_model_id, `${model.base_model_id}:latest`].includes(m.id));

				console.log('base_model', base_model);

				if (base_model) {
					model.base_model_id = base_model.id;
				} else {
					model.base_model_id = null;
				}
			}

			baseModelId = model.base_model_id ?? null;

			system = model?.params?.system ?? '';

			params = { ...params, ...model?.params };
			params.stop = params?.stop
				? (typeof params.stop === 'string' ? params.stop.split(',') : (params?.stop ?? [])).join(
						','
					)
				: null;

			knowledge = (model?.meta?.knowledge ?? []).map((item) => {
				if (item?.collection_name && item?.type !== 'file') {
					return {
						id: item.collection_name,
						name: item.name,
						legacy: true
					};
				} else if (item?.collection_names) {
					return {
						name: item.name,
						type: 'collection',
						collection_names: item.collection_names,
						legacy: true
					};
				} else {
					return item;
				}
			});

			toolIds = model?.meta?.toolIds ?? [];
			skillIds = model?.meta?.skillIds ?? [];
			filterIds = model?.meta?.filterIds ?? [];
			defaultFilterIds = model?.meta?.defaultFilterIds ?? [];
			actionIds = model?.meta?.actionIds ?? [];

			capabilities = { ...capabilities, ...(model?.meta?.capabilities ?? {}) };
			defaultFeatureIds = model?.meta?.defaultFeatureIds ?? [];
			if (capabilities.toggle_reasoning !== false && !defaultFeatureIds.includes('toggle_reasoning')) {
				defaultFeatureIds = [...defaultFeatureIds, 'toggle_reasoning'];
			}
			builtinTools = model?.meta?.builtinTools ?? {};
			tts = { voice: model?.meta?.tts?.voice ?? '' };

			accessGrants = model?.access_grants ?? [];

			info = {
				...info,
				...JSON.parse(
					JSON.stringify(
						model
							? model
							: {
									id: model.id,
									name: model.name
								}
					)
				)
			};

			console.log(model);
		}

		loaded = true;
		if (edit) {
			await tick();
			initialized = true;
		}
	});
</script>

{#if loaded}
	<AccessControlModal
		bind:show={showAccessControlModal}
		bind:accessGrants
		accessRoles={preset ? ['read', 'write'] : ['read']}
		share={$user?.permissions?.sharing?.models || $user?.role === 'admin'}
		sharePublic={$user?.permissions?.sharing?.public_models || $user?.role === 'admin'}
		shareUsers={($user?.permissions?.access_grants?.allow_users ?? true) || $user?.role === 'admin'}
		onChange={async () => {
			if (edit && model?.id) {
				try {
					await updateModelAccessGrants(
						localStorage.token,
						model.id,
						model.name ?? name,
						accessGrants
					);
					toast.success($i18n.t('Saved'));
				} catch (error) {
					toast.error(error?.detail ?? `${error}`);
				}
			}
		}}
	/>

	<!-- Layout wrapper: flex column fills available height (e.g. 28rem in Settings modal) -->
	<div class="flex flex-col h-full min-h-0">
		{#if onBack}
		<div class="flex justify-between items-center dark:text-gray-100 px-5 pt-4 pb-3 border-b border-gray-200/30 dark:border-gray-700/20 shrink-0">
			<div class="text-lg font-semibold font-primary">
				{$i18n.t('Editar modelo')}
			</div>
			<button
				class="text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 transition"
				type="button"
				on:click={async () => {
					savingOnClose = true;
					if (autoSaveTimer) {
						clearTimeout(autoSaveTimer);
						autoSaveTimer = null;
					}
					if (initialized && edit) {
						await submitHandler();
					}
					onBack();
				}}
			>
				<XMark className="size-5" />
			</button>
		</div>
		{/if}

	<div class="w-full flex flex-col flex-1 min-h-0 overflow-hidden">
		<input
			bind:this={filesInputElement}
			bind:files={inputFiles}
			type="file"
			hidden
			accept="image/*"
			on:change={() => {
				let reader = new FileReader();
				reader.onload = (event) => {
					let originalImageUrl = `${event.target?.result}`;

					// For animated formats (gif, webp), skip resizing to preserve animation
					const fileType = (inputFiles[0] as any)?.['type'];
					if (fileType === 'image/gif' || fileType === 'image/webp') {
						updateProfileImageUrl(originalImageUrl);
						inputFiles = null;
						filesInputElement.value = '';
						return;
					}

					const img = new Image();
					img.src = originalImageUrl;

					img.onload = function () {
						const canvas = document.createElement('canvas');
						const ctx = canvas.getContext('2d');

						// Calculate the aspect ratio of the image
						const aspectRatio = img.width / img.height;

						// Calculate the new width and height to fit within 100x100
						let newWidth, newHeight;
						if (aspectRatio > 1) {
							newWidth = 250 * aspectRatio;
							newHeight = 250;
						} else {
							newWidth = 250;
							newHeight = 250 / aspectRatio;
						}

						// Set the canvas size
						canvas.width = 250;
						canvas.height = 250;

						// Calculate the position to center the image
						const offsetX = (250 - newWidth) / 2;
						const offsetY = (250 - newHeight) / 2;

						// Draw the image on the canvas
						ctx.drawImage(img, offsetX, offsetY, newWidth, newHeight);

						// Get the base64 representation of the compressed image
						const compressedSrc = canvas.toDataURL('image/webp', 0.8);

						// Display the compressed image
						updateProfileImageUrl(compressedSrc);

						inputFiles = null;
						filesInputElement.value = '';
					};
				};

				if (
					inputFiles &&
					inputFiles.length > 0 &&
					['image/gif', 'image/webp', 'image/jpeg', 'image/png', 'image/svg+xml'].includes(
						(inputFiles[0] as any)?.['type']
					)
				) {
					reader.readAsDataURL(inputFiles[0]);
				} else {
					console.log(`Unsupported File Type '${(inputFiles[0] as any)?.['type']}'.`);
					inputFiles = null;
				}
			}}
		/>

		{#if !edit || (edit && model)}
			<form
				class="flex flex-col flex-1 min-h-0 w-full"
				on:submit|preventDefault={() => {
					submitHandler();
				}}
			>
				<div class="w-full pl-8 pr-4" on:scroll={() => tippyHideAll()}>
					<!-- Profile Image + Name/ID Header -->
					<div class="flex flex-row gap-4 md:gap-6 w-full">
						<div class="self-start flex justify-center my-2 shrink-0">
							<div class="self-center">
								<div class="relative inline-flex">
									<button
										class="rounded-xl flex shrink-0 items-center {info.meta.profile_image_url !==
										DEFAULT_MODEL_PROFILE_IMAGE_URL
											? 'bg-transparent'
											: 'bg-white'} shadow-xl group relative"
										type="button"
										aria-label={$i18n.t('Upload profile image')}
										on:click={() => {
											filesInputElement.click();
										}}
									>
										{#if info.meta.profile_image_url}
											<img
												src={info.meta.profile_image_url}
												alt="model profile"
												class="rounded-lg size-20 md:size-36 object-cover shrink-0"
											/>
										{:else}
											<img
												src={DEFAULT_MODEL_PROFILE_IMAGE_URL}
												alt="model profile"
												class="rounded-lg size-20 md:size-36 object-cover shrink-0"
											/>
										{/if}

										<div
											class="absolute top-0 bottom-0 left-0 right-0 bg-white dark:bg-black rounded-lg opacity-0 group-hover:opacity-20 transition"
										></div>
									</button>

									{#if info.meta.profile_image_url && info.meta.profile_image_url !== DEFAULT_MODEL_PROFILE_IMAGE_URL}
										<button
											class="absolute right-1.5 top-1.5 z-10 flex size-6 items-center justify-center rounded-full border border-gray-200 bg-white text-gray-500 shadow-md transition hover:text-gray-700 dark:border-gray-700 dark:bg-gray-850 dark:text-gray-300 dark:hover:text-white"
											type="button"
											aria-label={$i18n.t('Reset Image')}
											title={$i18n.t('Reset Image')}
											on:click={() => {
												updateProfileImageUrl(DEFAULT_MODEL_PROFILE_IMAGE_URL);
											}}
										>
											<XMark className="size-3.5" />
										</button>
									{/if}
								</div>
							</div>
						</div>

						<div class="flex flex-col w-full flex-1">
							<div class="flex flex-col w-full mt-2">
								<input
									class="text-2xl font-semibold leading-none w-full bg-transparent outline-hidden p-0"
									placeholder={$i18n.t('Model Name')}
									bind:value={name}
									spellcheck="false"
									required
								/>
								<input
									class="text-xs w-full bg-transparent outline-hidden text-gray-400 p-0 mt-px"
									placeholder={$i18n.t('Model ID')}
									value={id.replace(/^local\//, '')}
									on:input={(e) => { id = e.currentTarget.value; }}
									disabled={edit}
									required
								/>
							</div>

							{#if preset}
								<div class="mb-1">
									<label class="text-xs font-medium mb-1.5 text-gray-500 dark:text-gray-400 block">
										{$i18n.t('Base Model (From)')}
									</label>
									<select
										class="text-sm w-full bg-transparent border border-gray-200 dark:border-gray-700 rounded-lg px-3 py-1.5 outline-hidden focus:border-gray-400 dark:focus:border-gray-500 transition"
										placeholder={$i18n.t('Select a base model (e.g. llama3, gpt-4o)')}
										bind:value={baseModelId}
										required
									>
										<option value={null} class="text-gray-900"
											>{$i18n.t('Select a base model')}</option
										>
										{#each $models.filter((m) => (model ? m.id !== model.id : true) && !m?.preset && m?.owned_by !== 'arena' && !(m?.direct ?? false)) as model}
											<option value={model.id} class="text-gray-900">{model.name}</option>
										{/each}
									</select>
								</div>
							{/if}

							<div class="mt-3 mb-1">
								<label class="text-xs font-medium text-gray-500 dark:text-gray-400 block mb-1">
									Descrição
								</label>
								<Textarea
									className="text-sm w-full pr-6 bg-transparent outline-hidden resize-none overflow-y-hidden"
									placeholder={$i18n.t('Add a short description about what this model does')}
									spellcheck={false}
									bind:value={description}
								/>
							</div>
						</div>
					</div>

				</div>

				<!-- Params (scrollable) + Features (static) side by side -->
				<div class="flex-1 min-h-0 overflow-hidden px-4 pb-6 border-t border-gray-200/30 dark:border-gray-700/20 mt-2 pt-9.5">
					<div class="flex gap-0 w-full pl-8 h-full min-h-0">
						<!-- Left: Parâmetros Avançados + System Prompt (only this scrolls) -->
						<div class="w-[55%] min-w-0 h-full flex flex-col pr-1">
							<div class="text-xs font-semibold text-gray-500 dark:text-gray-400 mb-2 py-0 pl-2 pr-5 shrink-0">
								{$i18n.t('Parâmetros Avançados')}
							</div>
							<div class="flex-1 min-h-0 overflow-y-auto pr-5" on:scroll={() => tippyHideAll()}>
								<div class="model-editor-advanced-params">
									<AdvancedParams admin={true} custom={true} janStyle={true} bind:params tooltipsEnabled={false} />
								</div>

							<!-- System Prompt -->
											<div class="mt-0.5">
								<div class="flex w-full items-center justify-between py-1">
									{#if showSystemPromptField}
										<button
											type="button"
											class="ml-2 text-xs text-gray-700 dark:text-gray-300 underline decoration-dotted cursor-pointer hover:text-gray-500 dark:hover:text-gray-400 transition"
											on:click={() => { system = ''; showSystemPromptField = false; }}
										>{$i18n.t('System Prompt')}</button>
									{:else}
										<div class="ml-2 text-xs text-gray-700 dark:text-gray-300">{$i18n.t('System Prompt')}</div>
									{/if}
									{#if !showSystemPromptField}
										<button
											type="button"
											class="text-xs text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300 transition px-2 py-0.5 rounded-md border border-gray-200 dark:border-gray-700"
											on:click={() => { showSystemPromptField = true; }}
										>{$i18n.t('Default')}</button>
									{/if}
								</div>
								{#if showSystemPromptField}
									<Textarea
										className="text-xs w-full bg-transparent border border-gray-200/40 dark:border-gray-700/30 rounded-lg px-3 py-2 outline-hidden resize-none overflow-y-auto focus:border-gray-300 dark:focus:border-gray-600 transition min-h-[5rem]"
										placeholder={$i18n.t('Digite o prompt do sistema')}
										rows={4}
										bind:value={system}
									/>
								{/if}
							</div>
							</div>
						</div>

						<!-- Right: Funcionalidades (static, does not scroll) -->
						<div class="border-l border-gray-300/50 dark:border-gray-600/30"></div>
						<div class="w-[45%] min-w-0 pl-6 h-full overflow-hidden">
							<div class="text-xs font-semibold text-gray-500 dark:text-gray-400 mb-2">
								{$i18n.t('Funcionalidades')}
							</div>
							<DefaultFeatures availableFeatures={['web_search', 'code_interpreter', 'code_execution', 'toggle_reasoning']} bind:featureIds={defaultFeatureIds} tooltipsEnabled={false} />
						</div>
					</div>
				</div>


			</form>
		{/if}
	</div>

	</div><!-- end layout wrapper -->
{/if}

<style>
	.model-editor-advanced-params :global(.inline-tooltip) {
		margin-left: 0.5rem;
	}
</style>
