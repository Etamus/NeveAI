<script lang="ts">
	import { marked } from 'marked';

	import { getContext, createEventDispatcher } from 'svelte';
	import { fade } from 'svelte/transition';

	const dispatch = createEventDispatcher();

	import { getChatList } from '$lib/apis/chats';

	import { user, config, settings, models as _models, temporaryChatEnabled, selectedFolder, chats, currentChatPage } from '$lib/stores';
	import type { Model } from '$lib/stores';
	import { getUserFirstName } from '$lib/utils/user';

	import MessageInput from './MessageInput.svelte';
	import FolderPlaceholder from './Placeholder/FolderPlaceholder.svelte';
	import FolderTitle from './Placeholder/FolderTitle.svelte';
	import ImageIcon from '../icons/Image.svelte';
	import AcademicCap from '../icons/AcademicCap.svelte';
	import GlobeAlt from '../icons/GlobeAlt.svelte';
	import Video from '../icons/Video.svelte';
	import MusicNote from '../icons/MusicNote.svelte';
	import Cube from '../icons/Cube.svelte';
	import { integrationSuggestionUsage, loadIntegrationSuggestionUsage, getIntegrationSuggestions, type SuggestionIntegration } from '$lib/utils/integrationSuggestions';
	const suggestionOptions = {
		stable_diffusion: { label: 'Create an image', icon: ImageIcon },
		guided_learning: { label: 'Learn something new', icon: AcademicCap },
		web_search: { label: 'Search the web', icon: GlobeAlt },
		video_generation: { label: 'Create a video', icon: Video },
		music_generation: { label: 'Create music', icon: MusicNote },
		model3d_generation: { label: 'Create a 3D model', icon: Cube }
	};

	import type { I18nStore } from '$lib/i18n';
	const i18n = getContext<I18nStore>('i18n');

	export let createMessagePair: Function;
	export let stopResponse: Function;

	export let autoScroll = false;

	export let atSelectedModel: Model | undefined;
	export let selectedModels: string[] = [];

	export let history: any;

	export let prompt = '';
	export let files: any[] = [];
	export let messageInput = null;

	export let selectedToolIds: string[] = [];

	export let showCommands = false;

	export let learningEnabled = false;
	export let fileGenerationEnabled = false;
	export let webSearchEnabled = false;
	export let deepSearchEnabled = false;
	export let stableDiffusionEnabled = false;
	export let stableDiffusionQuality: 'qwen_image_2s' | 'qwen_image_2_1_official' = 'qwen_image_2s';
	export let stableDiffusionStyle: 'none' = 'none';
	export let stableDiffusionResolution: '1:1' | '16:9' | '9:16' | '4:3' | '3:4' = '1:1';
	export let stableDiffusionModeOptions: import('$lib/utils/imageModes').ImageModeOptions = { mode: 'normal' };
	export let musicGenerationEnabled = false;
	export let videoGenerationEnabled = false;
	export let model3dEnabled = false;
	import type { Model3dQuality } from '$lib/utils/model3dQuality';
	export let model3dQuality: Model3dQuality = 'standard';
	export let videoGenerationModel: import('$lib/utils/videoGeneration').VideoGenerationModel = 'vdn_h3';
	export let videoGenerationResolution: '480p' | '672p' = '480p';
	export let videoGenerationDuration: '5s' | '8s' = '5s';
	export let videoGenerationAspectRatio: '16:9' | '9:16' = '16:9';
	export let onNativeIntegrationChange: Function = () => {};
	export let thinkingEnabled = true;
	export let thinkingExtendedEnabled = true;
	export let thinkingUnlimitedEnabled = false;

	export let onUpload: Function = (e) => {};
	export let onSelect = (e) => {};
	export let onChange = (e) => {};

	export let sendDisabled = false;

	export let dragged = false;

	let models = [];
	let selectedModelIdx = 0;

	$: if (selectedModels.length > 0) {
		selectedModelIdx = models.length - 1;
	}

	$: models = selectedModels.map((id) => $_models.find((m) => m.id === id));
	$: userName = getUserFirstName($user?.name);
	$: loadIntegrationSuggestionUsage($user?.id);
	$: allowedSuggestions = [
		...($config?.features?.enable_stable_diffusion && ($user?.role === 'admin' || $user?.permissions?.features?.stable_diffusion) ? ['stable_diffusion'] : []),
		'guided_learning',
		...($user?.role === 'admin' || $user?.permissions?.features?.web_search ? ['web_search'] : []),
		...($config?.features?.enable_video_generation && ($user?.role === 'admin' || $user?.permissions?.features?.video_generation) ? ['video_generation'] : []),
		...($config?.features?.enable_music_generation && ($user?.role === 'admin' || $user?.permissions?.features?.music_generation) ? ['music_generation'] : []),
		...($config?.features?.enable_model3d_generation && $user?.role === 'admin' ? ['model3d_generation'] : [])
	] as SuggestionIntegration[];
	$: suggestedIntegrations = getIntegrationSuggestions($integrationSuggestionUsage[$user?.id ?? ''] ?? [], allowedSuggestions);
	$: showIntegrationSuggestions = ($settings?.enableSuggestions ?? true) && !$temporaryChatEnabled && !$selectedFolder && !webSearchEnabled && !deepSearchEnabled &&
		!learningEnabled && !stableDiffusionEnabled && !musicGenerationEnabled &&
		!videoGenerationEnabled && !model3dEnabled && selectedToolIds.length === 0;
	$: greeting = userName
		? $i18n.t('What would you like to explore today, {{name}}?', { name: userName })
		: $i18n.t('What would you like to explore today?');
</script>

<div class="chat-placeholder m-auto w-full max-w-6xl px-2 @2xl:px-20 -translate-y-20 py-24 text-center">
	<div
		class="w-full text-3xl text-gray-800 dark:text-gray-100 text-center flex items-center gap-4"
	>
		<div class="w-full flex flex-col justify-center items-center">
			{#if $selectedFolder}
				<FolderTitle
					folder={$selectedFolder}
					onUpdate={async (folder) => {
						currentChatPage.set(1);
						await chats.set(await getChatList(localStorage.token, 1));
					}}
					onDelete={async () => {
						await chats.set(await getChatList(localStorage.token, $currentChatPage));
						currentChatPage.set(1);

						selectedFolder.set(null);
					}}
				/>
			{:else}
				<div class="flex w-full max-w-full flex-col items-center justify-center px-5 mb-8">
					<div
						class="max-w-full break-words whitespace-normal sm:overflow-hidden sm:text-ellipsis sm:whitespace-nowrap pb-1 {$temporaryChatEnabled ? 'text-3xl' : 'text-[1.75rem]'} leading-[1.25]"
						in:fade={{ duration: 100 }}
					>
						{$temporaryChatEnabled
							? $i18n.t('Temporary Chat')
							: greeting}
					</div>
					{#if $temporaryChatEnabled}
						<div class="mt-2 text-sm font-normal text-gray-500 dark:text-gray-400" in:fade={{ duration: 100 }}>
							{$i18n.t("This chat won't appear in history and your messages will not be saved.")}
						</div>
					{/if}
				</div>


			{/if}

			<div class="relative text-base font-normal @md:max-w-2xl w-full py-3 {atSelectedModel ? 'mt-2' : ''}">
				<MessageInput
					bind:this={messageInput}
					{history}
					{selectedModels}
					bind:files
					bind:prompt
					bind:autoScroll
					bind:selectedToolIds
					bind:learningEnabled
					bind:fileGenerationEnabled
					bind:webSearchEnabled
					bind:deepSearchEnabled
					bind:stableDiffusionEnabled
					bind:stableDiffusionQuality
					bind:stableDiffusionStyle
					bind:stableDiffusionResolution
					bind:stableDiffusionModeOptions
					bind:musicGenerationEnabled
					bind:videoGenerationEnabled
					bind:model3dEnabled
					bind:model3dQuality
					bind:videoGenerationModel
					bind:videoGenerationResolution
					bind:videoGenerationDuration
					bind:videoGenerationAspectRatio
					{onNativeIntegrationChange}
					bind:thinkingEnabled
					bind:thinkingExtendedEnabled
					bind:thinkingUnlimitedEnabled
					bind:atSelectedModel
					bind:showCommands
					bind:dragged
					{stopResponse}
					{createMessagePair}
					{sendDisabled}
					placeholder={$i18n.t('How can I help you today?')}
					{onChange}
					{onUpload}
					on:submit={(e) => {
						dispatch('submit', e.detail);
					}}
				/>
				{#if showIntegrationSuggestions}
					<div data-new-chat-suggestions class="absolute inset-x-2.5 top-full mt-3 flex flex-col gap-1 text-left text-sm text-gray-500 dark:text-gray-400">
						{#each suggestedIntegrations as integration (integration)}
							<button type="button" data-suggest-integration={integration} class="suggestion-row grid min-h-11 w-full items-center gap-2 rounded-[10px] py-3 text-left hover:bg-gray-100/45 hover:text-gray-900 dark:hover:bg-gray-850/80 dark:hover:text-gray-100" on:click={() => onNativeIntegrationChange(integration)}>
								<svelte:component this={suggestionOptions[integration].icon} className="size-4 shrink-0 justify-self-center" strokeWidth={integration === 'guided_learning' ? '1.5' : '1.75'} /><span>{$i18n.t(suggestionOptions[integration].label)}</span>
							</button>
						{/each}
					</div>
				{/if}
			</div>
		</div>
	</div>

	{#if $selectedFolder}
		<div
			class="mx-auto px-4 md:max-w-2xl md:px-6 font-primary min-h-62"
			in:fade={{ duration: 200, delay: 200 }}
		>
			<FolderPlaceholder folder={$selectedFolder} />
		</div>
	{/if}
</div>

<style>
	:global(html:not(.dark)) .chat-placeholder :global(#message-input-container) {
		box-shadow: none;
	}
	.suggestion-row {
		grid-template-columns: 36px minmax(0, 1fr);
		padding-inline: calc(0.625rem + 1px);
	}
	:global(.chat-placeholder:has(#message-input-container.flex-col)) .suggestion-row {
		padding-inline: calc(0.375rem + 1px);
	}
	@media (max-width: 767px) {
		.suggestion-row { grid-template-columns: 38px minmax(0, 1fr); padding-inline: calc(0.5rem + 1px); }
		:global(.chat-placeholder:has(#message-input-container.flex-col)) .suggestion-row { padding-inline: calc(0.625rem + 1px); }
		.chat-placeholder { transform: none; translate: none; padding-block: 2rem; }
		.chat-placeholder :global(.text-\[1\.75rem\]),
		.chat-placeholder :global(.text-3xl) { font-size: 1.375rem; }
	}
	@media (max-width: 767px) and (max-height: 500px) {
		.chat-placeholder { padding-block: 0.75rem; }
		.chat-placeholder :global(.mb-8) { margin-bottom: 1rem; }
	}
</style>
