<script context="module" lang="ts">
	let cachedFiles: any[] | null = null;
	let cachedAllFilesLoaded = true;
</script>

<script lang="ts">
	import { modelGridWheel } from '$lib/utils/modelGridWheel';
	import { toast } from 'svelte-sonner';
	import { getContext, onMount, onDestroy } from 'svelte';
	import type { Writable } from 'svelte/store';
	import dayjs from 'dayjs';

	import { searchFiles, deleteFileById } from '$lib/apis/files';
	import Modal from '$lib/components/common/Modal.svelte';
	import MobileModalTitle from '$lib/components/common/MobileModalTitle.svelte';
	import Spinner from '$lib/components/common/Spinner.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import Loader from '$lib/components/common/Loader.svelte';
	import GarbageBin from '$lib/components/icons/GarbageBin.svelte';
	import XMark from '$lib/components/icons/XMark.svelte';
	import Search from '$lib/components/icons/Search.svelte';
	import ChevronUp from '$lib/components/icons/ChevronUp.svelte';
	import ChevronDown from '$lib/components/icons/ChevronDown.svelte';
	import ConfirmDialog from '$lib/components/common/ConfirmDialog.svelte';
	import FileItemModal from '$lib/components/common/FileItemModal.svelte';

	const i18n: Writable<any> = getContext('i18n');

	export let show = false;

	let files: any[] = cachedFiles ? [...cachedFiles] : [];
	let query = '';
	let orderBy = 'created_at';
	let direction = 'desc';

	let page = 0;
	let allFilesLoaded = cachedFiles ? cachedAllFilesLoaded : true;
	let filesLoading = false;
	let searchDebounceTimer: ReturnType<typeof setTimeout>;
	let searchRequestId = 0;

	let selectedFileId: string | null = null;
	let showDeleteConfirmDialog = false;

	let selectedFile: any = null;
	let showFileItemModal = false;

	let shiftKey = false;

	const PAGE_SIZE = 50;

	function fitRows(node: HTMLElement) {
		const resize = () => {
			const height = node.clientHeight;
			const preferred = 3.25 * parseFloat(getComputedStyle(document.documentElement).fontSize);
			if (height) node.style.setProperty('--file-row', (height / Math.max(1, Math.floor(height / preferred))) + 'px');
		};
		resize();
		const observer = new ResizeObserver(resize);
		observer.observe(node);
		return { destroy: () => observer.disconnect() };
	}

	const formatFileSize = (bytes: number): string => {
		if (bytes === 0) return '0 B';
		const k = 1024;
		const sizes = ['B', 'KB', 'MB', 'GB'];
		const i = Math.floor(Math.log(bytes) / Math.log(k));
		return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
	};

	const setSortKey = (key: string) => {
		if (orderBy === key) {
			direction = direction === 'asc' ? 'desc' : 'asc';
		} else {
			orderBy = key;
			direction = 'asc';
		}
		searchHandler();
	};

	const searchHandler = async (allowHidden = false) => {
		if (!show && !allowHidden) return;

		const requestId = ++searchRequestId;
		page = 0;

		try {
			const pattern = query ? `*${query}*` : '*';
			const newFiles = await searchFiles(localStorage.token, pattern, 0, PAGE_SIZE);
			if (requestId !== searchRequestId) return;
			files = sortFiles(newFiles);
			allFilesLoaded = newFiles.length < PAGE_SIZE;
			if (!query) {
				cachedFiles = [...files];
				cachedAllFilesLoaded = allFilesLoaded;
			}
		} catch (error) {
			if (requestId !== searchRequestId) return;
			if (!query && cachedFiles) {
				files = [...cachedFiles];
				allFilesLoaded = cachedAllFilesLoaded;
			} else {
				files = [];
				allFilesLoaded = true;
			}
		}
	};

	export const clearFiles = () => {
		clearTimeout(searchDebounceTimer);
		searchRequestId += 1;
		files = [];
		cachedFiles = [];
		cachedAllFilesLoaded = true;
		page = 0;
		allFilesLoaded = true;
		filesLoading = false;
		selectedFileId = null;
		selectedFile = null;
		showFileItemModal = false;
	};

	const loadMoreFiles = async () => {
		if (filesLoading || allFilesLoaded) return;

		const requestId = searchRequestId;
		filesLoading = true;
		page += 1;

		try {
			const pattern = query ? `*${query}*` : '*';
			const newFiles = await searchFiles(localStorage.token, pattern, page * PAGE_SIZE, PAGE_SIZE);
			if (requestId !== searchRequestId) return;

			allFilesLoaded = newFiles.length < PAGE_SIZE;

			if (newFiles.length > 0) {
				files = sortFiles([...(files || []), ...newFiles]);
			}
			if (!query) {
				cachedFiles = [...files];
				cachedAllFilesLoaded = allFilesLoaded;
			}
		} catch (error) {
			if (requestId === searchRequestId) {
				// Handle errors silently for load more
				allFilesLoaded = true;
			}
		} finally {
			if (requestId === searchRequestId) {
				filesLoading = false;
			}
		}
	};

	const sortFiles = (fileList: any[]): any[] => {
		return fileList.sort((a, b) => {
			let aVal = a[orderBy] ?? 0;
			let bVal = b[orderBy] ?? 0;

			if (orderBy === 'filename') {
				aVal = a.filename?.toLowerCase() ?? '';
				bVal = b.filename?.toLowerCase() ?? '';
			}

			if (aVal === bVal) return 0;
			if (direction === 'asc') {
				return aVal > bVal ? 1 : -1;
			} else {
				return aVal < bVal ? 1 : -1;
			}
		});
	};

	const deleteHandler = async (fileId: string) => {
		try {
			await deleteFileById(localStorage.token, fileId);
			toast.success($i18n.t('File deleted successfully.'));
			// Remove from local array instead of re-fetching to allow rapid deletion
			files = files.filter((f) => f.id !== fileId);
			if (cachedFiles) {
				cachedFiles = cachedFiles.filter((file) => file.id !== fileId);
			}
		} catch (error) {
			toast.error(`${error}`);
		}
	};

	const openFileViewer = (file: any) => {
		selectedFile = {
			id: file.id,
			name: file.filename,
			type: 'file',
			size: file.meta?.size,
			meta: file.meta
		};
		showFileItemModal = true;
	};

	// Debounce query changes
	$: if (show && query !== undefined) {
		clearTimeout(searchDebounceTimer);
		searchDebounceTimer = setTimeout(() => {
			searchHandler();
		}, query ? 300 : 0);
	}

	onMount(() => {
		void searchHandler(true);

		const onKeyDown = (event: KeyboardEvent) => {
			if (event.key === 'Shift') {
				shiftKey = true;
			}
		};

		const onKeyUp = (event: KeyboardEvent) => {
			if (event.key === 'Shift') {
				shiftKey = false;
			}
		};

		const onBlur = () => {
			shiftKey = false;
		};

		window.addEventListener('keydown', onKeyDown);
		window.addEventListener('keyup', onKeyUp);
		window.addEventListener('blur', onBlur);

		return () => {
			clearTimeout(searchDebounceTimer);
			window.removeEventListener('keydown', onKeyDown);
			window.removeEventListener('keyup', onKeyUp);
			window.removeEventListener('blur', onBlur);
		};
	});

	onDestroy(() => {
		clearTimeout(searchDebounceTimer);
	});
</script>

<ConfirmDialog
	animated={false}
	bind:show={showDeleteConfirmDialog}
	on:confirm={() => {
		if (selectedFileId) {
			deleteHandler(selectedFileId);
			selectedFileId = null;
		}
	}}
/>

<FileItemModal bind:show={showFileItemModal} item={selectedFile} edit={false} animated={false} />

{#snippet fileSearch()}
	<div class="search-field search-surface flex min-w-0 items-center gap-2 px-2.5">
		<Search className="size-3.5 shrink-0" />
		<input class="min-w-0 w-full text-sm py-1.5 outline-hidden bg-transparent" bind:value={query}
			placeholder={$i18n.t('Search files')} maxlength="500" />
		{#if query}
			<button type="button" aria-label={$i18n.t('Clear')} class="shrink-0 p-0.5 rounded-full hover:bg-gray-100 dark:hover:bg-gray-900" on:click={() => { query = ''; }}><XMark className="size-3" strokeWidth="2" /></button>
		{/if}
	</div>
{/snippet}

<Modal size="md" animated={false} bind:show>
	<div class="flex h-[33rem] max-h-[calc(100dvh-2rem)] flex-col overflow-hidden">
		<div class="grid grid-cols-2 md:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center gap-3 shrink-0 dark:text-gray-300 px-5 pt-4 pb-3">
			<div class="order-1 md:order-none text-lg font-medium self-center text-gray-700 dark:text-gray-100"><MobileModalTitle>{$i18n.t('Files')}</MobileModalTitle></div>
			<div class="order-3 md:order-none col-span-2 md:col-span-1 justify-self-center max-w-full">{@render fileSearch()}</div>
			<button data-mobile-modal-close
				class="order-2 md:order-none justify-self-end self-center"
				on:click={() => {
					show = false;
				}}
			>
				<svg
					xmlns="http://www.w3.org/2000/svg"
					viewBox="0 0 20 20"
					fill="currentColor"
					class="w-5 h-5"
				>
					<path
						fill-rule="evenodd"
						d="M6.28 5.22a.75.75 0 00-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 101.06 1.06L10 11.06l3.72 3.72a.75.75 0 101.06-1.06L11.06 10l3.72-3.72a.75.75 0 00-1.06-1.06L10 8.94 6.28 5.22z"
						clip-rule="evenodd"
					/>
				</svg>
			</button>
		</div>

		<div class="flex min-h-0 flex-1 flex-col w-full px-5 pt-2 pb-3 dark:text-gray-200">
			<!-- Files List -->
			<div class="flex min-h-0 flex-1 flex-col w-full">
				<div class="flex min-h-0 flex-1 flex-col w-full">
					{#if files.length > 0}
						<div class="flex text-xs font-medium mb-1.5">
							<button
								class="px-1.5 py-1 cursor-pointer select-none basis-3/5"
								on:click={() => setSortKey('filename')}
							>
								<div class="flex gap-1.5 items-center">
									{$i18n.t('Filename')}
									{#if orderBy === 'filename'}
										<span class="font-normal">
											{#if direction === 'asc'}
												<ChevronUp className="size-2" />
											{:else}
												<ChevronDown className="size-2" />
											{/if}
										</span>
									{:else}
										<span class="invisible">
											<ChevronUp className="size-2" />
										</span>
									{/if}
								</div>
							</button>
							<button
								class="px-1.5 py-1 cursor-pointer select-none hidden sm:flex sm:basis-2/5 justify-end"
								on:click={() => setSortKey('created_at')}
							>
								<div class="flex gap-1.5 items-center">
									{$i18n.t('Created at')}
									{#if orderBy === 'created_at'}
										<span class="font-normal">
											{#if direction === 'asc'}
												<ChevronUp className="size-2" />
											{:else}
												<ChevronDown className="size-2" />
											{/if}
										</span>
									{:else}
										<span class="invisible">
											<ChevronUp className="size-2" />
										</span>
									{/if}
								</div>
							</button>
						</div>
					{/if}

					<div use:modelGridWheel use:fitRows data-model-grid class="files-list-scroll overscroll-contain [scrollbar-gutter:stable] [overflow-anchor:none] min-h-0 flex-1 text-left text-sm mb-1 overflow-y-auto -mr-3 pr-3">
						{#if files.length === 0}
							<div
								class="text-xs text-gray-500 dark:text-gray-400 text-center px-5 min-h-20 w-full h-full flex justify-center items-center"
							>
								{$i18n.t('No files found')}
							</div>
						{/if}

						{#each files as file (file.id)}
							<div
								class="w-full flex h-[var(--file-row)] justify-between items-center rounded-lg text-sm py-2 px-3 hover:bg-gray-50 dark:hover:bg-gray-850 cursor-pointer"
								on:click={() => openFileViewer(file)}
							>
								<div class="basis-3/5 min-w-0">
									<div class="text-ellipsis line-clamp-1">{file.filename}</div>
									<div class="text-xs text-gray-500">
										{formatFileSize(file.meta?.size ?? 0)}
									</div>
								</div>

								<div class="basis-2/5 flex items-center justify-end">
									<div class="hidden sm:flex text-gray-500 dark:text-gray-400 text-xs">
										{dayjs(file.created_at * 1000).format('D MMM, YYYY')}
									</div>

									<div class="flex justify-end pl-2.5 text-gray-600 dark:text-gray-300">
										<Tooltip content={$i18n.t('Delete')}>
											<button
												aria-label={$i18n.t('Delete')}
												class="grid size-8 place-items-center self-center rounded-lg hover:bg-black/5 dark:hover:bg-white/5 {shiftKey
													? 'text-red-500'
													: ''}"
												on:click|stopPropagation={() => {
													if (shiftKey) {
														deleteHandler(file.id);
													} else {
														selectedFileId = file.id;
														showDeleteConfirmDialog = true;
													}
												}}
											>
														<GarbageBin className="size-4" strokeWidth="1.5" />
											</button>
										</Tooltip>
									</div>
								</div>
							</div>
						{/each}

						{#if !allFilesLoaded}
							<Loader
								on:visible={() => {
									if (!filesLoading) {
										loadMoreFiles();
									}
								}}
							>
								<div class="py-1"></div>
							</Loader>
						{/if}
					</div>
				</div>
			</div>
		</div>
	</div>
</Modal>
