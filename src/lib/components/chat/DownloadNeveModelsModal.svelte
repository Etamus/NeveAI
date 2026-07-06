<script lang="ts" context="module">
	const neveCatalogCacheKey = 'neveai.downloadModels.catalog';
	let memoryCatalogCache: any[] = [];

	const readCachedNeveCatalog = () => {
		if (memoryCatalogCache.length > 0) return memoryCatalogCache;
		if (typeof localStorage === 'undefined') return [];

		try {
			const cached = JSON.parse(localStorage.getItem(neveCatalogCacheKey) ?? 'null');
			if (!Array.isArray(cached?.catalog)) return [];
			memoryCatalogCache = cached.catalog;
			return memoryCatalogCache;
		} catch {
			return [];
		}
	};

	const writeCachedNeveCatalog = (catalog: any[]) => {
		memoryCatalogCache = Array.isArray(catalog) ? catalog : [];
		if (typeof localStorage === 'undefined') return;

		try {
			localStorage.setItem(
				neveCatalogCacheKey,
				JSON.stringify({ timestamp: Date.now(), catalog: memoryCatalogCache })
			);
		} catch {}
	};

	const modelBadges: Record<string, string[]> = {
		'neve-echo-s': ['4GB+', 'Q4_K_XL'],
		'neve-echo': ['6GB+', 'Q4_K_XL'],
		'neve-prism': ['8GB+', 'Q5_K_XL'],
		'neve-prism-x': ['8GB+', 'Q6_K_XL'],
		'neve-sense': ['12GB+', 'Q4_K_XL'],
		'neve-strata-s': ['6GB+', 'Q8_K_XL'],
		'neve-strata': ['16GB+', 'Q4_K_XL'],
		'neve-strata-x': ['16GB+', 'Q4_K_XL'],
		'neve-cascade-s': ['CPU', 'Q8_0'],
		'neve-cascade-x': ['CPU', 'Q3_K_XL']
	};
</script>

<script lang="ts">
	import { getContext, onDestroy, onMount } from 'svelte';
	import { toast } from 'svelte-sonner';

	import Modal from '$lib/components/common/Modal.svelte';
	import ConfirmDialog from '$lib/components/common/ConfirmDialog.svelte';
	import XMark from '$lib/components/icons/XMark.svelte';
	import Spinner from '$lib/components/common/Spinner.svelte';
	import DownloadProgressToast from '$lib/components/chat/DownloadNeveModelsProgressToast.svelte';
	import { NEVEAI_BASE_URL } from '$lib/constants';
	import { getModels } from '$lib/apis';
	import { models } from '$lib/stores';

	import {
		cancelNeveDownload,
		deleteNeveCatalogModel,
		getActiveNeveDownload,
		getNeveCatalog,
		normalizeLlamaCppErrorMessage,
		startNeveDownload,
		streamNeveDownload,
		type NeveCatalogModel,
		type NeveDownloadState
	} from '$lib/apis/llamacpp';

	const i18n = getContext('i18n');
	const downloadProgressToastId = 'neveai-download-model-progress';

	export let show = false;

	let loading = false;
	let catalog: NeveCatalogModel[] = readCachedNeveCatalog();
	let catalogError = '';
	let selectedIds: Set<string> = new Set();
	let queuedModelIds: string[] = [];
	let wasShown = false;

	let downloading = false;
	let cancelling = false;
	let progress = 0;
	let progressLabel = '';
	let currentTaskId: string | null = null;
	let downloadingModelId: string | null = null;
	let downloadingModelName = '';
	let currentEs: EventSource | null = null;
	let uninstallingModelId: string | null = null;
	let showUninstallConfirm = false;
	let uninstallTarget: NeveCatalogModel | null = null;
	let progressToastVisible = false;
	let modalBlockersOpen = false;
	let modalObserver: MutationObserver | null = null;
	let selectedDownloadItems: NeveCatalogModel[] = [];
	let selectedDownloadCount = 0;
	let selectedDownloadSizeLabel = '0 GB';

	const activeStatuses = ['queued', 'resolving', 'downloading', 'cancelling'];

	const fmtBytes = (n: number): string => {
		if (!n) return '';
		const units = ['B', 'KB', 'MB', 'GB', 'TB'];
		let i = 0;
		let v = n;
		while (v >= 1024 && i < units.length - 1) {
			v /= 1024;
			i++;
		}
		return `${v.toFixed(1)} ${units[i]}`;
	};

	const loadCatalog = async () => {
		try {
			catalogError = '';
			catalog = await getNeveCatalog(localStorage.token);
			writeCachedNeveCatalog(catalog);
		} catch (e: any) {
			catalogError = normalizeLlamaCppErrorMessage(e, 'Falha ao carregar catálogo');
			toast.error(catalogError);
			if (catalog.length === 0) {
				catalog = readCachedNeveCatalog();
			}
		}
	};

	const modelNameFor = (modelId?: string | null) =>
		catalog.find((model) => model.id === modelId)?.name || downloadingModelName || 'Modelo';

	const getSelectableModels = () =>
		catalog.filter((item) => selectedIds.has(item.id) && !item.installed);

	const parseSizeLabelToGb = (sizeLabel?: string): number => {
		const match = `${sizeLabel ?? ''}`.trim().match(/^([\d,.]+)\s*(B|KB|MB|GB|TB)?/i);
		if (!match) return 0;

		const value = Number.parseFloat(match[1].replace(',', '.'));
		if (!Number.isFinite(value)) return 0;

		const unit = (match[2] ?? 'GB').toUpperCase();
		if (unit === 'TB') return value * 1024;
		if (unit === 'MB') return value / 1024;
		if (unit === 'KB') return value / (1024 * 1024);
		if (unit === 'B') return value / (1024 * 1024 * 1024);
		return value;
	};

	const formatTotalSize = (sizeGb: number): string => {
		if (!sizeGb) return '0 GB';
		return `${sizeGb.toFixed(1)} GB`;
	};

	const hasVisibleModalBlocker = () => {
		if (typeof document === 'undefined') return false;
		const dialogs = Array.from(
			document.querySelectorAll<HTMLElement>('.modal, [role="dialog"][aria-modal="true"]')
		);

		return dialogs.some((dialog) => {
			if (dialog.closest('[data-sonner-toast]')) return false;
			if (dialog.getAttribute('aria-hidden') === 'true') return false;
			if (dialog.classList.contains('hidden')) return false;
			return dialog.offsetParent !== null || dialog.getClientRects().length > 0;
		});
	};

	const syncModalBlockers = () => {
		modalBlockersOpen = hasVisibleModalBlocker();
	};

	const toggleSelection = (item: NeveCatalogModel) => {
		if (downloading || item.installed) return;
		const next = new Set(selectedIds);
		if (next.has(item.id)) {
			next.delete(item.id);
		} else {
			next.add(item.id);
		}
		selectedIds = next;
	};

	const removeSelection = (modelId?: string | null) => {
		if (!modelId || !selectedIds.has(modelId)) return;
		const next = new Set(selectedIds);
		next.delete(modelId);
		selectedIds = next;
	};

	const clearSelections = () => {
		if (downloading || selectedIds.size === 0) return;
		selectedIds = new Set();
	};

	const showDownloadProgressToast = (name: string, progressValue: number, label: string) => {
		if (!downloading || show || !name) return;
		progressToastVisible = true;
		toast.custom(DownloadProgressToast, {
			id: downloadProgressToastId,
			class: 'neve-download-progress-toast-shell',
			componentProps: {
				name,
				progress: progressValue,
				label,
				cancelling,
				onCancel: handleCancelDownload
			},
			duration: Number.POSITIVE_INFINITY,
			dismissable: false,
			unstyled: true
		});
	};

	const dismissDownloadProgressToast = () => {
		if (!progressToastVisible) return;
		toast.dismiss(downloadProgressToastId);
		progressToastVisible = false;
	};

	const applyDownloadState = (state: NeveDownloadState) => {
		if (state.task_id) {
			currentTaskId = state.task_id;
		}
		if (state.model_id) {
			downloadingModelId = state.model_id;
			if (!selectedIds.has(state.model_id)) {
				selectedIds = new Set([...selectedIds, state.model_id]);
			}
		}
		if (state.name) {
			downloadingModelName = state.name;
		}

		downloading = activeStatuses.includes(state.status);
		cancelling = state.status === 'cancelling';
		progress = typeof state.progress === 'number' ? state.progress : progress;

		if (state.status === 'resolving') {
			progressLabel = 'Procurando arquivos...';
		} else if (state.status === 'downloading') {
			const fileLabel = state.file_total && state.file_total > 1 ? ` (${state.file_index}/${state.file_total})` : '';
			const sz = state.total ? `${fmtBytes(state.downloaded ?? 0)} / ${fmtBytes(state.total)}` : '';
			const verb = state.resumed ? 'Retomando' : 'Baixando';
			progressLabel = `${verb}${fileLabel} ${sz}`.trim();
		} else if (state.status === 'queued') {
			progressLabel = queuedModelIds.length > 0 ? `Na fila (${queuedModelIds.length} restante${queuedModelIds.length === 1 ? '' : 's'})...` : 'Na fila...';
		} else if (state.status === 'cancelling') {
			progressLabel = 'Cancelando e limpando arquivos...';
		} else if (state.status === 'completed') {
			progress = 1;
			progressLabel = 'Download concluído';
		} else if (state.status === 'cancelled') {
			progressLabel = 'Download cancelado';
		} else if (state.status === 'error') {
			progressLabel = 'Falha no download';
		}
	};

	const clearDownloadState = () => {
		if (currentEs) {
			currentEs.close();
		}
		downloading = false;
		cancelling = false;
		progress = 0;
		progressLabel = '';
		currentTaskId = null;
		downloadingModelId = null;
		downloadingModelName = '';
		currentEs = null;
		dismissDownloadProgressToast();
	};

	const startNextQueuedDownload = async () => {
		const nextId = queuedModelIds.find((id) => {
			const entry = catalog.find((model) => model.id === id);
			return entry && !entry.installed;
		});

		queuedModelIds = nextId ? queuedModelIds.filter((id) => id !== nextId) : [];
		if (!nextId) return;

		await startSingleDownload(nextId);
	};

	const attachToDownload = (taskId: string, initialState?: NeveDownloadState | null) => {
		if (currentTaskId === taskId && currentEs) {
			if (initialState) {
				applyDownloadState(initialState);
			}
			return;
		}

		if (currentEs) {
			currentEs.close();
			currentEs = null;
		}

		currentTaskId = taskId;
		downloading = true;
		cancelling = false;

		if (initialState) {
			applyDownloadState(initialState);
		}

		currentEs = streamNeveDownload(
			taskId,
			applyDownloadState,
			async (state) => {
				const completedId = state.model_id ?? downloadingModelId;
				const name = modelNameFor(completedId);
				clearDownloadState();
				removeSelection(completedId);

				if (state.message === 'Já instalado') {
					toast.info(`${name}: já instalado`);
				} else {
					toast.success(`${name} baixado com sucesso`);
				}

				await loadCatalog();
				models.set(await getModels(localStorage.token, null, false, true));
				await startNextQueuedDownload();
			},
			(err: any) => {
				queuedModelIds = [];
				clearDownloadState();
				toast.error(normalizeLlamaCppErrorMessage(err, 'Falha no download'));
			},
			async (state) => {
				queuedModelIds = [];
				const retryId = state.model_id ?? downloadingModelId;
				const name = modelNameFor(retryId);
				clearDownloadState();
				toast.info(`${name}: download cancelado e arquivos parciais removidos`);
				await loadCatalog();
			}
		);
	};

	const hydrateModal = async () => {
		loading = catalog.length === 0;
		const [catalogResult, activeResult] = await Promise.allSettled([
			getNeveCatalog(localStorage.token),
			getActiveNeveDownload(localStorage.token)
		]);

		if (catalogResult.status === 'fulfilled') {
			catalogError = '';
			catalog = catalogResult.value;
			writeCachedNeveCatalog(catalog);
		} else {
			catalogError = normalizeLlamaCppErrorMessage(
				catalogResult.reason,
				'Falha ao carregar catálogo'
			);
			toast.error(catalogError);
			if (catalog.length === 0) {
				catalog = readCachedNeveCatalog();
			}
		}

		if (activeResult.status === 'fulfilled' && activeResult.value?.task_id) {
			attachToDownload(activeResult.value.task_id, activeResult.value);
		} else if (!downloading) {
			progress = 0;
			progressLabel = '';
			cancelling = false;
		}

		loading = false;
	};

	$: selectedDownloadItems = catalog.filter((item) => selectedIds.has(item.id) && !item.installed);
	$: selectedDownloadCount = selectedDownloadItems.length;
	$: selectedDownloadSizeLabel = formatTotalSize(
		selectedDownloadItems.reduce((total, item) => total + parseSizeLabelToGb(item.size_label), 0)
	);

	$: if (show && !wasShown) {
		wasShown = true;
		void hydrateModal();
	} else if (!show && wasShown) {
		wasShown = false;
	}

	$: if (downloading && !show && !modalBlockersOpen && downloadingModelName) {
		showDownloadProgressToast(downloadingModelName, progress, progressLabel);
	} else {
		dismissDownloadProgressToast();
	}

	async function startSingleDownload(modelId: string) {
		const entry = catalog.find((m) => m.id === modelId);
		if (!entry) return;

		downloading = true;
		cancelling = false;
		downloadingModelId = entry.id;
		downloadingModelName = entry.name;
		progress = 0;
		progressLabel = 'Conectando...';

		try {
			const activeDownload = await getActiveNeveDownload(localStorage.token);
			if (activeDownload?.task_id) {
				attachToDownload(activeDownload.task_id, activeDownload);
				if (activeDownload.model_id !== entry.id) {
					queuedModelIds = [];
					toast.info('Já existe um download de modelo em andamento');
				}
				return;
			}

			const taskId = await startNeveDownload(localStorage.token, modelId);
			attachToDownload(taskId, {
				task_id: taskId,
				model_id: entry.id,
				name: entry.name,
				status: 'queued',
				progress: 0
			});
		} catch (e: any) {
			queuedModelIds = [];
			clearDownloadState();
			toast.error(normalizeLlamaCppErrorMessage(e, 'Falha ao iniciar download'));
		}
	}

	const handleDownload = async () => {
		if (downloading || loading) return;

		const targets = getSelectableModels().map((item) => item.id);
		if (targets.length === 0) return;

		queuedModelIds = targets.slice(1);
		await startSingleDownload(targets[0]);
	};

	const handleCancelDownload = async () => {
		if (!currentTaskId || !downloading || cancelling) return;

		cancelling = true;
		queuedModelIds = [];
		progressLabel = 'Cancelando e limpando arquivos...';
		try {
			const state = await cancelNeveDownload(localStorage.token, currentTaskId);
			applyDownloadState(state);
			if (state.status === 'cancelled') {
				clearDownloadState();
				await loadCatalog();
			}
		} catch (e: any) {
			cancelling = false;
			toast.error(normalizeLlamaCppErrorMessage(e, 'Falha ao cancelar download'));
		}
	};

	const requestUninstall = (item: NeveCatalogModel) => {
		if (!item.installed || downloading || uninstallingModelId) return;
		uninstallTarget = item;
		showUninstallConfirm = true;
	};

	const confirmUninstall = async () => {
		if (!uninstallTarget) return;
		const target = uninstallTarget;
		uninstallTarget = null;
		await handleUninstall(target);
	};

	const handleUninstall = async (item: NeveCatalogModel) => {
		if (!item.installed || downloading || uninstallingModelId) return;

		uninstallingModelId = item.id;
		try {
			await deleteNeveCatalogModel(localStorage.token, item.id);
			removeSelection(item.id);
			await loadCatalog();
			models.set(await getModels(localStorage.token, null, false, true));
			toast.success(`${item.name} desinstalado`);
		} catch (e: any) {
			toast.error(normalizeLlamaCppErrorMessage(e, 'Falha ao desinstalar modelo'));
		} finally {
			uninstallingModelId = null;
		}
	};

	onMount(() => {
		syncModalBlockers();
		if (typeof MutationObserver !== 'undefined' && typeof document !== 'undefined') {
			modalObserver = new MutationObserver(syncModalBlockers);
			modalObserver.observe(document.body, {
				attributes: true,
				attributeFilter: ['aria-hidden', 'class', 'style'],
				childList: true,
				subtree: true
			});
		}
	});

	onDestroy(() => {
		modalObserver?.disconnect();
		modalObserver = null;
		if (currentEs) {
			currentEs.close();
			currentEs = null;
		}
		dismissDownloadProgressToast();
	});
</script>

<Modal bind:show size="w-[40rem]" keepMounted>
	<div>
		<div
			class="flex justify-between dark:text-gray-300 px-5 pt-4 pb-3 border-b border-gray-200/30 dark:border-gray-700/20"
		>
			<div class="text-lg font-medium self-center">{$i18n.t('Baixar modelos')}</div>
			<button
				class="self-center"
				on:click={() => {
					show = false;
				}}
			>
				<XMark className={'size-5'} />
			</button>
		</div>

		<div class="flex flex-col w-full px-5 pt-4 pb-4 dark:text-gray-200">
			<div class="flex h-[26.15rem] max-h-[26.15rem] snap-y snap-mandatory flex-col gap-1 overflow-y-auto pr-1">
				{#if loading && catalog.length === 0}
					<div class="flex h-full items-center justify-center">
						<Spinner className="size-5" />
					</div>
				{:else if catalog.length === 0}
					<div class="flex h-full items-center justify-center px-4 text-center">
						<div class="max-w-[18rem]">
							<div class="text-sm font-medium text-gray-800 dark:text-gray-100">
								{$i18n.t(catalogError ? 'Catálogo indisponível' : 'Nenhum modelo disponível')}
							</div>
							<div class="mt-1 text-xs text-gray-500 dark:text-gray-400">
								{#if catalogError}
									{$i18n.t('Verifique se o backend está aberto e tente novamente.')}
								{:else}
									{$i18n.t('Conecte-se à internet para baixar modelos Neve ou coloque arquivos .gguf na pasta models.')}
								{/if}
							</div>
						</div>
					</div>
				{:else}
					{#each catalog as item (item.id)}
						{@const selected = selectedIds.has(item.id)}
						{@const isCurrentDownload = downloading && downloadingModelId === item.id}
						<div
							class="relative flex h-[4.15rem] shrink-0 snap-start items-center gap-3 rounded-lg px-3 transition border {item.installed
								? 'opacity-70 border-transparent'
								: selected
								? `${downloading ? 'cursor-default' : ''} border-gray-300 bg-gray-50 dark:border-gray-700 dark:bg-gray-850`
								: 'border-transparent hover:bg-gray-50 dark:hover:bg-gray-850/50'}"
						>
							<button
								type="button"
								class="mr-2 flex size-5 shrink-0 items-center justify-center rounded-full border transition {selected
									? 'border-black bg-black text-white dark:border-white dark:bg-white dark:text-black'
									: 'border-gray-300 bg-white text-transparent dark:border-gray-700 dark:bg-gray-900'} {item.installed || downloading ? 'cursor-default opacity-50' : 'cursor-pointer hover:border-gray-500 dark:hover:border-gray-500'}"
								disabled={item.installed || downloading}
								aria-label={selected ? `Remover ${item.name} da seleção` : `Selecionar ${item.name}`}
								aria-pressed={selected}
								on:click|stopPropagation={() => toggleSelection(item)}
							>
								{#if selected}
									<svg class="size-3" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
										<path d="M4.5 10.5 8 14l7.5-8" />
									</svg>
								{/if}
							</button>

							<img
								src="{NEVEAI_BASE_URL}/static/favicon.png"
								alt=""
								class="size-8 rounded-full object-cover shrink-0"
							/>

							<div class="min-w-0 flex-1 self-center">
								<div class="flex min-w-0 items-center gap-1.5">
									<span class="shrink-0 text-sm font-semibold leading-none">
										{item.name}
									</span>
									<div class="flex min-w-0 flex-wrap items-center gap-1">
										{#each modelBadges[item.id] ?? [] as badge}
											<span class="inline-flex h-5 items-center rounded-md bg-gray-100 px-1.5 text-[10px] font-medium leading-none text-gray-600 dark:bg-gray-800 dark:text-gray-300">
												{badge}
											</span>
										{/each}
									</div>
								</div>
								<div
									class="mt-1 text-gray-500 dark:text-gray-400 line-clamp-1"
									style="font-size: 14px !important; line-height: 1.08rem; transform: scale(1.04); transform-origin: left center; width: calc(100% / 1.04);"
								>
									{item.description}
								</div>
							</div>

							<div class="flex w-24 shrink-0 items-center justify-end">
								{#if item.installed}
									<button
										type="button"
										class="group inline-flex h-7 w-full cursor-pointer items-center justify-center px-2 text-center text-xs font-medium text-gray-500 transition hover:text-gray-900 disabled:cursor-default disabled:opacity-60 dark:text-gray-400 dark:hover:text-gray-100"
										disabled={uninstallingModelId === item.id}
										title="Desinstalar"
										aria-label="Desinstalar {item.name}"
										on:click|preventDefault|stopPropagation={() => requestUninstall(item)}
									>
										{#if uninstallingModelId === item.id}
											<Spinner className="size-3.5" />
										{:else}
											<span class="group-hover:hidden">Instalado</span>
											<span class="hidden group-hover:block">Desinstalar</span>
										{/if}
									</button>
								{:else if isCurrentDownload}
									<span
										class="inline-flex h-7 w-full items-center justify-center rounded-md bg-gray-850 px-2 text-center text-xs font-medium text-gray-200 shadow-xs dark:bg-gray-850 dark:text-gray-200"
									>
										Baixando
									</span>
								{/if}
							</div>
						</div>
					{/each}
				{/if}
			</div>

			{#if downloading}
				<div class="mx-auto mt-6 w-[92%]">
					<div class="flex justify-between text-xs text-gray-500 dark:text-gray-400 mb-1">
						<span class="line-clamp-1">{progressLabel}</span>
						<span>{Math.round(progress * 100)}%</span>
					</div>
					<div class="w-full h-1.5 bg-gray-100 dark:bg-gray-800 rounded-full overflow-hidden">
						<div
							class="h-full bg-black dark:bg-white transition-all"
							style="width: {Math.min(100, Math.max(0, progress * 100))}%"
						></div>
					</div>
				</div>
			{/if}

			<div class="flex items-center gap-2 pt-4">
				{#if downloading}
					<div class="flex-1"></div>
					<button
						class="px-4 py-1.5 text-xs font-medium border border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-850 transition rounded-lg disabled:opacity-40 flex items-center gap-2"
						disabled={cancelling}
						on:click={handleCancelDownload}
					>
						{#if cancelling}
							<Spinner className="size-3" />
						{/if}
						{$i18n.t(cancelling ? 'Cancelando...' : 'Cancelar')}
					</button>
				{:else}
					<div class="min-w-0 flex flex-1 items-center justify-between gap-3">
						{#if selectedDownloadCount > 0}
							<button
								type="button"
								class="shrink-0 text-xs font-medium text-gray-400 transition hover:text-gray-700 dark:text-gray-500 dark:hover:text-gray-200"
								on:click={clearSelections}
							>
								Desmarcar tudo
							</button>
							<div class="flex min-w-0 items-center justify-end gap-2 text-xs text-gray-500 dark:text-gray-400">
								<span class="whitespace-nowrap">
									{selectedDownloadCount}
									{selectedDownloadCount === 1 ? 'item selecionado' : 'itens selecionados'}
								</span>
								<span class="whitespace-nowrap font-medium text-gray-600 dark:text-gray-300">
									{selectedDownloadSizeLabel}
								</span>
							</div>
						{/if}
					</div>
					{#if false}
						<div class="hidden">
							<button
								type="button"
								class="px-1 text-sm leading-none text-gray-400 transition hover:text-gray-900 dark:text-gray-500 dark:hover:text-gray-100"
								aria-label="Limpar seleÃ§Ã£o"
								on:click={() => {}}
							>
								-
							</button>
							<span class="whitespace-nowrap">
								{selectedDownloadCount}
								{selectedDownloadCount === 1 ? 'item selecionado' : 'itens selecionados'}
							</span>
							<span class="whitespace-nowrap font-medium text-gray-600 dark:text-gray-300">
								{selectedDownloadSizeLabel}
							</span>
						</div>
					{/if}
					<button
						class="ml-2 px-4 py-1.5 text-xs font-medium bg-black text-white dark:bg-white dark:text-black hover:opacity-90 transition rounded-lg disabled:opacity-40 flex items-center gap-2"
						disabled={selectedDownloadCount === 0 || loading}
						on:click={handleDownload}
					>
						{$i18n.t('Baixar')}
					</button>
				{/if}
			</div>
		</div>
	</div>
</Modal>

<ConfirmDialog
	bind:show={showUninstallConfirm}
	title="Desinstalar modelo?"
	message={`Tem certeza que deseja desinstalar ${uninstallTarget?.name ?? 'este modelo'}?`}
	confirmLabel="Confirmar"
	cancelLabel="Cancelar"
	onConfirm={confirmUninstall}
	on:cancel={() => {
		uninstallTarget = null;
	}}
/>
