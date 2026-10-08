<script lang="ts">
	import { getContext, onMount, onDestroy } from 'svelte';
	import { getGeneratedFiles } from '$lib/apis/files';
	import { NEVEAI_API_BASE_URL } from '$lib/constants';
	import FileItemModal from '$lib/components/common/FileItemModal.svelte';
	import Document from '$lib/components/icons/Document.svelte';
	import MusicNote from '$lib/components/icons/MusicNote.svelte';
	import DocumentThumbnail from '$lib/components/common/DocumentThumbnail.svelte';
	import Sidebar from '$lib/components/icons/Sidebar.svelte';
	import { mobile, showSidebar } from '$lib/stores';
	const i18n = getContext('i18n');
	const tabs = [
		{ id: 'all', label: 'All' },
		{ id: 'image', label: 'Images' },
		{ id: 'video', label: 'Videos' },
		{ id: 'audio', label: 'Music' },
		{ id: 'document', label: 'Documents' }
	];
	let kind = 'all';
	let files: any[] = [];
	let loading = true;
	let hasMore = false;
	let error = '';
	let selectedFile: any = null;
	let showViewer = false;
	let timer: ReturnType<typeof setTimeout>;
	let requestId = 0;
	let mounted = false;
	const url = (file: any) => `${NEVEAI_API_BASE_URL}/files/${file.id}/content`;
	const mediaKind = (file: any) => (file.meta?.content_type ?? '').split('/')[0];
	$: visibleFiles = files.filter(
		(file) =>
			kind === 'all' ||
			(kind === 'document'
				? !['image', 'video', 'audio'].includes(mediaKind(file))
				: mediaKind(file) === kind)
	);
	const load = async (more = false, preservePages = false) => {
		const id = ++requestId;
		const requestedKind = kind;
		const pageCount = preservePages ? Math.max(1, Math.ceil(files.length / 50)) : 1;
		const start = more ? files.length : 0;
		loading = true;
		error = '';
		try {
			const results: any[] = [];
			let lastPage: any[] = [];
			for (let page = 0; page < pageCount; page++) {
				lastPage = await getGeneratedFiles(localStorage.token, requestedKind, '', start + page * 50);
				if (id !== requestId) return;
				results.push(...lastPage);
				if (lastPage.length < 50) break;
			}
			// Commit the refreshed window together so later pages never disappear between requests.
			files = [
				...new Map((more ? [...files, ...results] : results).map((file) => [file.id, file])).values()
			];
			hasMore = lastPage.length === 50;
		} catch (cause) {
			if (id === requestId) error = String(cause);
		} finally {
			if (id === requestId) loading = false;
		}
	};
	$: if (mounted) {
		kind;
		clearTimeout(timer);
		timer = setTimeout(() => load(), 0);
	}
	const open = (file: any) => {
		selectedFile = {
			id: file.id,
			name: file.filename,
			type: 'file',
			meta: file.meta,
			size: file.meta?.size
		};
		showViewer = true;
	};
	const refresh = () => {
		if (!document.hidden && !showViewer && !loading) void load(false, true);
	};
	onMount(() => {
		mounted = true;
		window.addEventListener('focus', refresh);
		const filesChanged = () => {
			void load(false, true);
		};
		window.addEventListener('neve:files-changed', filesChanged);
		document.addEventListener('visibilitychange', refresh);
		const poll = setInterval(refresh, 15000);
		return () => {
			clearInterval(poll);
			window.removeEventListener('focus', refresh);
			window.removeEventListener('neve:files-changed', filesChanged);
			document.removeEventListener('visibilitychange', refresh);
		};
	});
	onDestroy(() => {
		clearTimeout(timer);
		requestId++;
	});
</script>

<div class="h-full flex flex-col bg-white dark:bg-black text-gray-900 dark:text-gray-100">
	<header class="flex flex-wrap items-center gap-3 px-5 py-4 shrink-0">
		{#if $mobile}
			<button type="button" class="grid size-9 place-items-center rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800" aria-label={$i18n.t('Open Sidebar')} on:click={() => showSidebar.set(true)}><Sidebar className="size-5" /></button>
		{/if}
		<h1 class="text-xl font-semibold whitespace-nowrap shrink-0">{$i18n.t('Library')}</h1>
	</header>
	<nav class="flex gap-1 px-5 pb-4 overflow-x-auto shrink-0" aria-label={$i18n.t('Library')}>
		{#each tabs as tab}<button
				class="px-3 py-1.5 rounded-lg text-sm font-medium whitespace-nowrap {kind === tab.id
					? 'bg-gray-100 dark:bg-gray-800'
					: 'text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-900'}"
				aria-pressed={kind === tab.id}
				on:click={() => {
					if (kind !== tab.id) {
						requestId++;
						loading = true;
						kind = tab.id;
					}
				}}>{$i18n.t(tab.label)}</button
			>{/each}
	</nav>
	<main class="flex-1 min-h-0 overflow-y-auto px-5 pb-6">
		{#if error}<div role="alert" class="py-8 text-sm text-gray-500">
				{error} <button class="underline" on:click={() => load(false, true)}>{$i18n.t('Retry')}</button>
			</div>{/if}
		{#if visibleFiles.length === 0 && !error && !loading}<p
				class="py-12 text-center text-sm text-gray-500"
			>
				{$i18n.t('No creations yet')}
			</p>{/if}
		<div class="library-grid">
			{#each visibleFiles as file (file.id)}
				<article class="overflow-hidden rounded-2xl">
					<button
						class="library-item block w-full text-left relative overflow-hidden rounded-2xl aspect-[4/3] bg-gray-100 dark:bg-gray-850"
						on:click={() => open(file)}
						aria-label={file.filename}
					>
						<div class="h-full w-full overflow-hidden flex items-center justify-center">
							{#if mediaKind(file) === 'image'}<img
									src={url(file)}
									alt={file.filename}
									loading="lazy"
									class="size-full object-cover"
								/>
							{:else if mediaKind(file) === 'video'}<video
									src={url(file)}
									preload="metadata"
									muted
									playsinline
									class="size-full object-cover"><track kind="captions" /></video
								>
							{:else if mediaKind(file) === 'audio'}<MusicNote className="size-12 text-gray-500" />
							{:else}<div class="h-full w-full flex flex-col min-w-0">
									<div
										class="flex items-center gap-2 px-3 py-2.5 border-b border-gray-200/70 dark:border-gray-700/50 shrink-0"
									>
										<Document className="size-4 shrink-0 text-gray-500" /><span
											class="truncate text-xs font-medium"
											title={file.filename}>{file.filename}</span
										>
									</div>
									<div class="flex-1 min-h-0"><DocumentThumbnail {file} /></div>
								</div>{/if}
						</div>
					</button>
				</article>
			{/each}
		</div>
		{#if hasMore}<div class="flex justify-center pt-5">
				<button
					class="text-sm px-4 py-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800"
					disabled={loading}
					on:click={() => load(true)}>{$i18n.t('Load more')}</button
				>
			</div>{/if}
	</main>
</div>
{#if showViewer}<FileItemModal item={selectedFile} bind:show={showViewer} />{/if}

<style>
	@media (max-width: 767px) {
		header { padding-inline: 0.875rem; }
		nav { padding-inline: 0.875rem; flex-wrap: wrap; }
		nav button { padding-inline: 0.5rem; font-size: 0.75rem; min-height: 36px; }
		main { padding-inline: 0.875rem; padding-bottom: max(1rem, env(safe-area-inset-bottom, 0px)); }
		main .library-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
	}
	.library-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(min(100%, 210px), 1fr));
		gap: 16px;
	}
	.library-item {
		transition:
			filter 140ms ease,
			box-shadow 140ms ease;
	}
	.library-item:hover {
		filter: brightness(0.88);
		box-shadow: inset 0 0 0 2px rgb(128 128 128 / 35%);
	}
	.library-item:focus-visible {
		outline: 2px solid #888;
		outline-offset: 3px;
	}
</style>
