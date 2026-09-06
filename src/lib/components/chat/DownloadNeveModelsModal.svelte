<script lang="ts" context="module">
	const neveCatalogCacheKey = 'neveai.downloadModels.catalog';
	const retiredModelIds = new Set(['neve-prism', 'neve-prism-x', 'neve-strata', 'neve-cascade-s']);
	const catalogModelOverrides: Record<string, Partial<any>> = {
		'neve-strata-x': {
			name: 'Neve Strata'
		},
		'neve-muse': {
			repo: 'NeveAI/Neve-Muse-5-12B-GGUF',
			size_label: '12.1 GB',
			params: { temperature: 0.75, min_p: 0.1, dry_multiplier: 0.9, dry_allowed_length: 2 }
		},
		'neve-cascade-x': {
			name: 'Neve Cascade',
			repo: 'NeveAI/Neve-Cascade-5-1B-QAT-GGUF',
			params: { temperature: 0.25, min_p: 0.1, dry_multiplier: 0.2, dry_allowed_length: 4 }
		}
	};
	const catalogModelOrder = new Map(
		['neve-echo-s', 'neve-echo', 'neve-sense', 'neve-strata-s', 'neve-strata-x', 'neve-muse', 'neve-cascade-x'].map(
			(id, index) => [id, index]
		)
	);
	let memoryCatalogCache: any[] = [];

	const filterRetiredCatalogModels = (catalog: any[]) =>
		Array.isArray(catalog)
			? catalog
					.filter((model) => !retiredModelIds.has(model?.id))
					.map((model) => ({
						...model,
						...(catalogModelOverrides[model?.id] ?? {}),
						default_feature_ids: (model?.default_feature_ids ?? []).filter(
							(featureId: string) => featureId !== 'toggle_reasoning'
						)
					}))
					.sort(
						(a, b) =>
							(catalogModelOrder.get(a?.id) ?? Number.MAX_SAFE_INTEGER) -
							(catalogModelOrder.get(b?.id) ?? Number.MAX_SAFE_INTEGER)
					)
			: [];

	const readCachedNeveCatalog = () => {
		if (memoryCatalogCache.length > 0) return memoryCatalogCache;
		if (typeof localStorage === 'undefined') return [];

		try {
			const cached = JSON.parse(localStorage.getItem(neveCatalogCacheKey) ?? 'null');
			if (!Array.isArray(cached?.catalog)) return [];
			memoryCatalogCache = filterRetiredCatalogModels(cached.catalog);
			return memoryCatalogCache;
		} catch {
			return [];
		}
	};

	const writeCachedNeveCatalog = (catalog: any[]) => {
		memoryCatalogCache = filterRetiredCatalogModels(catalog);
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
		'neve-sense': ['12GB+', 'Q4_K_XL'],
		'neve-strata-s': ['6GB+', 'Q4_K_XL'],
		'neve-strata-x': ['16GB+', 'Q4_K_XL'],
		'neve-cascade-x': ['CPU', 'Q4_0'],
		'neve-muse': ['12GB+', 'Q8_0']
	};

	const modelIconPaths: Record<string, string> = {
		'neve-echo-s': '/static/logoechos.png',
		'neve-echo': '/static/logoecho.png',
		'neve-sense': '/static/logosense.png',
		'neve-strata-s': '/static/logostratas.png',
		'neve-strata-x': '/static/logostrata.png',
		'neve-cascade-x': '/static/logocascade.png',
		'neve-muse': '/static/logomuse.png'
	};
</script>

<script lang="ts">
	import { createEventDispatcher, getContext, onDestroy, onMount } from 'svelte';
	import { fade } from 'svelte/transition';
	import { DropdownMenu } from 'bits-ui';
	import { toast } from 'svelte-sonner';

	import Modal from '$lib/components/common/Modal.svelte';
	import ConfirmDialog from '$lib/components/common/ConfirmDialog.svelte';
	import XMark from '$lib/components/icons/XMark.svelte';
	import Spinner from '$lib/components/common/Spinner.svelte';
	import Dropdown from '$lib/components/common/Dropdown.svelte';
	import DownloadProgressToast from '$lib/components/chat/DownloadNeveModelsProgressToast.svelte';
	import { NEVEAI_BASE_URL } from '$lib/constants';
	import { getModels } from '$lib/apis';
	import { models, showArtifacts } from '$lib/stores';

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
	const dispatch = createEventDispatcher<{ modelsChanged: void }>();
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
	let interfaceBlockersOpen = false;
	let modalObserver: MutationObserver | null = null;
	let selectedDownloadItems: NeveCatalogModel[] = [];
	let selectedDownloadCount = 0;
	let selectedDownloadSizeLabel = '0 GB';
	let showDownloadDetails = false;

	const activeStatuses = ['queued', 'resolving', 'downloading', 'cancelling'];

	const getModelIconUrl = (item: NeveCatalogModel) => {
		const path = item.profile_image_url || modelIconPaths[item.id] || '/static/favicon.png';
		if (path.startsWith('http') || path.startsWith('data:')) return path;
		return `${NEVEAI_BASE_URL}${path.startsWith('/') ? path : `/${path}`}`;
	};

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
			catalog = filterRetiredCatalogModels(await getNeveCatalog(localStorage.token));
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

	const isVisibleElement = (element: HTMLElement) => {
		if (element.getAttribute('aria-hidden') === 'true') return false;
		if (element.classList.contains('hidden')) return false;
		return element.offsetParent !== null || element.getClientRects().length > 0;
	};

	const hasVisibleModalBlocker = () => {
		if (typeof document === 'undefined') return false;
		const dialogs = Array.from(
			document.querySelectorAll<HTMLElement>('.modal, [role="dialog"][aria-modal="true"]')
		);

		return dialogs.some((dialog) => {
			if (dialog.closest('[data-sonner-toast]')) return false;
			return isVisibleElement(dialog);
		});
	};

	const hasVisibleChatMoreMenu = () => {
		if (typeof document === 'undefined') return false;
		const menus = Array.from(document.querySelectorAll<HTMLElement>('[data-neve-chat-more-menu]'));
		return menus.some((menu) => isVisibleElement(menu));
	};

	const syncInterfaceBlockers = () => {
		interfaceBlockersOpen = hasVisibleModalBlocker() || hasVisibleChatMoreMenu();
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

	const selectAllModels = () => {
		if (downloading) return;
		selectedIds = new Set(
			catalog.filter((item) => !item.installed).map((item) => item.id)
		);
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
		const queueContinues = queuedModelIds.length > 0;
		if (currentEs) {
			currentEs.close();
		}
		downloading = queueContinues;
		cancelling = false;
		progress = 0;
		progressLabel = queueContinues ? 'Preparando próximo download...' : '';
		currentTaskId = null;
		downloadingModelId = null;
		downloadingModelName = '';
		currentEs = null;
		if (!queueContinues) {
			showDownloadDetails = false;
			dismissDownloadProgressToast();
		}
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
				dispatch('modelsChanged');
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
			catalog = filterRetiredCatalogModels(catalogResult.value);
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

	const hydrateActiveDownload = async () => {
		try {
			const activeDownload = await getActiveNeveDownload(localStorage.token);
			if (activeDownload?.task_id) {
				attachToDownload(activeDownload.task_id, activeDownload);
			} else {
				toast.dismiss(downloadProgressToastId);
				progressToastVisible = false;
			}
		} catch {
			// The visible modal load path will surface backend/catalog failures when the user opens it.
		}
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
		selectedIds = new Set();
		showDownloadDetails = false;
	}

	$: if (downloading && !show && !interfaceBlockersOpen && !$showArtifacts && downloadingModelName) {
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
			dispatch('modelsChanged');
			toast.success(`${item.name} desinstalado`);
		} catch (e: any) {
			toast.error(normalizeLlamaCppErrorMessage(e, 'Falha ao desinstalar modelo'));
		} finally {
			uninstallingModelId = null;
		}
	};

	onMount(() => {
		syncInterfaceBlockers();
		void hydrateActiveDownload();
		if (typeof MutationObserver !== 'undefined' && typeof document !== 'undefined') {
			modalObserver = new MutationObserver(syncInterfaceBlockers);
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
	});
</script>

<Modal
	bind:show
	animated={false}
	size="w-[min(40rem,calc(100vw-1rem))]"
	containerClassName="p-2 sm:p-3"
	className="bg-white dark:bg-gray-900 rounded-xl max-h-[calc(100dvh-1rem)] overflow-hidden"
>
	<div class="flex max-h-[calc(100dvh-1rem)] flex-col">
		<div
			class="flex h-[60px] min-h-[60px] shrink-0 items-center justify-between border-b border-gray-200/30 px-5 dark:border-gray-700/20 dark:text-gray-300"
		>
			<div class="self-center text-lg font-medium text-black dark:text-[#eee]">{$i18n.t('Baixar modelos')}</div>
			<div class="flex items-center gap-1.5">
				{#if downloading}
					<Dropdown
						bind:show={showDownloadDetails}
						align="end"
						triggerClassName="group relative grid size-9 shrink-0 place-items-center p-0"
					>
						<span aria-label="Progresso do download">
							<span class="pointer-events-none absolute inset-[3px] rounded-full bg-gray-800 transition group-hover:bg-gray-700 dark:bg-gray-800 dark:group-hover:bg-gray-700"></span>
							<svg
								aria-hidden="true"
								class="pointer-events-none absolute inset-0 size-9 -rotate-90"
								viewBox="0 0 36 36"
							>
								<circle cx="18" cy="18" r="16.5" fill="none" stroke="currentColor" stroke-width="1.5" class="text-white/20" />
								<circle
									cx="18"
									cy="18"
									r="16.5"
									fill="none"
									stroke="currentColor"
									stroke-width="1.5"
									stroke-linecap="round"
									pathLength="100"
									stroke-dasharray="100"
									stroke-dashoffset={100 - Math.min(100, Math.max(0, progress * 100))}
									class="text-white transition-[stroke-dashoffset]"
								/>
							</svg>
							<svg aria-hidden="true" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" class="relative z-10 size-5">
								<path stroke-linecap="round" stroke-linejoin="round" d="M3 16.5v2.25A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V16.5M16.5 12 12 16.5m0 0L7.5 12m4.5 4.5V3" />
							</svg>
						</span>

						<div slot="content">
							<DropdownMenu.Content
								class="z-[10002] w-[19rem] rounded-lg border border-gray-200 bg-white p-3 shadow-lg dark:border-gray-800 dark:bg-gray-850 dark:text-white"
								side="bottom"
								align="end"
								sideOffset={7}
								transition={(node) => fade(node, { duration: 100 })}
							>
								<div class="flex justify-between gap-3 text-xs text-gray-500 dark:text-gray-400">
									<span class="min-w-0 truncate">{progressLabel}</span>
									<span class="shrink-0">{Math.round(progress * 100)}%</span>
								</div>
								<div class="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-gray-100 dark:bg-gray-800">
									<div
										class="h-full bg-black transition-all dark:bg-white"
										style="width: {Math.min(100, Math.max(0, progress * 100))}%"
									></div>
								</div>
								<div class="mt-3 flex items-center justify-between gap-3">
									{#if queuedModelIds.length > 0}
										<span class="text-xs text-gray-500 dark:text-gray-400">
											{queuedModelIds.length}
											{queuedModelIds.length === 1 ? 'modelo em fila' : 'modelos em fila'}
										</span>
									{:else}
										<span></span>
									{/if}
									<button
										type="button"
										class="flex items-center gap-2 rounded-lg border border-gray-200 px-3 py-1.5 text-xs font-medium transition hover:bg-gray-50 disabled:opacity-40 dark:border-gray-700 dark:hover:bg-gray-800"
										disabled={cancelling}
										on:click={handleCancelDownload}
									>
										{#if cancelling}<Spinner className="size-3" />{/if}
										{$i18n.t(cancelling ? 'Cancelando...' : 'Cancelar')}
									</button>
								</div>
							</DropdownMenu.Content>
						</div>
					</Dropdown>
				{/if}
				<button
					class="self-center"
					on:click={() => {
						show = false;
					}}
				>
					<XMark className={'size-5'} />
				</button>
			</div>
		</div>

		<div class="flex min-h-0 w-full flex-col px-5 pt-4 pb-1 dark:text-gray-200">
			<div class="flex h-[min(490px,calc(100dvh-164px))] min-h-[192px] flex-col gap-1 overflow-y-auto pr-1">
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
						{@const isQueuedDownload = queuedModelIds.includes(item.id)}
						{@const isDownloadMarked = selected || isCurrentDownload || isQueuedDownload}
						<div
							class="relative box-border h-[66px] min-h-[66px] max-h-[66px] shrink-0 rounded-lg border transition-colors {item.installed
								? 'opacity-70 border-transparent'
								: selected || isCurrentDownload || isQueuedDownload
								? `${downloading ? 'cursor-default' : ''} border-gray-300 bg-gray-50 dark:border-gray-700 dark:bg-gray-850`
								: downloading
									? 'cursor-default border-transparent'
									: 'border-transparent hover:bg-gray-50 dark:hover:bg-gray-850/50'}"
						>
							<div class="grid h-full grid-cols-[auto_auto_minmax(0,1fr)_6rem] items-center gap-3 px-3">
								<button
								type="button"
								class="flex size-5 shrink-0 items-center justify-center rounded-full border transition-colors {isDownloadMarked
									? 'border-black bg-black text-white dark:border-white dark:bg-white dark:text-black'
									: 'border-gray-300 bg-white text-transparent dark:border-gray-700 dark:bg-gray-900'} {item.installed ? 'cursor-default opacity-50' : downloading ? 'cursor-default' : 'cursor-pointer hover:border-gray-500 dark:hover:border-gray-500'}"
								disabled={item.installed || downloading}
								aria-label={selected ? `Remover ${item.name} da seleção` : `Selecionar ${item.name}`}
								aria-pressed={isDownloadMarked}
								on:click|stopPropagation={() => toggleSelection(item)}
								>
									{#if isDownloadMarked}
										<svg class="size-3" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
											<path d="M4.5 10.5 8 14l7.5-8" />
										</svg>
									{/if}
								</button>

								<img
									src={getModelIconUrl(item)}
									alt=""
									class="size-8 shrink-0 rounded-full object-cover"
								/>

								<div class="grid h-10 min-w-0 grid-rows-[1.25rem_1.25rem] self-center">
									<div class="flex h-5 min-w-0 items-center gap-1.5 overflow-hidden">
									<span class="shrink-0 text-sm font-semibold leading-none">
										{item.name}
									</span>
									<div class="flex min-w-0 flex-nowrap items-center gap-1 overflow-hidden">
										{#each modelBadges[item.id] ?? [] as badge}
											<span class="inline-flex h-5 items-center rounded-md bg-gray-100 px-1.5 text-[10px] font-medium leading-none text-gray-600 dark:bg-gray-800 dark:text-gray-300">
												{badge}
											</span>
										{/each}
									</div>
									</div>
									<div
										class="relative top-[4px] h-5 overflow-hidden whitespace-nowrap text-gray-500 dark:text-gray-400"
										style="font-size: 14px !important; line-height: 1.08rem; transform: scale(1.04); transform-origin: left center; width: calc(100% / 1.04);"
									>
										{item.description}
									</div>
								</div>

								<div class="flex h-7 w-24 shrink-0 items-center justify-end">
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
									class="inline-flex h-7 w-full items-center justify-center px-2 text-center text-xs font-medium text-gray-500 dark:text-gray-400"
									>
									Baixando
								</span>
							{:else if isQueuedDownload}
								<span
									class="inline-flex h-7 w-full items-center justify-center px-2 text-center text-xs font-medium text-gray-500 dark:text-gray-400"
								>
									Em fila
								</span>
							{/if}
								</div>
							</div>

							{#if downloading && !item.installed && !isCurrentDownload && !isQueuedDownload}
								<div
									aria-hidden="true"
									class="pointer-events-none absolute inset-0 z-10 rounded-lg bg-white/50 dark:bg-gray-900/50"
								></div>
							{/if}
						</div>
					{/each}
				{/if}
			</div>

			<div class="mt-2 flex h-11 shrink-0 -translate-y-1 items-center gap-2">
				<div class="min-w-0 flex flex-1 items-center justify-between gap-3">
						{#if !downloading}
							<button
								type="button"
								class="shrink-0 text-xs font-medium text-gray-400 transition hover:text-gray-700 disabled:cursor-default disabled:opacity-50 dark:text-gray-500 dark:hover:text-gray-200"
								disabled={loading}
								on:click={selectedDownloadCount > 0 ? clearSelections : selectAllModels}
							>
								{selectedDownloadCount > 0 ? 'Desmarcar tudo' : 'Selecionar tudo'}
							</button>
							{#if selectedDownloadCount > 0}
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
						disabled={selectedDownloadCount === 0 || loading || downloading}
						on:click={handleDownload}
					>
						{$i18n.t('Baixar')}
				</button>
			</div>
		</div>
	</div>
</Modal>

<ConfirmDialog
	bind:show={showUninstallConfirm}
	animated={false}
	title="Desinstalar modelo?"
	message={`Tem certeza que deseja desinstalar ${uninstallTarget?.name ?? 'este modelo'}?`}
	confirmLabel="Confirmar"
	cancelLabel="Cancelar"
	onConfirm={confirmUninstall}
	on:cancel={() => {
		uninstallTarget = null;
	}}
/>
