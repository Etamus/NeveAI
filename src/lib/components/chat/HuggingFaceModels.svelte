<script lang="ts">
	import { getContext, onDestroy, tick } from 'svelte';
	import { searchHFModels, getHFModelFiles, type HFModel, type HFModelFile } from '$lib/apis/llamacpp';
	import { hfDownloadKey, type ModelDownloadRequest } from '$lib/utils/modelDownloadRequest';
	import { DropdownMenu } from 'bits-ui';
	import Dropdown from '$lib/components/common/Dropdown.svelte';
	import ChevronDown from '$lib/components/icons/ChevronDown.svelte';
	import ChevronUpCompact from '$lib/components/icons/ChevronUpCompact.svelte';
	import CheckCircle from '$lib/components/icons/CheckCircle.svelte';
	import type { I18nStore } from '$lib/i18n';
	import HuggingFace from '$lib/components/icons/HuggingFace.svelte';
	import ChevronLeft from '$lib/components/icons/ChevronLeft.svelte';
	import ChevronRight from '$lib/components/icons/ChevronRight.svelte';
	import Download from '$lib/components/icons/ModelDownload.svelte';
	import Spinner from '$lib/components/common/Spinner.svelte';
	const i18n = getContext<I18nStore>('i18n');
	export let query = '';
	export let active = false;
	export let detailOpen = false;
	export let hasResults = false;
	export let settledQuery: string | null = null;
	export let collapsible = true;
	export let onStickyChange: (stuck: boolean) => void = () => {};
	export let stickyActive = false;
	function observeSectionStart(element: HTMLElement, enabled: boolean) {
		const root = element.closest<HTMLElement>('[data-download-list]');
		if (!root || typeof IntersectionObserver === 'undefined') return;
		let observer: IntersectionObserver | undefined;
		let active = enabled, disposed = false, scheduled = false;
		const rebuild = () => {
			if (!active || disposed || scheduled) return;
			scheduled = true;
			void tick().then(() => {
				scheduled = false;
				if (!active || disposed) return;
				observer?.disconnect();
				// Observe the top edge even when a fast scroll skips the entire viewport.
				observer = new IntersectionObserver(([entry]) => {
					onStickyChange(Boolean(entry.rootBounds && entry.boundingClientRect.top < entry.rootBounds.top));
				}, { root, rootMargin: `0px 0px ${root.scrollHeight}px 0px`, threshold: [0, 1] });
				observer.observe(element);
			});
		};
		const resize = typeof ResizeObserver === 'undefined' ? undefined : new ResizeObserver(rebuild);
		const update = (value: boolean) => {
			active = value;
			resize?.disconnect(); observer?.disconnect();
			if (!active) { onStickyChange(false); return; }
			resize?.observe(root);
			const precedingSection = root.querySelector('section');
			if (precedingSection) resize?.observe(precedingSection);
			rebuild();
		};
		update(enabled);
		return { update, destroy() { disposed = true; resize?.disconnect(); observer?.disconnect(); onStickyChange(false); } };
	}
	export let activeKey: string | null = null;
	export let activeRequest: ModelDownloadRequest | undefined = undefined;
	export let queuedRequests: ModelDownloadRequest[] = [];
	let repoFiles: Record<string, HFModelFile[]> = {};
	export let queuedKeys: string[] = [];
	export let blocked = false;
	export let revision = 0;
	export let onQueue: (request: ModelDownloadRequest) => void;
	const cacheKey = 'neveai.hf.catalog.v1';
	let models: HFModel[] = [];
	let nextCursor: string | null = null;
	try { const cached = JSON.parse(localStorage.getItem(cacheKey) ?? 'null'); if (Array.isArray(cached?.models)) { models = cached.models.filter((row: HFModel) => typeof row?.id === 'string' && row.id.includes('/')).slice(0, 24); nextCursor = typeof cached.next_cursor === 'string' ? cached.next_cursor : null; } } catch { /* Empty cache is valid. */ }
	const pages = new Map<string, { models: HFModel[]; next_cursor: string | null }>();
	if (models.length) pages.set('', { models: [...models], next_cursor: nextCursor });
	let loading = false, lastQuery: string | null = null, generation = 0;
	let request: AbortController | null = null;
	let timer: ReturnType<typeof setTimeout>;
	let selectedRepo: HFModel | null = null;
	let files: HFModelFile[] = [], encoders: HFModelFile[] = [], encoder = '';
	let filesLoading = false, encoderMenu = false;
	let fileRequest: AbortController | null = null;
	let fileGeneration = 0;
	let lastRevision = revision;
	export function markInstalled(request: ModelDownloadRequest | undefined) {
		if (request?.source !== 'hf') return;
		const mark = (items: HFModelFile[]) => items.map(file => file.path === request.filename ? { ...file, installed: true } : file);
		if (selectedRepo?.id === request.repo) {
			// A pre-completion response must not overwrite the terminal download state.
			fileRequest?.abort(); fileGeneration++; filesLoading = false;
			files = mark(files);
		}
		repoFiles = { ...repoFiles, [request.repo]: mark(repoFiles[request.repo] ?? []) };
	}
	let expanded = true;
	$: if (!collapsible) expanded = true;
	let unavailable = false;
	let retryAttempt = 0;
	let retryTimer: ReturnType<typeof setTimeout>;
	$: detailOpen = selectedRepo !== null;
	$: hasResults = !unavailable && models.length > 0;
	function stopRequests() { clearTimeout(timer); clearTimeout(retryTimer); request?.abort(); fileRequest?.abort(); generation++; fileGeneration++; loading = false; filesLoading = false; lastQuery = null; }
	function scheduleRetry(search: string) {
		clearTimeout(retryTimer);
		if (!active || search !== query.trim()) return;
		retryTimer = setTimeout(() => { if (active && search === query.trim()) void load(search); }, Math.min(60000, 15000 * 2 ** Math.min(retryAttempt++, 2)));
	}
	$: if (!active) stopRequests();
	$: if (active && lastQuery !== query.trim()) {
		lastQuery = query.trim();
		loading = true;
		clearTimeout(timer);
		clearTimeout(retryTimer); retryAttempt = 0; unavailable = false;
		request?.abort();
		generation++;
		fileRequest?.abort(); fileGeneration++; filesLoading = false; selectedRepo = null;
		const cached = pages.get(lastQuery);
		if (cached) { models = cached.models; nextCursor = cached.next_cursor; }
		else { models = []; nextCursor = null; }
		const search = lastQuery;
		timer = setTimeout(() => load(search), search ? 250 : 0);
	}
	$: if (revision !== lastRevision) { lastRevision = revision; if (selectedRepo) void open(selectedRepo); }
	async function load(search: string, cursor = '') {
		clearTimeout(retryTimer);
		request?.abort(); const controller = request = new AbortController(); const id = ++generation;
		loading = true;
		try {
			const data = await searchHFModels(localStorage.token, search, cursor, controller.signal);
			if (id !== generation) return;
			models = cursor ? [...new Map([...models, ...data.models].map(model => [model.id, model])).values()] : data.models;
			nextCursor = data.next_cursor;
			unavailable = models.length === 0;
			settledQuery = search;
			if (unavailable) scheduleRetry(search); else retryAttempt = 0;
			if (!cursor) { pages.set(search, data); while (pages.size > 8) pages.delete(pages.keys().next().value!); }
			if (!search && !cursor) try { localStorage.setItem(cacheKey, JSON.stringify(data)); } catch { /* Storage may be full. */ }
		} catch { if (id === generation && !controller.signal.aborted) { unavailable = true; settledQuery = search; scheduleRetry(search); } }
		finally { if (id === generation) loading = false; }
	}
	async function open(repo: HFModel) {
		fileRequest?.abort(); const controller = fileRequest = new AbortController(); const id = ++fileGeneration;
		if (selectedRepo?.id !== repo.id) { files = []; encoders = []; encoder = ''; }
		selectedRepo = repo; filesLoading = true;
		try {
			const data = await getHFModelFiles(localStorage.token, repo.id, controller.signal);
			if (id !== fileGeneration) return;
			files = data.models; encoders = data.encoders;
			repoFiles = { ...repoFiles, [repo.id]: data.models };
			if (encoder && !encoders.some(file => file.path === encoder)) encoder = '';
		} catch { if (id === fileGeneration && !controller.signal.aborted) back(); }
		finally { if (id === fileGeneration) filesLoading = false; }
	}
	function back() { fileRequest?.abort(); fileGeneration++; filesLoading = false; selectedRepo = null; }
	function start(file: HFModelFile) {
		if (!selectedRepo || file.installed || blocked) return;
		onQueue({ source: 'hf', repo: selectedRepo.id, filename: file.path, encoder: encoder || undefined, name: selectedRepo.id });
	}
	const size = (bytes: number) => `${(bytes / 1024 ** 3).toFixed(2)} GB`;
	onDestroy(() => { clearTimeout(timer); clearTimeout(retryTimer); request?.abort(); fileRequest?.abort(); });
</script>

<svelte:window on:online={() => { if (active) void load(query.trim()); }} />

{#if selectedRepo || (!unavailable && models.length > 0)}
<div class={selectedRepo ? 'flex h-full min-h-0 flex-col' : 'min-w-0'} data-hf-catalog>
	{#if !selectedRepo}
		<div aria-hidden="true" class="pointer-events-none h-px -mb-px" use:observeSectionStart={active}></div>
		<div data-catalog-section-heading class="sticky top-0 h-10 bg-white dark:bg-gray-900 {stickyActive ? 'z-30' : 'z-10'}">
		<button type="button" data-hf-section-toggle disabled={!collapsible} aria-expanded={expanded} aria-controls="hf-catalog-items" class="mb-2 flex h-8 items-center gap-2 px-3 text-sm text-gray-500 dark:text-gray-400 disabled:cursor-default" on:click={() => { if (collapsible) expanded = !expanded; }}>
			<HuggingFace className="size-5 shrink-0" /><span>Hugging Face</span>{#if collapsible}<span class="relative top-px inline-flex shrink-0"><ChevronUpCompact className={`size-3.5 shrink-0 transition-transform ${expanded ? '' : 'rotate-180'}`} /></span>{/if}
		</button>
		</div>
	{/if}
	{#if selectedRepo}
		<div data-hf-model-header class="mb-3 flex h-8 min-w-0 shrink-0 items-center justify-between gap-2">
			<div class="flex min-w-0 flex-1 items-center gap-2"><button type="button" class="grid size-7 shrink-0 place-items-center rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800" aria-label={$i18n.t('Back to models')} title={$i18n.t('Back to models')} on:click={back}><ChevronLeft className="size-4" /></button>
			<span data-hf-model-name class="truncate text-sm font-medium">{selectedRepo.id}</span></div>
			{#if encoders.length}
				<Dropdown bind:show={encoderMenu} align="end" triggerClassName="flex max-w-[55%] shrink-0 items-center gap-1.5 rounded-full px-2.5 py-1.5 text-[0.79rem] font-normal text-gray-600 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-800">
					<span data-vision-selector class="min-w-0 truncate">{encoder || $i18n.t('Multimodal vision')}</span><ChevronDown className={`size-3 shrink-0 transition-transform ${encoderMenu ? 'rotate-180' : ''}`} />
					<div slot="content"><DropdownMenu.Content class="z-[10002] max-h-56 w-72 max-w-[calc(100vw-2rem)] overflow-y-auto rounded-md border border-gray-100 bg-white p-1 text-sm text-gray-700 shadow-md dark:border-gray-800 dark:bg-gray-850 dark:text-gray-200" side="bottom" align="end" sideOffset={5}>
						{#each [{ path: '', size: 0 }, ...encoders] as option}
							<DropdownMenu.Item role="menuitemradio" aria-checked={encoder === option.path} class="flex cursor-pointer select-none items-center justify-between gap-3 rounded-sm px-3 py-1.5 hover:bg-gray-100 dark:hover:bg-gray-800" on:click={() => { encoder = option.path; encoderMenu = false; }}><span class="min-w-0 truncate">{option.path ? `${option.path} (${size(option.size)})` : $i18n.t('None')}</span><span class="size-4 shrink-0">{#if encoder === option.path}<CheckCircle className="size-4" />{/if}</span></DropdownMenu.Item>
						{/each}
					</DropdownMenu.Content></div>
				</Dropdown>
			{/if}
		</div>
	{/if}
	{#if selectedRepo || expanded}
	<div id="hf-catalog-items" data-hf-model-list class={selectedRepo ? 'min-h-0 flex-1 overflow-y-auto overscroll-contain pr-2 [scrollbar-gutter:stable]' : 'min-w-0'}>
		{#if selectedRepo}
			{#if filesLoading && !files.length}<div class="flex h-24 items-center justify-center"><Spinner className="size-5" /></div>
			{:else}
				<div class="grid grid-cols-1 gap-2 md:grid-cols-2" aria-label={$i18n.t('Quantization')}>
					{#each files as file (file.path)}
						{@const key = hfDownloadKey(selectedRepo.id, file.path)}
						{@const current = key === activeKey}
						{@const queued = queuedKeys.includes(key)}
						<div data-hf-file={file.path} tabindex="-1" role="group" aria-label={file.path} class="flex min-h-[64px] min-w-0 items-center justify-between gap-3 rounded-lg border bg-gray-50 dark:bg-gray-850/50 px-3 py-2 text-left outline-none {current || queued ? 'border-gray-300 dark:border-gray-700' : 'border-transparent'}">
							<span class="min-w-0"><span class="block truncate text-sm">{file.path}</span><span class="text-xs text-gray-500">{size(file.size)}{file.parts && file.parts > 1 ? ` / ${file.parts} ${$i18n.t('Files')}` : ''}</span></span>
							{#if current || queued || file.installed}<span data-download-status class="mr-1 shrink-0 text-xs font-medium whitespace-nowrap text-gray-500 dark:text-gray-400">{$i18n.t(current ? 'Downloading' : queued ? 'Queued' : 'Installed')}</span>{:else}<button type="button" data-download-hf={file.path} aria-label={$i18n.t('Download')} title={$i18n.t('Download')} disabled={blocked} class="grid size-7 shrink-0 place-items-center rounded-md p-0 text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800" on:click={(event) => { event.currentTarget.closest<HTMLElement>('[data-hf-file]')?.focus({ preventScroll: true }); start(file); }}><Download className="block size-4" /></button>{/if}
						</div>
					{/each}
				</div>
				{#if !files.length}<p class="py-6 text-center text-sm text-gray-500">{$i18n.t('No GGUF files found')}</p>{/if}
			{/if}
		{:else}
			<div class="grid grid-cols-1 gap-x-4 gap-y-2 md:grid-cols-2" data-hf-grid>
				{#each models as model (model.id)}
					{@const current = activeRequest?.source === 'hf' && activeRequest.repo === model.id}
					{@const queued = queuedRequests.some(request => request.source === 'hf' && request.repo === model.id)}
					{@const installed = repoFiles[model.id]?.some(file => file.installed)}
					<div class="flex h-[72px] min-w-0 items-center gap-3 rounded-lg border bg-gray-50 dark:bg-gray-850/50 px-3 text-left {current || queued ? 'border-gray-300 dark:border-gray-700' : 'border-transparent'}" data-hf-repo={model.id}>
						<HuggingFace className="size-8 shrink-0 text-gray-500 dark:text-gray-400" />
						<span class="min-w-0 flex-1"><span class="block truncate text-sm font-medium">{model.id.split('/').slice(1).join('/')}</span><span class="block truncate text-xs text-gray-500">{model.id.split('/')[0]}</span></span>
						{#if current || queued || installed}<span data-download-status class="mr-1 shrink-0 text-xs font-medium whitespace-nowrap text-gray-500 dark:text-gray-400">{$i18n.t(current ? 'Downloading' : queued ? 'Queued' : 'Installed')}</span>{/if}
						<button type="button" aria-label={model.id} class="grid size-7 shrink-0 place-items-center rounded-md text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800" on:click={() => open(model)}><ChevronRight className="size-4" /></button>
					</div>
				{/each}
			</div>
			{#if loading}<div class="flex h-12 items-center justify-center"><Spinner className="size-4" /></div>{:else if nextCursor}<button type="button" class="mx-auto mt-3 block rounded-lg px-3 py-2 text-xs hover:bg-gray-100 dark:hover:bg-gray-800" on:click={() => load(query.trim(), nextCursor!)}>{$i18n.t('Load more')}</button>{/if}
		{/if}
	</div>
	{/if}
</div>
{/if}
