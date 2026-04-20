<script lang="ts">
	import { createEventDispatcher, getContext } from 'svelte';
	const dispatch = createEventDispatcher();
	const i18n = getContext('i18n');

	import XMark from '$lib/components/icons/XMark.svelte';
	import AdvancedParams from '../Settings/Advanced/AdvancedParams.svelte';
	import FileItem from '$lib/components/common/FileItem.svelte';
	import Collapsible from '$lib/components/common/Collapsible.svelte';

	import { user, settings } from '$lib/stores';
	export let models = [];
	export let chatFiles = [];
	export let params = {};
	export let embed = false;

	// Persist collapsible section open/close state
	const getOpen = (key: string, fallback = true): boolean => {
		const v = localStorage.getItem(`chatControls.${key}`);
		return v !== null ? v === 'true' : fallback;
	};
	const setOpen = (key: string) => (open: boolean) => {
		localStorage.setItem(`chatControls.${key}`, String(open));
	};

	let showFiles = getOpen('files');
	let showAdvancedParams = getOpen('advancedParams');
	let showSystemPromptField = false;
	$: if ((params?.system ?? '') !== '') showSystemPromptField = true;
</script>

<div class=" dark:text-white">
	{#if !embed}
		<div class=" flex items-center justify-between dark:text-gray-100 mb-2">
			<div class=" text-md self-center font-primary">{$i18n.t('Controls')}</div>
			<button
				class="self-center"
				aria-label={$i18n.t('Close chat controls')}
				on:click={() => {
					dispatch('close');
				}}
			>
				<XMark className="size-3.5" />
			</button>
		</div>
	{/if}

	{#if $user?.role === 'admin' || ($user?.permissions.chat?.controls ?? true)}
		<div class=" dark:text-gray-200 text-sm py-0.5 px-0.5">
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
								url={file?.url ? file.url : null}
								name={file.name}
								type={file.type}
								size={file?.size}
								dismissible={true}
								small={true}
								on:dismiss={() => {
									// Remove the file from the chatFiles array

									chatFiles.splice(fileIdx, 1);
									chatFiles = chatFiles;
								}}
								on:click={() => {
									console.log(file);
								}}
							/>
						{/each}
					</div>
				</Collapsible>

				<hr class="my-2 border-gray-50 dark:border-gray-700/10" />
			{/if}

			{#if $user?.role === 'admin' || ($user?.permissions.chat?.params ?? true)}
				<Collapsible
					title={$i18n.t('Advanced Params')}
					bind:open={showAdvancedParams}
					onChange={setOpen('advancedParams')}
					buttonClassName="w-full"
				>
					<div class="text-sm mt-1.5" slot="content">
						<div>
							<AdvancedParams admin={$user?.role === 'admin'} custom={true} separators={true} bind:params />
						</div>

						{#if $user?.role === 'admin' || ($user?.permissions.chat?.system_prompt ?? true)}
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
										class="w-full text-xs outline-hidden resize-vertical {$settings.highContrastMode
											? 'border-2 border-gray-300 dark:border-gray-700 rounded-lg bg-gray-50 dark:bg-gray-800 p-2.5'
											: 'py-1.5 bg-transparent'}"
										rows="4"
										placeholder={$i18n.t('Enter system prompt')}
									/>
								</div>
							{/if}
						{/if}
					</div>
				</Collapsible>
			{/if}
		</div>
	{/if}
</div>
