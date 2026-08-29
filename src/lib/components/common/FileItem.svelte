<script lang="ts">
	import { createEventDispatcher, getContext } from 'svelte';
	import { NEVEAI_API_BASE_URL } from '$lib/constants';
	import { getFileContentById } from '$lib/apis/files';

	import { formatFileSize } from '$lib/utils';
	import { settings } from '$lib/stores';

	import FileItemModal from './FileItemModal.svelte';
	import GarbageBin from '../icons/GarbageBin.svelte';
	import Spinner from './Spinner.svelte';
	import XMark from '$lib/components/icons/XMark.svelte';
	import AttachmentFile from '$lib/components/icons/AttachmentFile.svelte';

	const i18n = getContext('i18n');
	const dispatch = createEventDispatcher();

	export let className = 'w-44';
	export let colorClassName =
		'bg-white dark:bg-gray-850 border border-gray-50/30 dark:border-gray-800/30';
	export let url: string | null = null;

	export let dismissible = false;
	export let modal = false;
	export let loading = false;

	export let item = null;
	export let edit = false;
	export let small = false;
	export let inputChip = false;

	export let name: string;
	export let type: string;
	export let size: number;

	import Database from '../icons/Database.svelte';
	import PageEdit from '../icons/PageEdit.svelte';
	import ChatBubble from '../icons/ChatBubble.svelte';
	import Folder from '../icons/Folder.svelte';
	let showModal = false;

	const decodeString = (str: string) => {
		try {
			return decodeURIComponent(str);
		} catch (e) {
			return str;
		}
	};

	$: contentType =
		item?.content_type ??
		item?.meta?.content_type ??
		item?.file?.meta?.content_type ??
		item?.file?.content_type ??
		(type?.includes('/') ? type : '');

	const downloadGeneratedFile = async () => {
		const content = await getFileContentById(item.id);
		if (!content) return;

		const blobUrl = URL.createObjectURL(
			new Blob([content], { type: contentType || 'application/octet-stream' })
		);
		const anchor = document.createElement('a');
		anchor.href = blobUrl;
		anchor.download = item?.name ?? item?.meta?.name ?? name ?? 'arquivo';
		anchor.style.display = 'none';
		document.body.appendChild(anchor);
		anchor.click();
		anchor.remove();
		setTimeout(() => URL.revokeObjectURL(blobUrl), 1000);
	};
</script>

{#if item}
	<FileItemModal bind:show={showModal} bind:item {edit} />
{/if}

{#if item?.generated}
	<div class="relative group {className}">
		<button
			type="button"
			class="flex h-12 w-full items-center gap-2.5 rounded-lg bg-gray-100 px-3 pr-11 text-left text-gray-800 transition hover:bg-gray-200/80 dark:bg-gray-800 dark:text-gray-100 dark:hover:bg-gray-700"
			on:click={() => {
				showModal = true;
				dispatch('click');
			}}
		>
			<div
				class="flex size-7 shrink-0 items-center justify-center text-blue-500 dark:text-blue-400"
			>
				<AttachmentFile {name} {contentType} className="size-4.5" />
			</div>
			<div class="min-w-0 flex-1 truncate text-sm font-normal">
				{decodeString(name)}
			</div>
		</button>
		<button
			type="button"
			aria-label={$i18n.t('Download')}
			class="absolute right-3 top-1/2 flex size-7 -translate-y-1/2 items-center justify-center rounded-md text-gray-600 transition hover:bg-black/5 hover:text-gray-900 dark:text-gray-300 dark:hover:bg-white/10 dark:hover:text-white"
			on:click|stopPropagation={downloadGeneratedFile}
		>
			<svg
				aria-hidden="true"
				xmlns="http://www.w3.org/2000/svg"
				fill="none"
				viewBox="0 0 24 24"
				stroke-width="2"
				stroke="currentColor"
				class="size-4"
			>
				<path
					stroke-linecap="round"
					stroke-linejoin="round"
					d="M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2M7 11l5 5 5-5M12 4v12"
				/>
			</svg>
		</button>
	</div>
{:else}
	<div class="relative group {className}">
		<button
			class="w-full flex items-center gap-1 {inputChip
				? 'bg-gray-100/90 dark:bg-gray-800/80 border border-gray-200/70 dark:border-gray-700/50 text-gray-700 dark:text-gray-200 hover:bg-gray-200/80 dark:hover:bg-gray-700/70'
				: colorClassName} {small
				? inputChip
					? 'h-8 min-h-8 max-h-8 rounded-lg px-1.5 py-1'
					: 'rounded-lg p-1.5'
				: 'rounded-xl p-1.5'} text-left"
			type="button"
			on:click={async () => {
				if (item?.file?.data?.content || item?.type === 'file' || item?.content || modal) {
					showModal = !showModal;
				} else {
					if (url) {
						if (type === 'file') {
							if (url.startsWith('http')) {
								window.open(`${url}/content`, '_blank').focus();
							} else {
								window.open(`${NEVEAI_API_BASE_URL}/files/${url}/content`, '_blank').focus();
							}
						} else {
							window.open(`${url}`, '_blank').focus();
						}
					}
				}

				dispatch('click');
			}}
		>
			{#if !small}
				<div
					class="size-10 shrink-0 flex justify-center items-center bg-gray-100 dark:bg-gray-800 rounded-lg"
				>
					{#if !loading}
						<AttachmentFile {name} {contentType} className="size-5" />
					{:else}
						<Spinner />
					{/if}
				</div>
			{:else}
				<div class="pl-1 shrink-0">
					{#if !loading}
						{#if type === 'collection'}
							<Database />
						{:else if type === 'note'}
							<PageEdit />
						{:else if type === 'chat'}
							{#if inputChip}
								<svg
									aria-hidden="true"
									xmlns="http://www.w3.org/2000/svg"
									fill="none"
									viewBox="0 0 24 24"
									stroke-width="1.7"
									stroke="currentColor"
									class="size-3.5"
								>
									<path
										stroke-linecap="round"
										stroke-linejoin="round"
										d="M20.25 11.5c0 4.14-3.69 7.5-8.25 7.5-1.08 0-2.1-.19-3.02-.53L4.5 20.25l1.25-3.43C4.5 15.47 3.75 13.64 3.75 11.5 3.75 7.36 7.44 4 12 4s8.25 3.36 8.25 7.5Z"
									/>
								</svg>
							{:else}
								<ChatBubble />
							{/if}
						{:else if type === 'folder'}
							<Folder />
						{:else}
							<AttachmentFile {name} {contentType} className={inputChip ? 'size-3.5' : 'size-4'} />
						{/if}
					{:else}
						<Spinner className={inputChip ? 'size-3.5' : 'size-4'} />
					{/if}
				</div>
			{/if}

			{#if !small}
				<div class="flex flex-col justify-center -space-y-0.5 px-2.5 w-full">
					<div class=" dark:text-gray-100 text-sm font-medium line-clamp-1 mb-1">
						{decodeString(name)}
					</div>

					<div
						class=" flex justify-between text-xs line-clamp-1 {($settings?.highContrastMode ??
						false)
							? 'text-gray-800 dark:text-gray-100'
							: 'text-gray-500'}"
					>
						{#if type === 'file'}
							{$i18n.t('File')}
						{:else if type === 'note'}
							{$i18n.t('Note')}
						{:else if type === 'doc'}
							{$i18n.t('Document')}
						{:else if type === 'collection'}
							{$i18n.t('Collection')}
						{:else if type !== 'chat'}
							<span class=" capitalize line-clamp-1">{type}</span>
						{/if}
						{#if size}
							<span class="capitalize">{formatFileSize(size)}</span>
						{/if}
					</div>
				</div>
			{:else}
				<div class="flex flex-col w-full min-w-0">
					<div class="flex flex-col justify-center w-full min-w-0 {inputChip ? 'px-0.5' : 'px-1'}">
						<div class="dark:text-gray-100 text-xs flex justify-between items-center gap-1">
							<div class="line-clamp-1 flex-1 min-w-0">{decodeString(name)}</div>
							{#if dismissible}
								<button
									type="button"
									aria-label={$i18n.t('Remove File')}
									class="hidden group-hover:flex items-center justify-center text-gray-300 hover:text-gray-400 dark:text-gray-600 dark:hover:text-gray-500 transition shrink-0"
									on:click|stopPropagation={() => dispatch('dismiss')}
								>
									<XMark className="size-3.5" />
								</button>
								<div
									class="group-hover:hidden text-gray-400 dark:text-gray-500 text-xs capitalize shrink-0"
								>
									{#if size}{formatFileSize(size)}{:else if type !== 'chat'}{type}{/if}
								</div>
							{:else if size}
								<div class="text-gray-400 text-xs capitalize shrink-0">{formatFileSize(size)}</div>
							{:else if type !== 'chat'}
								<div class="text-gray-400 text-xs capitalize shrink-0">{type}</div>
							{/if}
						</div>
					</div>
				</div>
			{/if}
		</button>
	</div>
{/if}
