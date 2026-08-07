<script>
	import { getContext, tick, onMount } from 'svelte';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { toast } from 'svelte-sonner';

	import { config } from '$lib/stores';
	import { getBackendConfig } from '$lib/apis';

	import Models from './Settings/Models.svelte';
	import Documents from './Settings/Documents.svelte';
	import CodeExecution from './Settings/CodeExecution.svelte';
	import StableDiffusion from './Settings/StableDiffusion.svelte';

	import Search from '../icons/Search.svelte';

	const i18n = getContext('i18n');

	let selectedTab = 'models';

	// Get current tab from URL pathname, default to 'models'
	$: {
		const pathParts = $page.url.pathname.split('/');
		const tabFromPath = pathParts[pathParts.length - 1];
		selectedTab = [
			'models',
			'documents',
			'code-execution',
			'stable-diffusion'
		].includes(tabFromPath)
			? tabFromPath
			: 'models';
	}

	$: if (selectedTab) {
		// scroll to selectedTab
		scrollToTab(selectedTab);
	}

	const scrollToTab = (tabId) => {
		const tabElement = document.getElementById(tabId);
		if (tabElement) {
			tabElement.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'start' });
		}
	};

	let search = '';
	let searchDebounceTimeout;
	let filteredSettings = [];

	const allSettings = [
		{
			id: 'models',
			title: 'Models',
			route: '/admin/settings/models',
			keywords: [
				'models',
				'pull',
				'delete',
				'create',
				'edit',
				'modelfile',
				'gguf',
				'import',
				'export'
			]
		},

		{
			id: 'code-execution',
			title: 'Code Execution',
			route: '/admin/settings/code-execution',
			keywords: ['code execution', 'python', 'sandbox', 'compiler', 'jupyter', 'interpreter']
		},
		{
			id: 'stable-diffusion',
			title: 'Criar imagem',
			route: '/admin/settings/stable-diffusion',
			keywords: ['stable diffusion', 'image generation', 'geração de imagem', 'sdxl', 'turbo', 'gpu']
		}
	];

	const setFilteredSettings = () => {
		filteredSettings = allSettings.filter((tab) => {
			const searchTerm = search.toLowerCase().trim();
			return (
				search === '' ||
				tab.title.toLowerCase().includes(searchTerm) ||
				tab.keywords.some((keyword) => keyword.includes(searchTerm))
			);
		});
	};

	const searchDebounceHandler = () => {
		if (searchDebounceTimeout) {
			clearTimeout(searchDebounceTimeout);
		}

		searchDebounceTimeout = setTimeout(() => {
			setFilteredSettings();
		}, 100);
	};

	onMount(() => {
		const containerElement = document.getElementById('admin-settings-tabs-container');

		if (containerElement) {
			containerElement.addEventListener('wheel', function (event) {
				if (event.deltaY !== 0) {
					// Adjust horizontal scroll position based on vertical scroll
					containerElement.scrollLeft += event.deltaY;
				}
			});
		}

		setFilteredSettings();
		// Scroll to the selected tab on mount
		scrollToTab(selectedTab);
	});
</script>

<div class="flex flex-col lg:flex-row w-full h-full pb-2 lg:space-x-4">
	<div
		id="admin-settings-tabs-container"
		class="tabs mx-[16px] lg:mx-0 lg:px-[16px] flex flex-row overflow-x-auto gap-2.5 max-w-full lg:gap-1 lg:flex-col lg:flex-none lg:w-50 dark:text-gray-200 text-sm font-medium text-left scrollbar-none"
	>
		<div
			class="hidden md:flex w-full rounded-full px-2.5 gap-2 bg-gray-100/80 dark:bg-gray-850/80 backdrop-blur-2xl my-1 -mx-1 mt-1.5"
			id="settings-search"
		>
			<div class="self-center rounded-l-xl bg-transparent">
				<Search className="size-3.5" strokeWidth="1.5" />
			</div>
			<label class="sr-only" for="search-input-settings-modal">{$i18n.t('Search')}</label>
			<input
				class="w-full py-1 text-sm bg-transparent dark:text-gray-300 outline-hidden"
				bind:value={search}
				id="search-input-settings-modal"
				on:input={searchDebounceHandler}
				placeholder={$i18n.t('Search')}
			/>
		</div>

		<!-- {$i18n.t('General')} -->
		<!-- {$i18n.t('Models')} -->
		<!-- {$i18n.t('Evaluations')} -->
		<!-- {$i18n.t('Documents')} -->
		<!-- {$i18n.t('Web Search')} -->
		<!-- {$i18n.t('Code Execution')} -->
		<!-- {$i18n.t('Interface')} -->
		<!-- {$i18n.t('Database')} -->
		{#each filteredSettings as tab (tab.id)}
			<a
				id={tab.id}
				href={tab.route}
				draggable="false"
				class="px-0.5 py-1 min-w-fit rounded-lg flex-1 lg:flex-none flex text-right transition select-none {selectedTab ===
				tab.id
					? ''
					: ' text-gray-300 dark:text-gray-600 hover:text-gray-700 dark:hover:text-white'}"
			>
				<div class=" self-center mr-2">
					{#if tab.id === 'models'}
						<svg
							xmlns="http://www.w3.org/2000/svg"
							viewBox="0 0 20 20"
							fill="currentColor"
							class="w-4 h-4"
						>
							<path
								fill-rule="evenodd"
								d="M10 1c3.866 0 7 1.79 7 4s-3.134 4-7 4-7-1.79-7-4 3.134-4 7-4zm5.694 8.13c.464-.264.91-.583 1.306-.952V10c0 2.21-3.134 4-7 4s-7-1.79-7-4V8.178c.396.37.842.688 1.306.953C5.838 10.006 7.854 10.5 10 10.5s4.162-.494 5.694-1.37zM3 13.179V15c0 2.21 3.134 4 7 4s7-1.79 7-4v-1.822c-.396.37-.842.688-1.306.953-1.532.875-3.548 1.369-5.694 1.369s-4.162-.494-5.694-1.37A7.009 7.009 0 013 13.179z"
								clip-rule="evenodd"
							/>
						</svg>
					{:else if tab.id === 'code-execution'}
						<svg
							xmlns="http://www.w3.org/2000/svg"
							viewBox="0 0 16 16"
							fill="currentColor"
							class="size-4"
						>
							<path
								fill-rule="evenodd"
								d="M2 4a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V4Zm2.22 1.97a.75.75 0 0 0 0 1.06l.97.97-.97.97a.75.75 0 1 0 1.06 1.06l1.5-1.5a.75.75 0 0 0 0-1.06l-1.5-1.5a.75.75 0 0 0-1.06 0ZM8.75 8.5a.75.75 0 0 0 0 1.5h2.5a.75.75 0 0 0 0-1.5h-2.5Z"
								clip-rule="evenodd"
							/>
						</svg>
					{:else if tab.id === 'stable-diffusion'}
						<svg
							xmlns="http://www.w3.org/2000/svg"
							viewBox="0 0 24 24"
							fill="currentColor"
							class="size-4"
						>
							<path fill-rule="evenodd" d="M1.5 6a2.25 2.25 0 0 1 2.25-2.25h16.5A2.25 2.25 0 0 1 22.5 6v12a2.25 2.25 0 0 1-2.25 2.25H3.75A2.25 2.25 0 0 1 1.5 18V6ZM3 16.06V18c0 .414.336.75.75.75h16.5A.75.75 0 0 0 21 18v-1.94l-2.69-2.689a1.5 1.5 0 0 0-2.12 0l-.88.879.97.97a.75.75 0 1 1-1.06 1.06l-5.16-5.159a1.5 1.5 0 0 0-2.12 0L3 16.061Zm10.125-7.81a1.125 1.125 0 1 1 2.25 0 1.125 1.125 0 0 1-2.25 0Z" clip-rule="evenodd" />
						</svg>
					{/if}
				</div>
				<div class=" self-center">{$i18n.t(tab.title)}</div>
			</a>
		{/each}
	</div>

	<div
		class="flex-1 mt-3 lg:mt-1 px-[16px] lg:pr-[16px] lg:pl-0 overflow-y-scroll scrollbar-hidden"
	>
		{#if selectedTab === 'models'}
			<Models />

		{:else if selectedTab === 'code-execution'}
			<CodeExecution
				saveHandler={async () => {
					toast.success($i18n.t('Settings saved successfully!'));

					await tick();
					await config.set(await getBackendConfig());
				}}
			/>
		{:else if selectedTab === 'stable-diffusion'}
			<StableDiffusion
				saveHandler={async () => {
					toast.success($i18n.t('Settings saved successfully!'));

					await tick();
					await config.set(await getBackendConfig());
				}}
			/>
		{/if}
	</div>
</div>
