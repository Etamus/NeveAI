<script lang="ts" context="module">
	const searchModalCache: {
		query: string;
		page: number;
		chatList: any[] | null;
		allChatsLoaded: boolean;
	} = {
		query: '',
		page: 1,
		chatList: null,
		allChatsLoaded: false
	};
</script>

<script lang="ts">
	import { toast } from 'svelte-sonner';
	import { getContext, onDestroy, tick } from 'svelte';
	import type { I18nStore } from '$lib/i18n';
	const i18n = getContext<I18nStore>('i18n');

	import Modal from '$lib/components/common/Modal.svelte';
	import MobileModalTitle from '$lib/components/common/MobileModalTitle.svelte';
	import SearchInput from './Sidebar/SearchInput.svelte';
	import { getChatById, getChatList, getChatListBySearchText } from '$lib/apis/chats';

	import dayjs from '$lib/dayjs';
	import localizedFormat from 'dayjs/plugin/localizedFormat';
	import calendar from 'dayjs/plugin/calendar';
	import Loader from '../common/Loader.svelte';
	import { createMessagesList } from '$lib/utils';
	import { user } from '$lib/stores';
	import Messages from '../chat/Messages.svelte';
	import { goto } from '$app/navigation';
	import PencilSquare from '../icons/PencilSquare.svelte';
	import XMark from '../icons/XMark.svelte';
	dayjs.extend(calendar);
	dayjs.extend(localizedFormat);

	export let show = false;
	export let onClose = () => {};

	$: actions = [
		{
			label: $i18n.t('Start a new conversation'),
			onClick: async () => {
				await goto(`/${query ? `?q=${query}` : ''}`);
				show = false;
				onClose();
			},
			icon: PencilSquare
		}
	];

	let query = searchModalCache.query;
	let page = searchModalCache.page;

	let chatList = searchModalCache.chatList;

	let chatListLoading = false;
	let allChatsLoaded = searchModalCache.allChatsLoaded;

	let searchDebounceTimeout;
	let searchRequestId = 0;
	let previewRequestId = 0;
	let searchShell: HTMLDivElement;
	let wasShown = false;

	let selectedIdx = null;
	let keyboardSelection = false;
	let selectedChat = null;

	let selectedModels = [''];
	let history = null;
	let messages = null;

	$: if (show && !chatListLoading && chatList) {
		loadChatPreview(selectedIdx);
	}

	const loadChatPreview = async (selectedIdx) => {
		const requestId = ++previewRequestId;
		if (!chatList || chatList.length === 0 || selectedIdx === null) {
			selectedChat = null;
			messages = null;
			history = null;
			selectedModels = [''];
			return;
		}

		const selectedChatIdx = selectedIdx - actions.length;
		if (selectedChatIdx < 0 || selectedChatIdx >= chatList.length) {
			selectedChat = null;
			messages = null;
			history = null;
			selectedModels = [''];
			return;
		}

		const chatId = chatList[selectedChatIdx].id;

		const chat = await getChatById(localStorage.token, chatId).catch(async (error) => {
			return null;
		});
		if (requestId !== previewRequestId || !show || chatList?.[selectedChatIdx]?.id !== chatId) return;

		if (chat) {
			selectedChat = chat;
			if (chat?.chat?.history) {
				selectedModels =
					(chat?.chat?.models ?? undefined) !== undefined
						? chat?.chat?.models
						: [chat?.chat?.models ?? ''];

				history = chat?.chat?.history;
				messages = createMessagesList(chat?.chat?.history, chat?.chat?.history?.currentId);

				// scroll to the bottom of the messages container
				await tick();
				const messagesContainerElement = document.getElementById('chat-preview');
				if (messagesContainerElement) {
					messagesContainerElement.scrollTop = messagesContainerElement.scrollHeight;
				}
			} else {
				messages = [];
			}
		} else {
			toast.error($i18n.t('Failed to load chat preview'));
			selectedChat = null;
			messages = null;
			history = null;
			selectedModels = [''];
			return;
		}
	};

	const persistSearchCache = () => {
		searchModalCache.query = query;
		searchModalCache.page = page;
		searchModalCache.chatList = chatList;
		searchModalCache.allChatsLoaded = allChatsLoaded;
	};

	const searchHandler = async (immediate = false) => {
		if (!show) {
			return;
		}

		if (searchDebounceTimeout) {
			clearTimeout(searchDebounceTimeout);
		}

		page = 1;
		const currentQuery = query;
		const requestId = ++searchRequestId;
		previewRequestId += 1;
		chatListLoading = true;
		selectedIdx = null;
		keyboardSelection = false;
		selectedChat = null;
		messages = null;
		history = null;
		selectedModels = [''];

		const runSearch = async () => {
			chatListLoading = true;
			try {
				const nextChatList =
					currentQuery === ''
						? await getChatList(localStorage.token, 1)
						: await getChatListBySearchText(localStorage.token, currentQuery, 1);

				if (!show || requestId !== searchRequestId || currentQuery !== query) return;

				chatList = nextChatList;
				allChatsLoaded = (chatList ?? []).length === 0;
				persistSearchCache();
			} catch (error) {
				if (show && requestId === searchRequestId) {
					chatList = [];
					allChatsLoaded = true;
					toast.error(`${error}`);
				}
			} finally {
				if (requestId === searchRequestId) {
					chatListLoading = false;
				}
			}
		};

		if (immediate || currentQuery === '') {
			await runSearch();
		} else {
			searchDebounceTimeout = setTimeout(runSearch, 500);
		}
	};

	const loadMoreChats = async () => {
		if (!show || chatListLoading || allChatsLoaded) return;
		const requestId = searchRequestId;
		const currentQuery = query;
		const nextPage = page + 1;
		chatListLoading = true;
		try {
			const newChatList = currentQuery
				? await getChatListBySearchText(localStorage.token, currentQuery, nextPage)
				: await getChatList(localStorage.token, nextPage);
			if (!show || requestId !== searchRequestId || currentQuery !== query) return;
			page = nextPage;
			allChatsLoaded = newChatList.length === 0;
			if (newChatList.length > 0) chatList = [...(chatList ?? []), ...newChatList];
			persistSearchCache();
		} catch (error) {
			if (show && requestId === searchRequestId) toast.error(`${error}`);
		} finally {
			if (requestId === searchRequestId) chatListLoading = false;
		}
	};

	$: if (show && !wasShown) {
		wasShown = true;
		keyboardSelection = false;
		selectedIdx = null;
		searchHandler();
	} else if (!show && wasShown) {
		wasShown = false;
		clearTimeout(searchDebounceTimeout);
		searchRequestId += 1;
		previewRequestId += 1;
		chatListLoading = false;
	}

	const onKeyDown = (event: KeyboardEvent) => {
		if (!show || event.isComposing || !['Enter', 'Escape', 'ArrowDown', 'ArrowUp'].includes(event.key)) return;
		event.stopPropagation();
		if (event.key === 'Enter' && (event.target as HTMLElement).closest('a, button')) return;
		event.preventDefault();
		if (event.key === 'Escape') {
			show = false;
			onClose();
			return;
		}
		if (event.key === 'Enter') {
			const selected = keyboardSelection && !chatListLoading
				? searchShell?.querySelector<HTMLElement>('[data-arrow-selected="true"]') : null;
			if (selected) selected.click();
			else void searchHandler(true);
			return;
		}
		if (chatListLoading) return;
		keyboardSelection = true;
		const lastIndex = actions.length + (chatList?.length ?? 0) - 1;
		selectedIdx = selectedIdx === null
			? event.key === 'ArrowDown' ? (query && chatList?.length ? actions.length : 0) : lastIndex
			: Math.min(lastIndex, Math.max(0, selectedIdx + (event.key === 'ArrowDown' ? 1 : -1)));
		void tick().then(() => searchShell?.querySelector<HTMLElement>('[data-arrow-selected="true"]')?.scrollIntoView({block: 'nearest'}));
	};

	onDestroy(() => {
		if (searchDebounceTimeout) {
			clearTimeout(searchDebounceTimeout);
		}
		searchRequestId += 1;
		previewRequestId += 1;
	});
</script>

<Modal size="w-[60rem]" bind:show mobileFullscreen containerClassName="p-2 sm:p-3 outline-none" initialFocus="#search-input" keepMounted>
	<!-- svelte-ignore a11y_no_static_element_interactions (Delegates keyboard events from the search controls.) -->
	<div
		bind:this={searchShell}
		on:keydown={onKeyDown}
		class="search-modal-shell py-3 dark:text-gray-300 text-gray-700 flex flex-col"
		style="height: min(39rem, calc(100dvh - 1.5rem));"
	>
		<div class="mobile-search-title"><MobileModalTitle>{$i18n.t('Sidebar Search')}</MobileModalTitle></div>
		<div class="px-4 pb-1.5 flex items-center gap-2">
			<div class="min-w-0 flex-1">
				<SearchInput
					bind:value={query}
					on:input={(event) => { query = event.detail; void searchHandler(); }}
					placeholder={$i18n.t('Search')}
					showClearButton={false}
					onFocus={() => {
						selectedIdx = null;
						keyboardSelection = false;
						messages = null;
					}}
				/>
			</div>
			<button data-mobile-modal-close
				aria-label={$i18n.t('Close search modal')}
				class="search-modal-close text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 transition"
				on:click={() => {
					show = false;
					onClose();
				}}
			>
				<XMark className="w-5 h-5"></XMark>
			</button>
		</div>

		<!-- <hr class="border-gray-50 dark:border-gray-850/30 my-1" /> -->

		<div class="flex px-4 pb-1 min-h-0 flex-1">
			<div
				class="flex flex-col overflow-y-auto h-full min-h-0 max-h-full scrollbar-hidden w-full flex-1 pr-2"
			>
				<div class="w-full text-xs text-gray-500 dark:text-gray-500 font-medium pb-2 px-2">
					{$i18n.t('Actions')}
				</div>

				{#each actions as action, idx (action.label)}
					<button
						class=" w-full flex items-center rounded-xl text-sm py-2 px-3 hover:bg-gray-50 dark:hover:bg-gray-850 {keyboardSelection && selectedIdx ===
						idx
							? 'bg-gray-50 dark:bg-gray-850'
							: ''}"
						data-arrow-selected={selectedIdx === idx ? 'true' : undefined}
						draggable="false"
						on:mouseenter={() => {
							keyboardSelection = false;
							selectedIdx = idx;
						}}
						on:click={async () => {
							await action.onClick();
						}}
					>
						<div class="pr-2">
							<svelte:component this={action.icon} />
						</div>
						<div class=" flex-1 text-left">
							<div class="text-ellipsis line-clamp-1 w-full">
								{$i18n.t(action.label)}
							</div>
						</div>
					</button>
				{/each}

				{#if chatList}
					<hr class="border-gray-50 dark:border-gray-850/30 my-3" />

					{#if chatList.length === 0}
						<div class="text-xs text-gray-500 dark:text-gray-400 text-center px-5 py-4">
							{$i18n.t('No results found')}
						</div>
					{/if}

					{#each chatList as chat, idx (chat.id)}
						{#if idx === 0 || (idx > 0 && chat.time_range !== chatList[idx - 1].time_range)}
							<div
								class="w-full text-xs text-gray-500 dark:text-gray-500 font-medium {idx === 0
									? ''
									: 'pt-5'} pb-2 px-2"
							>
								{$i18n.t(chat.time_range)}
								<!-- localisation keys for time_range to be recognized from the i18next parser (so they don't get automatically removed):
							{$i18n.t('Today')}
							{$i18n.t('Yesterday')}
							{$i18n.t('Previous 7 days')}
							{$i18n.t('Previous 30 days')}
							{$i18n.t('January')}
							{$i18n.t('February')}
							{$i18n.t('March')}
							{$i18n.t('April')}
							{$i18n.t('May')}
							{$i18n.t('June')}
							{$i18n.t('July')}
							{$i18n.t('August')}
							{$i18n.t('September')}
							{$i18n.t('October')}
							{$i18n.t('November')}
							{$i18n.t('December')}
							-->
							</div>
						{/if}

						<a
							class=" w-full flex justify-between items-center rounded-xl text-sm py-2 px-3 hover:bg-gray-50 dark:hover:bg-gray-850 {keyboardSelection && selectedIdx ===
							idx + actions.length
								? 'bg-gray-50 dark:bg-gray-850'
								: ''}"
							href="/c/{chat.id}"
							draggable="false"
							data-arrow-selected={selectedIdx === idx + actions.length ? 'true' : undefined}
							on:mouseenter={() => {
								keyboardSelection = false;
								selectedIdx = idx + actions.length;
							}}
							on:click|preventDefault={async () => {
								await goto(`/c/${chat.id}`);
								show = false;
								onClose();
							}}
						>
							<div class=" flex-1">
								<div class="text-ellipsis line-clamp-1 w-full">
									{chat?.title}
								</div>
							</div>

							<div class=" pl-3 shrink-0 text-gray-500 dark:text-gray-400 text-xs">
								{dayjs(chat?.updated_at * 1000).calendar(null, {
									sameDay: `[${$i18n.t('Today')}]`,
									nextDay: `[${$i18n.t('Tomorrow')}]`,
									nextWeek: 'dddd',
									lastDay: `[${$i18n.t('Yesterday')}]`,
									lastWeek: `[${$i18n.t('Last')}] dddd`,
									sameElse: 'L'
								})}
							</div>
						</a>
					{/each}

					{#if !allChatsLoaded}
						<Loader
							on:visible={(e) => {
								if (!chatListLoading) {
									loadMoreChats();
								}
							}}
						>
							<div class="h-px w-full" aria-hidden="true"></div>
						</Loader>
					{/if}
				{:else}
					<div class="w-full h-full"></div>
				{/if}
			</div>
			<div
				id="chat-preview"
				class="hidden md:flex md:flex-1 w-full overflow-y-auto h-full min-h-0 scrollbar-hidden"
			>
				{#if messages === null}
					<div
						class="w-full h-full flex justify-center items-center text-gray-500 dark:text-gray-400 text-sm"
					>
						{$i18n.t('Select a conversation to preview')}
					</div>
				{:else}
					<div class="w-full h-full flex flex-col">
						<Messages
							className="h-full flex pt-4 pb-8 w-full"
							chatId={`chat-preview-${selectedChat?.id ?? ''}`}
							user={$user}
							readOnly={true}
							{selectedModels}
							bind:history
							autoScroll={true}
							sendMessage={() => {}}
							continueResponse={() => {}}
							regenerateResponse={() => {}}
						/>
					</div>
				{/if}
			</div>
		</div>
	</div>
</Modal>

<style>
	.mobile-search-title { display: none; }
	@media (max-width: 767px) {
		.mobile-search-title { display: block; padding: 0 16px 8px; font-size: 18px; font-weight: 600; }
		.search-modal-shell { height: 100% !important; min-height: 0; }
		.search-modal-close { display: none; }
	}
</style>
