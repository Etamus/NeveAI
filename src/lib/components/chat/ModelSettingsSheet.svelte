<script lang="ts">
	import { fly } from 'svelte/transition';
	import { getContext } from 'svelte';
	import { showModelSettings, user } from '$lib/stores';
	import AdvancedParams from '$lib/components/chat/Settings/Advanced/AdvancedParams.svelte';
	import FileItem from '$lib/components/common/FileItem.svelte';
	import Collapsible from '$lib/components/common/Collapsible.svelte';

	const i18n = getContext('i18n');

	export let params: Record<string, any> = {};
	export let chatFiles: any[] = [];
	export let selectedModelName = '';

	const getOpen = (key: string, fallback = true): boolean => {
		const v = localStorage.getItem(`chatControls.${key}`);
		return v !== null ? v === 'true' : fallback;
	};
	const setOpen = (key: string) => (open: boolean) => {
		localStorage.setItem(`chatControls.${key}`, String(open));
	};

	let showFiles = getOpen('files');
	let showSystemPromptField = false;
	$: if ((params?.system ?? '') !== '') showSystemPromptField = true;

	const close = () => showModelSettings.set(false);
</script>

{#if $showModelSettings}
	<!-- Backdrop -->
	<button
		class="fixed inset-0 z-40 cursor-default bg-black/20 dark:bg-black/30"
		on:click={close}
		aria-label="Close settings"
		type="button"
		tabindex="-1"
	/>

	<!-- Sheet panel -->
	<div
		class="fixed top-0 right-0 bottom-0 z-50 flex flex-col bg-white dark:bg-gray-850 shadow-2xl overflow-hidden"
		style="width: 360px"
		transition:fly={{ x: 360, duration: 220, opacity: 1 }}
	>
		<!-- Header — Jan-style -->
		<div
			class="flex items-start justify-between px-5 pt-5 pb-4 border-b border-gray-200/30 dark:border-gray-700/15 shrink-0"
		>
			<div class="min-w-0 flex-1">
				<h2 class="text-sm font-semibold text-gray-900 dark:text-white truncate leading-snug">
					{selectedModelName || $i18n.t('Controles')}
				</h2>
				<p class="text-xs text-gray-400 dark:text-gray-500 mt-0.5 leading-normal">
					{$i18n.t('Ajuste os parâmetros para esta conversa')}
				</p>
			</div>

			<button
				class="ml-3 mt-0.5 p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition text-gray-500 dark:text-gray-400 shrink-0"
				on:click={close}
				aria-label={$i18n.t('Close')}
				type="button"
			>
				<svg
					xmlns="http://www.w3.org/2000/svg"
					viewBox="0 0 24 24"
					fill="none"
					stroke="currentColor"
					stroke-width="1.5"
					class="size-4"
				>
					<path stroke-linecap="round" stroke-linejoin="round" d="M6 18 18 6M6 6l12 12" />
				</svg>
			</button>
		</div>

		<!-- Content -->
		<div class="flex-1 overflow-y-auto px-4 py-3 scrollbar-hidden">
			{#if $user?.role === 'admin' || ($user?.permissions?.chat?.controls ?? true)}
				<div class="text-sm text-gray-700 dark:text-gray-300">

					{#if chatFiles.length > 0}
						<Collapsible
							title={$i18n.t('Files')}
							bind:open={showFiles}
							onChange={setOpen('files')}
							buttonClassName="w-full"
						>
							<div class="flex flex-col gap-1 mt-1.5" slot="content">
								{#each chatFiles as file, fileIdx}
									<FileItem
										className="w-full"
										item={file}
										edit={true}
										url={file?.url ?? null}
										name={file.name}
										type={file.type}
										size={file?.size}
										dismissible={true}
										small={true}
										on:dismiss={() => {
											chatFiles.splice(fileIdx, 1);
											chatFiles = chatFiles;
										}}
										on:click={() => {}}
									/>
								{/each}
							</div>
						</Collapsible>
					{/if}

					{#if $user?.role === 'admin' || ($user?.permissions?.chat?.params ?? true)}
						<div class="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1.5">{$i18n.t('Advanced Params')}</div>
						<div class="mt-1.5">
							<AdvancedParams
								admin={$user?.role === 'admin'}
								custom={true}
								separators={true}
								janStyle={true}
								bind:params
							/>
						</div>
					{/if}

					{#if $user?.role === 'admin' || ($user?.permissions?.chat?.system_prompt ?? true)}
						<div class="flex w-full items-center justify-between py-1.5 mt-1">
							{#if showSystemPromptField}
								<button
									type="button"
									class="text-xs text-gray-700 dark:text-gray-300 underline decoration-dotted cursor-pointer hover:text-gray-500 dark:hover:text-gray-400 transition"
									on:click={() => { params.system = ''; showSystemPromptField = false; }}
								>{$i18n.t('System Prompt')}</button>
							{:else}
								<div class="text-xs text-gray-700 dark:text-gray-300">{$i18n.t('System Prompt')}</div>
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
							<div class="pt-1">
								<textarea
									bind:value={params.system}
									class="w-full text-xs outline-none resize-vertical bg-transparent py-1.5"
									rows="4"
									placeholder={$i18n.t('Enter system prompt')}
								/>
							</div>
						{/if}
					{/if}
				</div>
			{/if}
		</div>
	</div>
{/if}
