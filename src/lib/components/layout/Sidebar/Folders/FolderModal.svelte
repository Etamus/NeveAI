<script lang="ts">
	import { getContext, createEventDispatcher, onMount, tick } from 'svelte';

	import Spinner from '$lib/components/common/Spinner.svelte';
	import Modal from '$lib/components/common/Modal.svelte';
	import XMark from '$lib/components/icons/XMark.svelte';

	import { toast } from 'svelte-sonner';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { user, config } from '$lib/stores';

	import Textarea from '$lib/components/common/Textarea.svelte';
	import { getFolderById } from '$lib/apis/folders';
	const i18n = getContext('i18n');

	export let show = false;
	export let onSubmit: Function = (e) => {};

	export let folderId = null;
	export let parentId = null;
	export let edit = false;

	let folder = null;
	let name = '';
	let meta = {
		background_image_url: null
	};
	let data = {
		system_prompt: '',
		files: []
	};

	let loading = false;

	const submitHandler = async () => {
		loading = true;

		if ((data?.files ?? []).some((file) => file.status === 'uploading')) {
			toast.error($i18n.t('Please wait until all files are uploaded.'));
			loading = false;
			return;
		}

		// Check folder max file count limit
		const maxFileCount = $config?.features?.folder_max_file_count ?? '';
		if (maxFileCount && (data?.files ?? []).length > maxFileCount) {
			toast.error(
				$i18n.t('Maximum number of files per folder is {{max}}.', { max: maxFileCount ?? 0 })
			);
			loading = false;
			return;
		}

		await onSubmit({
			name,
			meta,
			data,
			parent_id: edit ? undefined : parentId
		});
		show = false;
		loading = false;
	};

	const init = async () => {
		if (folderId) {
			folder = await getFolderById(localStorage.token, folderId).catch((error) => {
				toast.error(`${error}`);
				return null;
			});

			name = folder.name;
			meta = folder.meta || {
				background_image_url: null
			};
			data = folder.data || {
				system_prompt: '',
				files: []
			};
		}

		focusInput();
	};

	const focusInput = async () => {
		await tick();
		const input = document.getElementById('folder-name') as HTMLInputElement;
		if (input) {
			input.focus();
			input.select();
		}
	};

	$: if (show) {
		init();
	}

	$: if (!show && !edit) {
		name = '';
		meta = {
			background_image_url: null
		};
		data = {
			system_prompt: '',
			files: []
		};
	}
</script>

<Modal size="sm" bind:show>
	<div>
		<div class="flex justify-between items-center px-5 pt-4 pb-3 border-b border-gray-200/30 dark:border-gray-700/20">
			<div class="text-lg font-semibold dark:text-gray-100">
				{#if edit}
					{$i18n.t('Editar projeto')}
				{:else}
					{$i18n.t('Criar projeto')}
				{/if}
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

		<div class="flex flex-col w-full px-5 py-4 dark:text-gray-200">
			<form
				class="flex flex-col w-full"
				on:submit|preventDefault={() => {
					submitHandler();
				}}
			>
				<div
					class="flex flex-col gap-3 px-3.5 py-3 border border-gray-100 dark:border-gray-850 rounded-xl"
				>
					<div class="flex flex-col">
						<div class="text-xs text-gray-500 mb-1">{$i18n.t('Nome do projeto')}</div>
						<input
							id="folder-name"
							class="w-full text-sm bg-transparent outline-hidden placeholder:text-gray-300 dark:placeholder:text-gray-700"
							type="text"
							bind:value={name}
							placeholder={$i18n.t('Digite o nome do projeto')}
							autocomplete="off"
						/>
					</div>
				</div>

				<div class="flex justify-end pt-4 text-sm font-medium gap-1.5">
					<button
					class="px-4 py-1.5 text-xs font-medium bg-black hover:opacity-90 text-white dark:bg-white dark:text-black transition rounded-lg flex flex-row space-x-1 items-center {loading
							? ' cursor-not-allowed'
							: ''}"
						type="submit"
						disabled={loading}
					>
						{edit ? $i18n.t('Editar') : $i18n.t('Criar')}

						{#if loading}
							<div class="ml-2 self-center">
								<Spinner />
							</div>
						{/if}
					</button>
				</div>
			</form>
		</div>
	</div>
</Modal>
