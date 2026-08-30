<script lang="ts">
	import { DropdownMenu } from 'bits-ui';
	import { getContext, onMount, tick } from 'svelte';
	import { fly, fade } from 'svelte/transition';

	import { config, user, tools as _tools, mobile, toolServers } from '$lib/stores';

	import { getOAuthClientAuthorizationUrl } from '$lib/apis/configs';
	import { getTools } from '$lib/apis/tools';

	import Dropdown from '$lib/components/common/Dropdown.svelte';
	import Switch from '$lib/components/common/Switch.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import DocumentArrowUp from '$lib/components/icons/DocumentArrowUp.svelte';
	import Note from '$lib/components/icons/Note.svelte';
	import Clip from '$lib/components/icons/Clip.svelte';
	import ChatBubbleOval from '$lib/components/icons/ChatBubbleOval.svelte';
	import Refresh from '$lib/components/icons/Refresh.svelte';
	import Agile from '$lib/components/icons/Agile.svelte';
	import ChevronRight from '$lib/components/icons/ChevronRight.svelte';
	import ChevronLeft from '$lib/components/icons/ChevronLeft.svelte';
	import PageEdit from '$lib/components/icons/PageEdit.svelte';
	import Knobs from '$lib/components/icons/Knobs.svelte';
	import Wrench from '$lib/components/icons/Wrench.svelte';
	import Sparkles from '$lib/components/icons/Sparkles.svelte';
	import GlobeAlt from '$lib/components/icons/GlobeAlt.svelte';
	import Atom02 from '$lib/components/icons/Atom02.svelte';
	import Photo from '$lib/components/icons/Photo.svelte';
	import ImageIcon from '$lib/components/icons/Image.svelte';
	import MusicNote from '$lib/components/icons/MusicNote.svelte';
	import CheckCircle from '$lib/components/icons/CheckCircle.svelte';
	import Spinner from '$lib/components/common/Spinner.svelte';
	import Notes from './InputMenu/Notes.svelte';

	import { createPicker } from '$lib/utils/google-drive-picker';
	import { setFileGenerationPreference } from '$lib/utils/fileGenerationPreference';

	const i18n = getContext('i18n');

	export let files = [];

	export let selectedModels: string[] = [];
	export let fileUploadCapableModels: string[] = [];

	export let uploadFilesHandler: Function;
	export let inputFilesHandler: Function;

	export let uploadGoogleDriveHandler: Function;
	export let uploadOneDriveHandler: Function;

	export let onUpload: Function;
	export let onClose: Function;

	// Integration props
	export let selectedToolIds: string[] = [];
	export let toggleFilters: { id: string; name: string; description?: string; icon?: string }[] = [];
	export let selectedFilterIds: string[] = [];
	export let showWebSearchButton = false;
	export let webSearchEnabled = false;
	export let deepSearchEnabled = false;
	export let showImageGenerationButton = false;
	export let imageGenerationEnabled = false;
	export let showCodeExecutionButton = false;
	export let codeExecutionEnabled = false;
	export let showFileGenerationButton = true;
	export let fileGenerationEnabled = false;
	export let showStableDiffusionButton = false;
	export let stableDiffusionEnabled = false;
	export let showMusicGenerationButton = false;
	export let musicGenerationEnabled = false;
	export let onShowValves: Function = () => {};

	let show = false;
	let tab = '';
	let tools = null;
	$: fileGenerationBlocked =
		deepSearchEnabled ||
		imageGenerationEnabled ||
		stableDiffusionEnabled ||
		musicGenerationEnabled;
	$: effectiveFileGenerationEnabled = fileGenerationEnabled && !fileGenerationBlocked;

	$: if (show) {
		initTools();
	}

	const initTools = async () => {
		if ($_tools === null) {
			await _tools.set(await getTools(localStorage.token));
		}
		if ($_tools) {
			tools = $_tools.reduce((a, tool) => {
				a[tool.id] = {
					name: tool.name,
					description: tool.meta.description,
					enabled: selectedToolIds.includes(tool.id),
					...tool
				};
				return a;
			}, {});
		}
		if ($toolServers) {
			for (const serverIdx in $toolServers) {
				const server = $toolServers[serverIdx];
				if (server.info) {
					tools[`direct_server:${serverIdx}`] = {
						name: server?.info?.title ?? server.url,
						description: server.info.description ?? '',
						enabled: selectedToolIds.includes(`direct_server:${serverIdx}`)
					};
				}
			}
		}
		selectedToolIds = selectedToolIds.filter((id) => tools && Object.keys(tools).includes(id));
	};

	type IntegrationId =
		| 'web_search'
		| 'deep_search'
		| 'image_generation'
		| 'code_execution'
		| 'stable_diffusion'
		| 'music_generation';

	const clearNativeIntegrations = () => {
		webSearchEnabled = false;
		deepSearchEnabled = false;
		imageGenerationEnabled = false;
		codeExecutionEnabled = false;
		stableDiffusionEnabled = false;
		musicGenerationEnabled = false;
	};

	const closeIntegrationsMenu = () => {
		tab = '';
		show = false;
	};

	const integrationOptionClass = (enabled: boolean) =>
		enabled
			? 'bg-gray-100 hover:bg-gray-100 dark:bg-gray-800/70 dark:hover:bg-gray-800/70'
			: 'hover:bg-gray-50 dark:hover:bg-gray-800/50';

	const isNativeIntegrationEnabled = (integration: IntegrationId) => {
		switch (integration) {
			case 'web_search':
				return webSearchEnabled;
			case 'deep_search':
				return deepSearchEnabled;
			case 'image_generation':
				return imageGenerationEnabled;
			case 'code_execution':
				return codeExecutionEnabled;
			case 'stable_diffusion':
				return stableDiffusionEnabled;
			case 'music_generation':
				return musicGenerationEnabled;
		}
	};

	const toggleNativeIntegration = (integration: IntegrationId) => {
		const enable = !isNativeIntegrationEnabled(integration);
		clearNativeIntegrations();
		selectedToolIds = [];
		selectedFilterIds = [];

		if (!enable) {
			closeIntegrationsMenu();
			return;
		}

		switch (integration) {
			case 'web_search':
				webSearchEnabled = true;
				break;
			case 'deep_search':
				deepSearchEnabled = true;
				break;
			case 'image_generation':
				imageGenerationEnabled = true;
				break;
			case 'code_execution':
				codeExecutionEnabled = true;
				break;
			case 'stable_diffusion':
				stableDiffusionEnabled = true;
				break;
			case 'music_generation':
				musicGenerationEnabled = true;
				break;
		}

		closeIntegrationsMenu();
	};

	const selectFilter = (filterId: string) => {
		if (selectedFilterIds.includes(filterId)) {
			selectedFilterIds = [];
			closeIntegrationsMenu();
			return;
		}

		clearNativeIntegrations();
		selectedToolIds = [];
		selectedFilterIds = [filterId];
		closeIntegrationsMenu();
	};

	const selectTool = (toolId: string) => {
		if (selectedToolIds.includes(toolId)) {
			selectedToolIds = [];
			closeIntegrationsMenu();
			return;
		}

		clearNativeIntegrations();
		selectedFilterIds = [];
		selectedToolIds = [toolId];
		closeIntegrationsMenu();
	};

	let fileUploadEnabled = true;
	$: fileUploadEnabled =
		fileUploadCapableModels.length === selectedModels.length &&
		($user?.role === 'admin' || $user?.permissions?.chat?.file_upload);

	$: if (!fileUploadEnabled && files.length > 0) {
		files = [];
	}

	const handleFileChange = (event) => {
		const inputFiles = Array.from(event.target?.files);
		if (inputFiles && inputFiles.length > 0) {
			console.log(inputFiles);
			inputFilesHandler(inputFiles);
		}
	};

	const onSelect = (item) => {
		if (files.find((f) => f.id === item.id)) {
			return;
		}
		files = [
			...files,
			{
				...item,
				status: 'processed'
			}
		];

		show = false;
	};
</script>

<Dropdown
	bind:show
	on:change={(e) => {
		if (e.detail === false) {
			onClose();
		}
	}}
>
	<Tooltip content={$i18n.t('More')}>
		<slot />
	</Tooltip>

	<div slot="content">
		<DropdownMenu.Content
			class="w-full max-w-[255px] rounded-md px-1 py-1 border border-gray-100 dark:border-gray-800 z-50 bg-white dark:bg-gray-850 dark:text-white shadow-md max-h-72 overflow-y-auto overflow-x-hidden scrollbar-thin"
			style="font-family: 'Segoe UI', sans-serif;"
			sideOffset={4}
			alignOffset={8}
			side="bottom"
			align="start"
			transition={(e) => fade(e, { duration: 100 })}
		>
			{#if tab === ''}
				<div in:fly={{ x: -20, duration: 150 }}>
					<Tooltip
						content={fileUploadCapableModels.length !== selectedModels.length
							? $i18n.t('Model(s) do not support file upload')
							: !fileUploadEnabled
								? $i18n.t('You do not have permission to upload files.')
								: ''}
						className="w-full"
					>
						<DropdownMenu.Item
							class="flex gap-2 items-center px-3 py-1.5 text-sm select-none cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800/50 rounded-sm {!fileUploadEnabled
								? 'opacity-50'
								: ''}"
							on:click={() => {
								if (fileUploadEnabled) {
									uploadFilesHandler();
								}
							}}
						>
							<Clip />

						<div class="line-clamp-1 -ml-0.5">{$i18n.t('Upload Files')}</div>
						</DropdownMenu.Item>
					</Tooltip>

				{#if $config?.features?.enable_notes ?? false}
						<Tooltip
							content={fileUploadCapableModels.length !== selectedModels.length
								? $i18n.t('Model(s) do not support file upload')
								: !fileUploadEnabled
									? $i18n.t('You do not have permission to upload files.')
									: ''}
							className="w-full"
						>
							<button
								class="flex gap-2 w-full items-center px-3 py-1.5 text-sm select-none cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800/50 rounded-sm {!fileUploadEnabled
									? 'opacity-50'
									: ''}"
								on:click={() => {
									tab = 'notes';
								}}
							>
								<PageEdit />

								<div class="flex items-center w-full justify-between">
									<div class=" line-clamp-1">
										{$i18n.t('Attach Notes')}
									</div>

									<div class="text-gray-500">
										<ChevronRight />
									</div>
								</div>
							</button>
						</Tooltip>
					{/if}

					{#if fileUploadEnabled}
						{#if $config?.features?.enable_google_drive_integration}
							<DropdownMenu.Item
								class="flex gap-2 items-center px-3 py-1.5 text-sm select-none cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800/50 rounded-sm"
								on:click={() => {
									uploadGoogleDriveHandler();
								}}
							>
								<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 87.3 78" class="w-4">
									<path
										d="m6.6 66.85 3.85 6.65c.8 1.4 1.95 2.5 3.3 3.3l13.75-23.8h-27.5c0 1.55.4 3.1 1.2 4.5z"
										fill="#0066da"
									/>
									<path
										d="m43.65 25-13.75-23.8c-1.35.8-2.5 1.9-3.3 3.3l-25.4 44a9.06 9.06 0 0 0 -1.2 4.5h27.5z"
										fill="#00ac47"
									/>
									<path
										d="m73.55 76.8c1.35-.8 2.5-1.9 3.3-3.3l1.6-2.75 7.65-13.25c.8-1.4 1.2-2.95 1.2-4.5h-27.502l5.852 11.5z"
										fill="#ea4335"
									/>
									<path
										d="m43.65 25 13.75-23.8c-1.35-.8-2.9-1.2-4.5-1.2h-18.5c-1.6 0-3.15.45-4.5 1.2z"
										fill="#00832d"
									/>
									<path
										d="m59.8 53h-32.3l-13.75 23.8c1.35.8 2.9 1.2 4.5 1.2h50.8c1.6 0 3.15-.45 4.5-1.2z"
										fill="#2684fc"
									/>
									<path
										d="m73.4 26.5-12.7-22c-.8-1.4-1.95-2.5-3.3-3.3l-13.75 23.8 16.15 28h27.45c0-1.55-.4-3.1-1.2-4.5z"
										fill="#ffba00"
									/>
								</svg>
								<div class="line-clamp-1">{$i18n.t('Google Drive')}</div>
							</DropdownMenu.Item>
						{/if}

						{#if $config?.features?.enable_onedrive_integration && ($config?.features?.enable_onedrive_personal || $config?.features?.enable_onedrive_business)}
							<button
								class="flex gap-2 w-full items-center px-3 py-1.5 text-sm select-none cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800/50 rounded-sm {!fileUploadEnabled
									? 'opacity-50'
									: ''}"
								on:click={() => {
									tab = 'microsoft_onedrive';
								}}
							>
								<svg
									xmlns="http://www.w3.org/2000/svg"
									viewBox="0 0 32 32"
									class="size-4"
									fill="none"
								>
									<mask
										id="mask0_87_7796"
										style="mask-type:alpha"
										maskUnits="userSpaceOnUse"
										x="0"
										y="6"
										width="32"
										height="20"
									>
										<path
											d="M7.82979 26C3.50549 26 0 22.5675 0 18.3333C0 14.1921 3.35322 10.8179 7.54613 10.6716C9.27535 7.87166 12.4144 6 16 6C20.6308 6 24.5169 9.12183 25.5829 13.3335C29.1316 13.3603 32 16.1855 32 19.6667C32 23.0527 29 26 25.8723 25.9914L7.82979 26Z"
											fill="#C4C4C4"
										/>
									</mask>
									<g mask="url(#mask0_87_7796)">
										<path
											d="M7.83017 26.0001C5.37824 26.0001 3.18957 24.8966 1.75391 23.1691L18.0429 16.3335L30.7089 23.4647C29.5926 24.9211 27.9066 26.0001 26.0004 25.9915C23.1254 26.0001 12.0629 26.0001 7.83017 26.0001Z"
											fill="url(#paint0_linear_87_7796)"
										/>
										<path
											d="M25.5785 13.3149L18.043 16.3334L30.709 23.4647C31.5199 22.4065 32.0004 21.0916 32.0004 19.6669C32.0004 16.1857 29.1321 13.3605 25.5833 13.3337C25.5817 13.3274 25.5801 13.3212 25.5785 13.3149Z"
											fill="url(#paint1_linear_87_7796)"
										/>
										<path
											d="M7.06445 10.7028L18.0423 16.3333L25.5779 13.3148C24.5051 9.11261 20.6237 6 15.9997 6C12.4141 6 9.27508 7.87166 7.54586 10.6716C7.3841 10.6773 7.22358 10.6877 7.06445 10.7028Z"
											fill="url(#paint2_linear_87_7796)"
										/>
										<path
											d="M1.7535 23.1687L18.0425 16.3331L7.06471 10.7026C3.09947 11.0792 0 14.3517 0 18.3331C0 20.1665 0.657197 21.8495 1.7535 23.1687Z"
											fill="url(#paint3_linear_87_7796)"
										/>
									</g>
									<defs>
										<linearGradient
											id="paint0_linear_87_7796"
											x1="4.42591"
											y1="24.6668"
											x2="27.2309"
											y2="23.2764"
											gradientUnits="userSpaceOnUse"
										>
											<stop stop-color="#2086B8" />
											<stop offset="1" stop-color="#46D3F6" />
										</linearGradient>
										<linearGradient
											id="paint1_linear_87_7796"
											x1="23.8302"
											y1="19.6668"
											x2="30.2108"
											y2="15.2082"
											gradientUnits="userSpaceOnUse"
										>
											<stop stop-color="#1694DB" />
											<stop offset="1" stop-color="#62C3FE" />
										</linearGradient>
										<linearGradient
											id="paint2_linear_87_7796"
											x1="8.51037"
											y1="7.33333"
											x2="23.3335"
											y2="15.9348"
											gradientUnits="userSpaceOnUse"
										>
											<stop stop-color="#0D3D78" />
											<stop offset="1" stop-color="#063B83" />
										</linearGradient>
										<linearGradient
											id="paint3_linear_87_7796"
											x1="-0.340429"
											y1="19.9998"
											x2="14.5634"
											y2="14.4649"
											gradientUnits="userSpaceOnUse"
										>
											<stop stop-color="#16589B" />
											<stop offset="1" stop-color="#1464B7" />
										</linearGradient>
									</defs>
								</svg>

								<div class="flex items-center w-full justify-between">
									<div class=" line-clamp-1">
										{$i18n.t('Microsoft OneDrive')}
									</div>

									<div class="text-gray-500">
										<ChevronRight />
									</div>
								</div>
							</button>
						{/if}
					{/if}

					{#if showWebSearchButton || showImageGenerationButton || showCodeExecutionButton || showFileGenerationButton || showStableDiffusionButton || showMusicGenerationButton || (toggleFilters && toggleFilters.length > 0) || (tools && Object.keys(tools).length > 0)}
						<hr class="my-1 border-gray-200 dark:border-gray-700 mx-auto w-[90%]" />
					{/if}

					{#if tools}
						{#if Object.keys(tools).length > 0}
							<button
								class="flex w-full justify-between gap-2 items-center px-3 py-1.5 text-sm cursor-pointer rounded-sm hover:bg-gray-50 dark:hover:bg-gray-800/50"
								on:click={() => { tab = 'tools'; }}
							>
								<Wrench />
								<div class="flex items-center w-full justify-between">
									<div class=" line-clamp-1">
										{$i18n.t('Tools')}
										<span class="ml-0.5 text-gray-500">{Object.keys(tools).length}</span>
									</div>
									<div class="text-gray-500"><ChevronRight /></div>
								</div>
							</button>
						{/if}
					{:else}
						<div class="py-2 flex justify-center"><Spinner /></div>
					{/if}

					{#if toggleFilters && toggleFilters.length > 0}
						{#each toggleFilters.sort((a, b) => a.name.localeCompare(b.name, undefined, { sensitivity: 'base' })) as filter (filter.id)}
							<Tooltip content={filter?.description} placement="top-start">
								<button
									class="flex w-full justify-between gap-2 items-center px-3 py-1.5 text-sm cursor-pointer rounded-sm {integrationOptionClass(selectedFilterIds.includes(filter.id))}"
									on:click={() => {
										selectFilter(filter.id);
									}}
								>
									<div class="flex-1 truncate">
										<div class="flex flex-1 gap-2 items-center">
											<div class="shrink-0">
												{#if filter?.icon}
													<div class="size-4 items-center flex justify-center">
														<img src={filter.icon} class="size-3.5 {filter.icon.includes('data:image/svg') ? 'dark:invert-[80%]' : ''}" style="fill: currentColor;" alt={filter.name} />
													</div>
												{:else}
													<Sparkles className="size-4" strokeWidth="1.75" />
												{/if}
											</div>
											<div class=" truncate">{filter?.name}</div>
										</div>
									</div>
									{#if filter?.has_user_valves && ($user?.role === 'admin' || ($user?.permissions?.chat?.valves ?? true))}
										<div class=" shrink-0">
											<Tooltip content={$i18n.t('Valves')}>
												<button class="self-center w-fit text-sm text-gray-600 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 transition rounded-full" type="button" on:click={(e) => { e.stopPropagation(); e.preventDefault(); onShowValves({ type: 'function', id: filter.id }); }}>
													<Knobs />
												</button>
											</Tooltip>
										</div>
									{/if}
									<div class="size-4 shrink-0">
										{#if selectedFilterIds.includes(filter.id)}<CheckCircle strokeWidth="1.7" />{/if}
									</div>
								</button>
							</Tooltip>
						{/each}
					{/if}

					{#if showWebSearchButton}
						<Tooltip content="" placement="top-start">
							<button class="my-px flex w-full justify-between gap-2 items-center px-3 py-1.5 text-sm cursor-pointer rounded-sm {integrationOptionClass(webSearchEnabled)}" aria-pressed={webSearchEnabled} on:click={() => toggleNativeIntegration('web_search')}>
								<div class="flex-1 truncate">
									<div class="flex flex-1 gap-2 items-center">
										<div class="shrink-0"><GlobeAlt /></div>
										<div class=" truncate">{$i18n.t('Web Search')}</div>
									</div>
								</div>
								<div class="size-4 shrink-0">{#if webSearchEnabled}<CheckCircle strokeWidth="1.7" />{/if}</div>
							</button>
						</Tooltip>
					{/if}

					{#if showImageGenerationButton}
						<Tooltip content="" placement="top-start">
							<button class="my-px flex w-full justify-between gap-2 items-center px-3 py-1.5 text-sm cursor-pointer rounded-sm {integrationOptionClass(imageGenerationEnabled)}" aria-pressed={imageGenerationEnabled} on:click={() => toggleNativeIntegration('image_generation')}>
								<div class="flex-1 truncate">
									<div class="flex flex-1 gap-2 items-center">
										<div class="shrink-0"><Photo className="size-4" strokeWidth="1.5" /></div>
										<div class=" truncate">{$i18n.t('Image')}</div>
									</div>
								</div>
								<div class="size-4 shrink-0">{#if imageGenerationEnabled}<CheckCircle strokeWidth="1.7" />{/if}</div>
							</button>
						</Tooltip>
					{/if}

					{#if showWebSearchButton}
						<Tooltip content="" placement="top-start">
							<button class="my-px flex w-full justify-between gap-2 items-center px-3 py-1.5 text-sm cursor-pointer rounded-sm {integrationOptionClass(deepSearchEnabled)}" aria-pressed={deepSearchEnabled} on:click={() => toggleNativeIntegration('deep_search')}>
								<div class="flex-1 truncate">
									<div class="flex flex-1 gap-2 items-center">
										<div class="shrink-0"><Atom02 /></div>
										<div class=" truncate">{$i18n.t('Deep Search')}</div>
									</div>
								</div>
								<div class="size-4 shrink-0">{#if deepSearchEnabled}<CheckCircle strokeWidth="1.7" />{/if}</div>
							</button>
						</Tooltip>
					{/if}

					{#if showCodeExecutionButton}
						<Tooltip content="" placement="top-start">
							<button class="my-px flex w-full justify-between gap-2 items-center px-3 py-1.5 text-sm cursor-pointer rounded-sm {integrationOptionClass(codeExecutionEnabled)}" aria-pressed={codeExecutionEnabled} on:click={() => toggleNativeIntegration('code_execution')}>
								<div class="flex-1 truncate">
									<div class="flex flex-1 gap-2 items-center">
										<div class="shrink-0">
											<svg aria-hidden="true" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5" class="size-4">
												<path stroke-linecap="round" stroke-linejoin="round" d="m21 7.5-9-5.25L3 7.5m18 0-9 5.25m9-5.25v9l-9 5.25M3 7.5l9 5.25M3 7.5v9l9 5.25m0-9v9"/>
											</svg>
										</div>
										<div class=" truncate">{$i18n.t('Code Execution')}</div>
									</div>
								</div>
								<div class="size-4 shrink-0">{#if codeExecutionEnabled}<CheckCircle strokeWidth="1.7" />{/if}</div>
							</button>
						</Tooltip>
					{/if}

					{#if showStableDiffusionButton}
						<hr class="my-1 border-gray-200 dark:border-gray-800 mx-auto w-[90%]" />
					{/if}

					{#if showStableDiffusionButton}
						<Tooltip content="" placement="top-start">
							<button class="my-px flex w-full justify-between gap-2 items-center px-3 py-1.5 text-sm cursor-pointer rounded-sm {integrationOptionClass(stableDiffusionEnabled)}" aria-pressed={stableDiffusionEnabled} on:click={() => toggleNativeIntegration('stable_diffusion')}>
								<div class="flex-1 truncate">
									<div class="flex flex-1 gap-2 items-center">
										<div class="shrink-0">
											<ImageIcon className="size-4" strokeWidth="1.5" />
										</div>
										<div class=" truncate">{$i18n.t('Criar imagem')}</div>
									</div>
								</div>
								<div class="size-4 shrink-0">{#if stableDiffusionEnabled}<CheckCircle strokeWidth="1.7" />{/if}</div>
							</button>
						</Tooltip>
					{/if}

					{#if showMusicGenerationButton}
						<Tooltip content="" placement="top-start">
							<button class="my-px flex w-full justify-between gap-2 items-center px-3 py-1.5 text-sm cursor-pointer rounded-sm {integrationOptionClass(musicGenerationEnabled)}" aria-pressed={musicGenerationEnabled} on:click={() => toggleNativeIntegration('music_generation')}>
								<div class="flex-1 truncate">
									<div class="flex flex-1 gap-2 items-center">
										<div class="shrink-0">
											<MusicNote className="size-4" strokeWidth="1.5" />
										</div>
										<div class="truncate">{$i18n.t('Criar música')}</div>
									</div>
								</div>
								<div class="size-4 shrink-0">{#if musicGenerationEnabled}<CheckCircle strokeWidth="1.7" />{/if}</div>
							</button>
						</Tooltip>
					{/if}

					{#if showFileGenerationButton}
						<hr class="my-1 border-gray-200 dark:border-gray-800 mx-auto w-[90%]" />
						<Tooltip content="" placement="top-start">
							<button
								type="button"
								class="my-px flex w-full justify-between gap-2 items-center px-3 py-1.5 text-sm rounded-sm transition {fileGenerationBlocked
									? 'cursor-not-allowed text-gray-400 dark:text-gray-600'
									: 'cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800/50'}"
								aria-pressed={effectiveFileGenerationEnabled}
								aria-disabled={fileGenerationBlocked}
								disabled={fileGenerationBlocked}
								on:click|stopPropagation={() => {
									fileGenerationEnabled = !fileGenerationEnabled;
									setFileGenerationPreference(fileGenerationEnabled);
								}}
							>
								<div class="flex min-w-0 flex-1 items-center gap-2">
									<div class="shrink-0">
										<svg
											aria-hidden="true"
											xmlns="http://www.w3.org/2000/svg"
											viewBox="0 0 24 24"
											fill="none"
											stroke="currentColor"
											stroke-width="2"
											stroke-linecap="round"
											stroke-linejoin="round"
											class="size-4"
										>
											<rect width="18" height="18" x="3" y="3" rx="2" />
											<path d="M3 9h18" />
											<path d="M9 21V9" />
										</svg>
									</div>
									<div class="truncate">Ferramentas</div>
								</div>
								<div class="pointer-events-none shrink-0">
									<Switch
										state={effectiveFileGenerationEnabled}
										disabled={fileGenerationBlocked}
									/>
								</div>
							</button>
						</Tooltip>
					{/if}
				</div>
			{:else if tab === 'tools' && tools}
				<div in:fly={{ x: 20, duration: 150 }}>
					<button
						class="flex w-full justify-between gap-2 items-center px-3 py-1.5 text-sm cursor-pointer rounded-sm hover:bg-gray-50 dark:hover:bg-gray-800/50"
						on:click={() => { tab = ''; }}
					>
						<ChevronLeft />
						<div class="flex items-center w-full justify-between">
							<div>{$i18n.t('Tools')} <span class="ml-0.5 text-gray-500">{Object.keys(tools).length}</span></div>
						</div>
					</button>
					{#each Object.keys(tools) as toolId}
						<button
							class="relative flex w-full justify-between gap-2 items-center px-3 py-1.5 text-sm cursor-pointer rounded-sm {integrationOptionClass(selectedToolIds.includes(toolId))}"
							on:click={async (e) => {
								if (!(tools[toolId]?.authenticated ?? true)) {
									e.preventDefault();
									let parts = toolId.split(':');
									let serverId = parts?.at(-1) ?? toolId;
									const authUrl = getOAuthClientAuthorizationUrl(serverId, 'mcp');
									window.open(authUrl, '_self', 'noopener');
								} else {
									selectTool(toolId);
									await tick();
								}
							}}
						>
							{#if !(tools[toolId]?.authenticated ?? true)}
								<div class="absolute inset-0 opacity-50 rounded-sm cursor-pointer z-10" />
							{/if}
							<div class="flex-1 truncate">
								<div class="flex flex-1 gap-2 items-center">
									<Tooltip content={tools[toolId]?.name ?? ''} placement="top">
										<div class="shrink-0"><Wrench /></div>
									</Tooltip>
									<Tooltip content={tools[toolId]?.description ?? ''} placement="top-start">
										<div class=" truncate">{tools[toolId].name}</div>
									</Tooltip>
								</div>
							</div>
							{#if tools[toolId]?.has_user_valves && ($user?.role === 'admin' || ($user?.permissions?.chat?.valves ?? true))}
								<div class=" shrink-0">
									<Tooltip content={$i18n.t('Valves')}>
										<button class="self-center w-fit text-sm text-gray-600 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 transition rounded-full" type="button" on:click={(e) => { e.stopPropagation(); e.preventDefault(); onShowValves({ type: 'tool', id: toolId }); }}>
											<Knobs />
										</button>
									</Tooltip>
								</div>
							{/if}
							<div class="size-4 shrink-0">
								{#if selectedToolIds.includes(toolId)}<CheckCircle strokeWidth="1.7" />{/if}
							</div>
						</button>
					{/each}
				</div>
			{:else if tab === 'notes'}
				<div in:fly={{ x: 20, duration: 150 }}>
					<button
						class="flex w-full justify-between gap-2 items-center px-3 py-1.5 text-sm select-none cursor-pointer rounded-sm hover:bg-gray-50 dark:hover:bg-gray-800/50"
						on:click={() => {
							tab = '';
						}}
					>
						<ChevronLeft />

						<div class="flex items-center w-full justify-between">
							<div>
								{$i18n.t('Notes')}
							</div>
						</div>
					</button>

					<Notes {onSelect} />
				</div>
			{:else if tab === 'microsoft_onedrive'}
				<div in:fly={{ x: 20, duration: 150 }}>
					<button
						class="flex w-full justify-between gap-2 items-center px-3 py-1.5 text-sm select-none cursor-pointer rounded-sm hover:bg-gray-50 dark:hover:bg-gray-800/50"
						on:click={() => {
							tab = '';
						}}
					>
						<ChevronLeft />

						<div class="flex items-center w-full justify-between">
							<div>
								{$i18n.t('Microsoft OneDrive')}
							</div>
						</div>
					</button>

					{#if $config?.features?.enable_onedrive_personal}
						<DropdownMenu.Item
							class="flex gap-2 items-center px-3 py-1.5 text-sm select-none cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800/50 rounded-sm text-left"
							on:click={() => {
								uploadOneDriveHandler('personal');
							}}
						>
							<div class="flex flex-col">
								<div class="line-clamp-1">{$i18n.t('Microsoft OneDrive (personal)')}</div>
							</div>
						</DropdownMenu.Item>
					{/if}

					{#if $config?.features?.enable_onedrive_business}
						<DropdownMenu.Item
							class="flex gap-2 items-center px-3 py-1.5 text-sm select-none cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800/50 rounded-sm text-left"
							on:click={() => {
								uploadOneDriveHandler('organizations');
							}}
						>
							<div class="flex flex-col">
								<div class="line-clamp-1">
									{$i18n.t('Microsoft OneDrive (work/school)')}
								</div>
								<div class="text-xs text-gray-500">{$i18n.t('Includes SharePoint')}</div>
							</div>
						</DropdownMenu.Item>
					{/if}
				</div>
			{/if}
		</DropdownMenu.Content>
	</div>
</Dropdown>
