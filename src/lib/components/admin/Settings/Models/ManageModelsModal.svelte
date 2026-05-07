<script>
	import { toast } from 'svelte-sonner';

	import { createEventDispatcher, getContext, onMount } from 'svelte';
	const i18n = getContext('i18n');
	const dispatch = createEventDispatcher();

	import { user } from '$lib/stores';

	import XMark from '$lib/components/icons/XMark.svelte';
	import Modal from '$lib/components/common/Modal.svelte';
	import ManageOllama from './Manage/ManageOllama.svelte';
	import { getOllamaConfig } from '$lib/apis/ollama';
	import Spinner from '$lib/components/common/Spinner.svelte';
	import ManageMultipleOllama from './Manage/ManageMultipleOllama.svelte';

	export let show = false;

	let selected = null;
	let ollamaConfig = null;

	onMount(async () => {
		if ($user?.role === 'admin') {
			await Promise.all([
				(async () => {
					ollamaConfig = await getOllamaConfig(localStorage.token);
				})()
			]);

			if (ollamaConfig) {
				selected = 'ollama';
				return;
			}

			selected = '';
		}
	});
</script>

<Modal size="sm" bind:show>
	<div>
		<div class="flex justify-between items-center dark:text-gray-100 px-5 pt-4 pb-3 border-b border-gray-100 dark:border-gray-800">
			<div class="text-lg font-semibold font-primary">
				{$i18n.t('Manage Models')}
			</div>
			<button
				class="text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 transition"
				on:click={() => {
					show = false;
				}}
			>
				<XMark className={'size-5'} />
			</button>
		</div>

		<div class="flex flex-col w-full px-4 py-3 dark:text-gray-200">
			<div class="flex flex-col w-full">
				{#if selected === ''}
					<div class="py-5 text-gray-400 text-xs">
						<div>
							{$i18n.t('No inference engine with management support found')}
						</div>
					</div>
				{:else if selected !== null}
					<div class="flex w-full flex-col">
						<div
							class="flex gap-1 scrollbar-none overflow-x-auto w-fit text-center text-sm font-medium bg-transparent dark:text-gray-200 mb-2"
						>
							<button
								class="min-w-fit px-3 py-1.5 rounded-lg transition {selected === 'ollama'
									? 'font-semibold text-gray-900 dark:text-white bg-gray-100 dark:bg-gray-800'
									: 'text-gray-400 dark:text-gray-500 hover:text-gray-700 dark:hover:text-white'}"
								on:click={() => {
									selected = 'ollama';
								}}>{$i18n.t('Ollama')}</button
							>
						</div>

						<div class="border-t border-gray-100 dark:border-gray-800 pt-3">
							{#if selected === 'ollama'}
								<ManageMultipleOllama {ollamaConfig} />
							{/if}
						</div>
					</div>
				{:else}
					<div class="py-5">
						<Spinner />
					</div>
				{/if}
			</div>
		</div>
	</div>
</Modal>
