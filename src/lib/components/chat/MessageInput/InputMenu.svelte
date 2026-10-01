<script lang="ts">
	import { DropdownMenu } from 'bits-ui';
	import { getContext, onMount, tick } from 'svelte';
	import { fly, fade } from 'svelte/transition';

	import { user, tools as _tools, mobile, toolServers } from '$lib/stores';

	import { getOAuthClientAuthorizationUrl } from '$lib/apis/configs';
	import { getTools } from '$lib/apis/tools';

	import Dropdown from '$lib/components/common/Dropdown.svelte';
	import Switch from '$lib/components/common/Switch.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import Clip from '$lib/components/icons/Clip.svelte';
	import ChevronRight from '$lib/components/icons/ChevronRight.svelte';
	import ChevronLeft from '$lib/components/icons/ChevronLeft.svelte';
	import Knobs from '$lib/components/icons/Knobs.svelte';
	import Wrench from '$lib/components/icons/Wrench.svelte';
	import GlobeAlt from '$lib/components/icons/GlobeAlt.svelte';
	import Atom02 from '$lib/components/icons/Atom02.svelte';
	import ImageIcon from '$lib/components/icons/Image.svelte';
	import MusicNote from '$lib/components/icons/MusicNote.svelte';
	import Video from '$lib/components/icons/Video.svelte';
	import CheckCircle from '$lib/components/icons/CheckCircle.svelte';
	import Spinner from '$lib/components/common/Spinner.svelte';

	import { setFileGenerationPreference } from '$lib/utils/fileGenerationPreference';
	import type { MediaAttachmentPolicy } from '$lib/utils/mediaAttachmentPolicy';

	const i18n = getContext('i18n');

	export let files = [];
	export let mediaAttachmentPolicy: MediaAttachmentPolicy | null = null;

	export let selectedModels: string[] = [];
	export let fileUploadCapableModels: string[] = [];

	export let uploadFilesHandler: Function;
	export let inputFilesHandler: Function;

	export let onUpload: Function;
	export let onClose: Function;

	// Integration props
	export let selectedToolIds: string[] = [];
	export let showWebSearchButton = false;
	export let webSearchEnabled = false;
	export let deepSearchEnabled = false;
	export let showCodeExecutionButton = false;
	export let codeExecutionEnabled = false;
	export let showFileGenerationButton = true;
	export let fileGenerationEnabled = false;
	export let showStableDiffusionButton = false;
	export let stableDiffusionEnabled = false;
	export let showMusicGenerationButton = false;
	export let musicGenerationEnabled = false;
	export let showVideoGenerationButton = false;
	export let videoGenerationEnabled = false;
	export let onNativeIntegrationChange: Function = () => {};
	export let onShowValves: Function = () => {};

	let show = false;
	let tab = '';
	let tools = null;
	$: fileGenerationBlocked =
		deepSearchEnabled ||
		stableDiffusionEnabled ||
		musicGenerationEnabled ||
		videoGenerationEnabled;
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
		| 'code_execution'
		| 'stable_diffusion'
		| 'music_generation'
		| 'video_generation';

	const clearNativeIntegrations = () => {
		webSearchEnabled = false;
		deepSearchEnabled = false;
		codeExecutionEnabled = false;
		stableDiffusionEnabled = false;
		musicGenerationEnabled = false;
		videoGenerationEnabled = false;
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
			case 'code_execution':
				return codeExecutionEnabled;
			case 'stable_diffusion':
				return stableDiffusionEnabled;
			case 'music_generation':
				return musicGenerationEnabled;
			case 'video_generation':
				return videoGenerationEnabled;
		}
	};

	const toggleNativeIntegration = (integration: IntegrationId) => {
		const enable = !isNativeIntegrationEnabled(integration);
		clearNativeIntegrations();
		selectedToolIds = [];

		if (!enable) {
			onNativeIntegrationChange(null);
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
			case 'code_execution':
				codeExecutionEnabled = true;
				break;
			case 'stable_diffusion':
				stableDiffusionEnabled = true;
				break;
			case 'music_generation':
				musicGenerationEnabled = true;
				break;
			case 'video_generation':
				videoGenerationEnabled = true;
				break;
		}

		onNativeIntegrationChange(integration);
		closeIntegrationsMenu();
	};

	const selectTool = (toolId: string) => {
		if (selectedToolIds.includes(toolId)) {
			selectedToolIds = [];
			closeIntegrationsMenu();
			return;
		}

		clearNativeIntegrations();
		onNativeIntegrationChange(null);
		selectedToolIds = [toolId];
		closeIntegrationsMenu();
	};

	let fileUploadEnabled = true;
	$: fileUploadEnabled =
		(mediaAttachmentPolicy ? mediaAttachmentPolicy.maxCount > 0 : fileUploadCapableModels.length === selectedModels.length) &&
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
		if (mediaAttachmentPolicy) return;
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

<svelte:window
	on:resize={() => {
		show = false;
	}}
/>

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
			class="max-h-[calc(100dvh-16px)] overflow-x-hidden overflow-y-auto overscroll-contain rounded-md px-1 py-1 border border-gray-100 dark:border-gray-800 z-50 bg-white dark:bg-gray-850 dark:text-white shadow-md"
			style="font-family: 'Segoe UI', sans-serif; width: min(255px, calc(100vw - 16px)); max-width: 255px !important;"
			strategy="fixed"
			fitViewport={true}
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
								? $i18n.t('Este recurso não suporta anexos.')
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


					{#if showWebSearchButton || showCodeExecutionButton || showFileGenerationButton || showStableDiffusionButton || showMusicGenerationButton || showVideoGenerationButton || (tools && Object.keys(tools).length > 0)}
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
										<div class=" truncate">{$i18n.t('Artifacts')}</div>
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

					{#if showVideoGenerationButton}
						<Tooltip content="" placement="top-start">
							<button class="my-px flex w-full justify-between gap-2 items-center px-3 py-1.5 text-sm cursor-pointer rounded-sm {integrationOptionClass(videoGenerationEnabled)}" aria-pressed={videoGenerationEnabled} on:click={() => toggleNativeIntegration('video_generation')}>
								<div class="flex-1 truncate">
									<div class="flex flex-1 gap-2 items-center">
										<div class="shrink-0"><Video className="size-4" strokeWidth="1.5" /></div>
										<div class="truncate">{$i18n.t('Criar vídeo')}</div>
									</div>
								</div>
								<div class="size-4 shrink-0">{#if videoGenerationEnabled}<CheckCircle strokeWidth="1.7" />{/if}</div>
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
									<div class="truncate">{$i18n.t('Tools')}</div>
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

			{/if}
		</DropdownMenu.Content>
	</div>
</Dropdown>
