<script lang="ts">
	import { getContext } from 'svelte';
	import { dismissChatDropdowns } from '$lib/utils/chatDropdownDismissal';

	import { banners, chatId, config, mobile, models as globalModels, settings, showSidebar, temporaryChatEnabled, user } from '$lib/stores';

	import { page } from '$app/stores';
	import { goto } from '$app/navigation';

	import ModelSelector from '../chat/ModelSelector.svelte';
	import Tooltip from '../common/Tooltip.svelte';
	import Menu from '$lib/components/layout/Navbar/Menu.svelte';
	import AdjustmentsHorizontal from '../icons/AdjustmentsHorizontal.svelte';

	import PencilSquare from '../icons/PencilSquare.svelte';
	import Banner from '../common/Banner.svelte';
	import Sidebar from '../icons/Sidebar.svelte';

	import ChatBubbleDotted from '../icons/ChatBubbleDotted.svelte';
	import ChatBubbleDottedChecked from '../icons/ChatBubbleDottedChecked.svelte';

	import EllipsisHorizontal from '../icons/EllipsisHorizontal.svelte';
	import ChatPlus from '../icons/ChatPlus.svelte';
	import ChatCheck from '../icons/ChatCheck.svelte';
	import Knobs from '../icons/Knobs.svelte';
	import { showModelSettings } from '$lib/stores';
	const i18n = getContext('i18n');

	export let initNewChat: Function;
	export let menuEnabled: boolean = false;
	export let scrollTop = 0;

	export let chat;
	export let history;
	export let selectedModels;
	export let showModelSelector = true;

	export let onSaveTempChat: () => {};
	export let moveChatHandler: (id: string, folderId: string) => void;

	let closedBannerIds = [];

</script>


<button
	id="new-chat-button"
	class="hidden"
	on:click={() => {
		initNewChat();
	}}
	aria-label="New Chat"
/>

<nav class="chat-navbar sticky top-0 z-30 w-full pt-0.5 pb-1 flex flex-col items-center drag-region">
	<div class="flex items-center w-full pl-1.5 pr-0">
		<div
			id="navbar-bg-gradient-to-b"
			class="{chat?.id
				? 'visible'
				: 'invisible'} chat-navbar-fade pointer-events-none absolute inset-0 -bottom-7 z-[-1]"
		></div>

		<div class=" flex max-w-full w-full mx-auto px-1.5 md:px-2 pt-0.5 bg-transparent">
			<div class="flex items-center w-full max-w-full">
				{#if $mobile && !$showSidebar}
					<div
						class="chat-navbar-sidebar -translate-x-0.5 mr-1 mt-1 self-start flex flex-none items-center text-gray-600 dark:text-gray-400"
					>
						<Tooltip content={$showSidebar ? $i18n.t('Close Sidebar') : $i18n.t('Open Sidebar')}>
							<button
								class=" cursor-pointer flex rounded-lg hover:bg-gray-100 dark:hover:bg-gray-850 transition"
								on:click={() => {
									showSidebar.set(!$showSidebar);
								}}
							>
								<div class=" self-center p-1.5">
									<Sidebar />
								</div>
							</button>
						</Tooltip>
					</div>
				{/if}

				<div
					class="chat-navbar-model flex-1 overflow-hidden max-w-full mt-0.5 py-0.5
			{$showSidebar ? '-ml-1' : '-ml-2'}
			"
				>
					{#if showModelSelector}
						<ModelSelector bind:selectedModels />
					{/if}
				</div>

				<div class="chat-navbar-actions self-start flex flex-none items-center text-gray-600 dark:text-gray-400">
					<!-- <div class="md:hidden flex self-center w-[1px] h-5 mx-2 bg-gray-300 dark:bg-stone-700" /> -->

					{#if $mobile && !$temporaryChatEnabled && chat && chat.id}
						<Tooltip content={$i18n.t('New Chat')}>
							<button
								class=" flex {$showSidebar
									? 'md:hidden'
									: ''} cursor-pointer px-2 py-2 rounded-xl text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-850 transition"
								on:click={() => {
									initNewChat();
								}}
								aria-label="New Chat"
							>
								<div class=" m-auto self-center">
									<ChatPlus className=" size-4.5" strokeWidth="1.5" />
								</div>
							</button>
						</Tooltip>
					{/if}

					{#if menuEnabled && chat && (chat.id || $temporaryChatEnabled)}
						<Menu
							{chat}
							{moveChatHandler}
						>
							<button
								class="flex cursor-pointer px-2 py-2 rounded-xl hover:bg-gray-50 dark:hover:bg-gray-850 transition"
								id="chat-context-menu-button"
							>
								<div class=" m-auto self-center">
									<EllipsisHorizontal className=" size-5" strokeWidth="1.5" />
								</div>
							</button>
						</Menu>
					{/if}

					{#if $user?.role === 'user' ? ($user?.permissions?.chat?.temporary ?? true) && !($user?.permissions?.chat?.temporary_enforced ?? false) : true}
						{#if !chat?.id}
							<Tooltip content={$i18n.t(`Temporary Chat`)}>
								<button
									class="flex cursor-pointer px-2 py-2 rounded-xl hover:bg-gray-50 dark:hover:bg-gray-850 transition"
									id="temporary-chat-button"
									on:click={async () => {
										await dismissChatDropdowns();
										if (($settings?.temporaryChatByDefault ?? false) && $temporaryChatEnabled) {
											// for proper initNewChat handling
											await temporaryChatEnabled.set(null);
										} else {
											await temporaryChatEnabled.set(!$temporaryChatEnabled);
										}

										if ($page.url.pathname !== '/') {
											await goto('/');
										}

										// add 'temporary-chat=true' to the URL
										if ($temporaryChatEnabled) {
											window.history.replaceState(null, '', '?temporary-chat=true');
										} else {
											window.history.replaceState(null, '', location.pathname);
										}
									}}
								>
									<div class=" m-auto self-center">
										{#if $temporaryChatEnabled}
											<ChatBubbleDottedChecked className=" size-4.5" strokeWidth="1.5" />
										{:else}
											<ChatBubbleDotted className=" size-4.5" strokeWidth="1.5" />
										{/if}
									</div>
								</button>
							</Tooltip>
						{:else if $temporaryChatEnabled}
							<Tooltip content={$i18n.t(`Save Chat`)}>
								<button
									class="flex cursor-pointer px-2 py-2 rounded-xl hover:bg-gray-50 dark:hover:bg-gray-850 transition"
									id="save-temporary-chat-button"
									on:click={async () => {
										onSaveTempChat();
									}}
								>
									<div class=" m-auto self-center">
										<ChatCheck className=" size-4.5" strokeWidth="1.5" />
									</div>
								</button>
							</Tooltip>
						{/if}
					{/if}

					{#if selectedModels?.some((id) => $globalModels.some((model) => model.id === id)) && ($user?.role === 'admin' || ($user?.permissions?.chat?.controls ?? true))}
						<Tooltip content={$i18n.t('Parâmetros')}>
							<button id="chat-parameters-button" type="button" aria-label={$i18n.t('Parâmetros')} aria-expanded={$showModelSettings} class="flex cursor-pointer px-2 py-2 rounded-xl hover:bg-gray-50 dark:hover:bg-gray-850 transition" on:click={() => showModelSettings.set(!$showModelSettings)}>
								<Sidebar className="size-5 -scale-x-100" />
							</button>
						</Tooltip>
					{/if}
				</div>
			</div>
		</div>
	</div>

	{#if $temporaryChatEnabled && ($chatId ?? '').startsWith('local:')}
		<div class=" w-full z-30 text-center">
			<div class="text-xs text-gray-500">{$i18n.t('Temporary Chat')}</div>
		</div>
	{/if}

	<div class="absolute top-[100%] left-0 right-0 h-fit">
		{#if !history.currentId && !$chatId && $banners.length > 0}
			<div class=" w-full z-30">
				<div class=" flex flex-col gap-1 w-full">
					{#each $banners.filter((b) => ![...JSON.parse(localStorage.getItem('dismissedBannerIds') ?? '[]'), ...closedBannerIds].includes(b.id)) as banner (banner.id)}
						<Banner
							{banner}
							on:dismiss={(e) => {
								const bannerId = e.detail;

								if (banner.dismissible) {
									localStorage.setItem(
										'dismissedBannerIds',
										JSON.stringify(
											[
												bannerId,
												...JSON.parse(localStorage.getItem('dismissedBannerIds') ?? '[]')
											].filter((id) => $banners.find((b) => b.id === id))
										)
									);
								} else {
									closedBannerIds = [...closedBannerIds, bannerId];
								}
							}}
						/>
					{/each}
				</div>
			</div>
		{/if}
	</div>
</nav>

<style>
	.chat-navbar-fade { background-image: linear-gradient(to bottom, #fff, rgb(255 255 255 / 80%), rgb(255 255 255 / 0%)); }
	:global(.dark) .chat-navbar-fade { background-image: linear-gradient(to bottom, #000, rgb(0 0 0 / 80%), rgb(0 0 0 / 0%)); }
	@media (max-width: 767px) {
		.chat-navbar {
			min-height: calc(3rem + env(safe-area-inset-top, 0px));
			padding-top: env(safe-area-inset-top, 0px);
			padding-bottom: 0;
		}
		.chat-navbar > :global(div) { min-height: 3rem; }
		.chat-navbar-model { min-width: 0; margin: 0; padding: 0; }
		.chat-navbar-actions { align-self: center; gap: 0; min-width: 0; }
		.chat-navbar-sidebar { align-self: center; margin: 0; transform: none; }
		.chat-navbar-sidebar :global(button) { width: 38px; height: 38px; justify-content: center; align-items: center; padding: 0; }
		.chat-navbar :global(button) { min-height: 38px; }
		.chat-navbar :global(button[id^='model-selector-']) { padding-inline: 0.375rem; font-size: 18px; }
		.chat-navbar :global(button[aria-label='New Chat']) { display: none; }
		.chat-navbar :global(#chat-context-menu-button),
		.chat-navbar :global(button[aria-label='Models']),
		.chat-navbar :global(#chat-parameters-button),
		.chat-navbar :global(#temporary-chat-button),
		.chat-navbar :global(#save-temporary-chat-button) { width: 38px; height: 38px; padding: 0; justify-content: center; align-items: center; }
		.chat-navbar :global(button svg) { flex-shrink: 0; }
		.chat-navbar-actions :global(button) { flex-shrink: 0; }
	}
</style>
