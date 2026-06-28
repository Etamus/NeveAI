<script lang="ts">
	import { getContext, onMount, tick } from 'svelte';
	import { toast } from 'svelte-sonner';
	import { config, models, settings, user, showSettingsTab } from '$lib/stores';
	import { updateUserSettings } from '$lib/apis/users';
	import { getModels as _getModels } from '$lib/apis';
	import { goto } from '$app/navigation';

	import Modal from '../common/Modal.svelte';
	import General from './Settings/General.svelte';
	import DataControls from './Settings/DataControls.svelte';
	import Personalization from './Settings/Personalization.svelte';
	import About from './Settings/About.svelte';
	import Search from '../icons/Search.svelte';
	import XMark from '../icons/XMark.svelte';
	import DatabaseSettings from '../icons/DatabaseSettings.svelte';
	import SettingsAlt from '../icons/SettingsAlt.svelte';
	import UserCircle from '../icons/UserCircle.svelte';
	import Face from '../icons/Face.svelte';
	import UserBadgeCheck from '../icons/UserBadgeCheck.svelte';
	import Info from '../icons/Info.svelte';

	const i18n = getContext('i18n');

	export let show = false;

	$: if (show) {
		addScrollListener();
		if ($showSettingsTab) {
			selectedTab = $showSettingsTab;
			showSettingsTab.set('');
		}
	} else {
		removeScrollListener();
	}

	interface SettingsTab {
		id: string;
		title: string;
		keywords: string[];
	}

	const allSettings: SettingsTab[] = [
		{
			id: 'general',
			title: 'General',
			keywords: [
				'advancedparams',
				'advancedparameters',
				'advanced params',
				'advanced parameters',
				'configuration',
				'defaultparameters',
				'default parameters',
				'defaultsettings',
				'default settings',
				'general',
				'keepalive',
				'keep alive',
				'languages',
				'notifications',
				'requestmode',
				'request mode',
				'systemparameters',
				'system parameters',
				'systemprompt',
				'system prompt',
				'systemsettings',
				'system settings',
				'theme',
				'translate',
				'neveaisettings',
				'neveai settings'
			]
		},
		{
			id: 'personalization',
			title: 'Personalization',
			keywords: [
				'account preferences',
				'account settings',
				'accountpreferences',
				'accountsettings',
				'custom settings',
				'customsettings',
				'experimental',
				'memories',
				'memory',
				'personalization',
				'personalize',
				'personal settings',
				'personalsettings',
				'profile',
				'user preferences',
				'userpreferences'
			]
		},
		{
			id: 'data_controls',
			title: 'Data Controls',
			keywords: [
				'archive all chats',
				'archive chats',
				'archiveallchats',
				'archivechats',
				'archived chats',
				'archivedchats',
				'chat activity',
				'chat history',
				'chat settings',
				'chatactivity',
				'chathistory',
				'chatsettings',
				'conversation activity',
				'conversation history',
				'conversationactivity',
				'conversationhistory',
				'conversations',
				'convos',
				'delete all chats',
				'delete chats',
				'deleteallchats',
				'deletechats',
				'export chats',
				'exportchats',
				'import chats',
				'importchats',
				'message activity',
				'message archive',
				'message history',
				'messagearchive',
				'messagehistory'
			]
		},
		{
			id: 'about',
			title: 'Sobre',
			keywords: [
				'about',
				'sobre',
				'version',
				'versao',
				'versão',
				'creator',
				'criador',
				'mateus',
				'etamus',
				'github',
				'hugging face',
				'license',
				'licenca',
				'licença'
			]
		}
	];

	let availableSettings = [];
	let filteredSettings = [];

	let search = '';
	let searchDebounceTimeout;

	const getAvailableSettings = () => {
		return allSettings.filter((tab) => {
			if (tab.id === 'personalization') {
				return true;
			}

			// Admin-only tabs
			if (tab.id.startsWith('admin-')) {
				return $user?.role === 'admin';
			}

			return true;
		});
	};

	const setFilteredSettings = () => {
		filteredSettings = availableSettings
			.filter((tab) => {
				return (
					search === '' ||
					tab.title.toLowerCase().includes(search.toLowerCase().trim()) ||
					tab.keywords.some((keyword) => keyword.includes(search.toLowerCase().trim()))
				);
			})
			.map((tab) => tab.id);

		if (filteredSettings.length > 0 && !filteredSettings.includes(selectedTab)) {
			selectedTab = filteredSettings[0];
		}
	};

	const searchDebounceHandler = () => {
		if (searchDebounceTimeout) {
			clearTimeout(searchDebounceTimeout);
		}

		searchDebounceTimeout = setTimeout(() => {
			setFilteredSettings();
		}, 100);
	};

	const saveSettings = async (updated) => {
		console.log(updated);
		await settings.set({ ...$settings, ...updated });
		await models.set(await getModels());
		await updateUserSettings(localStorage.token, { ui: $settings });
	};

	const getModels = async () => {
		return await _getModels(localStorage.token);
	};

	let selectedTab = 'general';

	// Function to handle sideways scrolling
	const scrollHandler = (event) => {
		const settingsTabsContainer = document.getElementById('settings-tabs-container');
		if (settingsTabsContainer) {
			event.preventDefault(); // Prevent default vertical scrolling
			settingsTabsContainer.scrollLeft += event.deltaY; // Scroll sideways
		}
	};

	const addScrollListener = async () => {
		await tick();
		const settingsTabsContainer = document.getElementById('settings-tabs-container');
		if (settingsTabsContainer) {
			settingsTabsContainer.addEventListener('wheel', scrollHandler);
		}
	};

	const removeScrollListener = async () => {
		await tick();
		const settingsTabsContainer = document.getElementById('settings-tabs-container');
		if (settingsTabsContainer) {
			settingsTabsContainer.removeEventListener('wheel', scrollHandler);
		}
	};

	onMount(() => {
		availableSettings = getAvailableSettings();
		setFilteredSettings();

		config.subscribe((configData) => {
			availableSettings = getAvailableSettings();
			setFilteredSettings();
		});
	});
</script>

<Modal size="md" bind:show keepMounted>
	<div class="text-gray-700 dark:text-gray-100">
		<div class="flex justify-between items-center px-5 pt-4 pb-3 border-b border-gray-200/30 dark:border-gray-700/20">
			<div class="text-lg font-semibold dark:text-gray-100">
				{$i18n.t('Settings')}
			</div>
			<button
				aria-label={$i18n.t('Close settings modal')}
				class="text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 transition"
				on:click={() => {
					show = false;
				}}
			>
				<XMark className="w-5 h-5"></XMark>
			</button>
		</div>

		<div class="flex flex-col md:flex-row w-full">
			<div
				role="tablist"
				id="settings-tabs-container"
				class="tabs flex flex-row overflow-x-auto gap-1 px-3 py-3 md:px-3 md:gap-0.5 md:flex-col flex-1 md:flex-none md:w-44 md:min-h-[22rem] md:max-h-[22rem] dark:text-gray-200 text-sm text-left md:border-r border-gray-200/30 dark:border-gray-700/20"
			>

				{#if filteredSettings.length > 0}
					{#each filteredSettings as tabId (tabId)}
						{#if tabId === 'general'}
							<button
								role="tab"
								aria-controls="tab-general"
								aria-selected={selectedTab === 'general'}
								class="px-3 py-2 min-w-fit rounded-lg flex items-center gap-2 transition
								{selectedTab === 'general'
									? 'font-semibold text-gray-900 dark:text-white bg-gray-100 dark:bg-gray-800'
									: 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-800/50'}"
								on:click={() => {
									selectedTab = 'general';
								}}
							>
								<SettingsAlt strokeWidth="2" />
								<span>{$i18n.t('General')}</span>
							</button>
						{:else if tabId === 'personalization'}
							<button
								role="tab"
								aria-controls="tab-personalization"
								aria-selected={selectedTab === 'personalization'}
								class="px-3 py-2 min-w-fit rounded-lg flex items-center gap-2 transition
								{selectedTab === 'personalization'
									? 'font-semibold text-gray-900 dark:text-white bg-gray-100 dark:bg-gray-800'
									: 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-800/50'}"
								on:click={() => {
									selectedTab = 'personalization';
								}}
							>
								<Face strokeWidth="2" />
								<span>{$i18n.t('Personalization')}</span>
							</button>
						{:else if tabId === 'data_controls'}
							<button
								role="tab"
								aria-controls="tab-data-controls"
								aria-selected={selectedTab === 'data_controls'}
								class="px-3 py-2 min-w-fit rounded-lg flex items-center gap-2 transition
								{selectedTab === 'data_controls'
									? 'font-semibold text-gray-900 dark:text-white bg-gray-100 dark:bg-gray-800'
									: 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-800/50'}"
								on:click={() => {
									selectedTab = 'data_controls';
								}}
							>
								<DatabaseSettings strokeWidth="2" />
								<span>{$i18n.t('Data Controls')}</span>
							</button>
						{:else if tabId === 'about'}
							<button
								role="tab"
								aria-controls="tab-about"
								aria-selected={selectedTab === 'about'}
								class="px-3 py-2 min-w-fit rounded-lg flex items-center gap-2 transition
								{selectedTab === 'about'
									? 'font-semibold text-gray-900 dark:text-white bg-gray-100 dark:bg-gray-800'
									: 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-800/50'}"
								on:click={() => {
									selectedTab = 'about';
								}}
							>
								<Info strokeWidth="2" />
								<span>Sobre</span>
							</button>
						{/if}
					{/each}
				{:else}
					<div class="text-center text-gray-500 mt-4">
						{$i18n.t('No results found')}
					</div>
				{/if}
			</div>
			<div class="flex-1 px-4 py-3 md:min-h-[22rem] max-h-[22rem] overflow-y-auto">
				{#if selectedTab === 'general'}
					<General
						{getModels}
						{saveSettings}
						on:save={() => {
							toast.success($i18n.t('Settings saved successfully!'));
						}}
					/>
				{:else if selectedTab === 'personalization'}
					<Personalization
						{saveSettings}
						on:save={() => {
							toast.success($i18n.t('Settings saved successfully!'));
							show = false;
						}}
					/>
				{:else if selectedTab === 'data_controls'}
					<DataControls {saveSettings} />
				{:else if selectedTab === 'about'}
					<About />
				{/if}
			</div>
		</div>
	</div>
</Modal>

<style>
	input::-webkit-outer-spin-button,
	input::-webkit-inner-spin-button {
		/* display: none; <- Crashes Chrome on hover */
		-webkit-appearance: none;
		margin: 0; /* <-- Apparently some margin are still there even though it's hidden */
	}

	.tabs::-webkit-scrollbar {
		display: none; /* for Chrome, Safari and Opera */
	}

	.tabs {
		-ms-overflow-style: none; /* IE and Edge */
		scrollbar-width: none; /* Firefox */
	}

	input[type='number'] {
		appearance: textfield;
		-moz-appearance: textfield; /* Firefox */
	}
</style>
