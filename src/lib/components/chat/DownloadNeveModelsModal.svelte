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
						profile_image_url: '/static/logo.png',
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


</script>

<script lang="ts">
	import { createEventDispatcher, getContext, onDestroy, onMount, tick } from 'svelte';
	import { fade } from 'svelte/transition';
	import { DropdownMenu } from 'bits-ui';
	import { toast } from 'svelte-sonner';

	import Modal from '$lib/components/common/Modal.svelte';
	import MobileModalTitle from '$lib/components/common/MobileModalTitle.svelte';
	import ConfirmDialog from '$lib/components/common/ConfirmDialog.svelte';
	import XMark from '$lib/components/icons/XMark.svelte';
	import XCircle from '$lib/components/icons/XCircle.svelte';
	import Pause from '$lib/components/icons/Pause.svelte';
	import Search from '$lib/components/icons/Search.svelte';
	import ModelInformation from './ModelInformation.svelte';
	import ChevronUpCompact from '$lib/components/icons/ChevronUpCompact.svelte';
	import HuggingFaceModels from '$lib/components/chat/HuggingFaceModels.svelte';
	import Trash from '$lib/components/icons/Trash.svelte';
	import Download from '$lib/components/icons/ModelDownload.svelte';
	import { modelDownloadKey, downloadFilename, type ModelDownloadRequest } from '$lib/utils/modelDownloadRequest';
	import Spinner from '$lib/components/common/Spinner.svelte';
	import Dropdown from '$lib/components/common/Dropdown.svelte';
	import { NEVEAI_BASE_URL } from '$lib/constants';
	import { getModels } from '$lib/apis';
	import { models, neveDownloadToast, showArtifacts, mobile } from '$lib/stores';

	import {
		cancelNeveDownload,
		pauseNeveDownload,
		getPausedNeveDownloads,
		deleteNeveCatalogModel,
		getActiveNeveDownload,
		getNeveCatalog,
		getHFModelFiles,
		normalizeLlamaCppErrorMessage,
		startNeveDownload,
		downloadHFModel,
		streamNeveDownload,
		type NeveCatalogModel,
		type NeveDownloadState
	} from '$lib/apis/llamacpp';

	import type { I18nStore } from '$lib/i18n';
	const i18n = getContext<I18nStore>('i18n');
	const dispatch = createEventDispatcher<{ modelsChanged: void }>();
	export let show = false;
	export let embedded = false;
	export let onBack: () => void = () => { show = false; };
	let query = '';
	let neveExpanded = true;
	let hfDetailOpen = false;
	let hfHasResults = false;
	let hfHeaderActive = false;
	$: if (!hfHasResults) neveExpanded = true;
	$: if (!hfHasResults || hfDetailOpen) hfHeaderActive = false;
	let hfSettledQuery: string | null = null;
	let catalogScroller: HTMLDivElement;
	let previousDetailOpen = false;
	let catalogScrollTop = 0;
	$: if (hfDetailOpen !== previousDetailOpen) {
		previousDetailOpen = hfDetailOpen;
		const opening = hfDetailOpen;
		if (opening) catalogScrollTop = catalogScroller?.scrollTop ?? 0;
		void tick().then(() => { if (catalogScroller && hfDetailOpen === opening) catalogScroller.scrollTop = opening ? 0 : catalogScrollTop; });
	}
	let hfRevision = 0;
	$: visibleCatalog = catalog.filter(item => `${item.name} ${item.repo ?? ''} ${item.description ?? ''} ${$i18n.t(item.description ?? '')} ${item.id}`.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase()));

	let loading = false;
	let catalog: NeveCatalogModel[] = readCachedNeveCatalog();
	let catalogError = '';
	let queuedModelIds: string[] = [];
	const downloadRequests = new Map<string, ModelDownloadRequest>();
	let activeDownloadKey: string | null = null;
	let pausedKeys: string[] = [];
	let removingKeys: string[] = [];
	const pausedTasks = new Map<string, string>();
	const settledTasks = new Set<string>();
	let pendingControl: 'cancel' | 'pause' | null = null;
	let currentFilename = '';
	let queueRevision = 0;
	const downloadLabel = (key: string | null) => {
		const request = key ? downloadRequests.get(key) : undefined;
		return downloadFilename(key === activeDownloadKey && currentFilename || request?.filename || (request?.source === 'neve' ? infoSizes[catalog.find(item => item.id === request.modelId)?.repo ?? '']?.[0]?.path : '')) || $i18n.t('Preparing...');
	};
	let infoSizes: Record<string, { path: string; size: number }[]> = {};
	const pendingInfo = new Set<string>();
	async function loadInfoSize(item: NeveCatalogModel) {
		if (!item.repo || infoSizes[item.repo] || pendingInfo.has(item.repo)) return;
		pendingInfo.add(item.repo);
		try {
			const data = await getHFModelFiles(localStorage.token, item.repo);
			infoSizes = { ...infoSizes, [item.repo]: data.models };
		} catch { /* Preserve the catalog size when metadata is unavailable. */ }
		finally { pendingInfo.delete(item.repo); }
	}
	let wasShown = false;

	let downloading = false;
	let huggingFaceModels: HuggingFaceModels | null = null;
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
	let showDownloadDetails = false;
	let downloadHubElement: HTMLDivElement;
	let downloadMenuElement: HTMLDivElement | undefined;
	const requestModalFocus = getContext<((element: HTMLElement) => void) | undefined>('modal-request-focus');
	const preserveDownloadControlFocus = () => {
		if (!showDownloadDetails) return;
		downloadMenuElement?.focus({ preventScroll: true });
	};
	$: if (showDownloadDetails && !downloading && !queuedModelIds.length && !pausedKeys.length) {
		if (downloadHubElement) requestModalFocus?.(downloadHubElement);
		showDownloadDetails = false;
	}
	let openModelInfoId: string | null = null;

	const activeStatuses = ['queued', 'resolving', 'downloading', 'cancelling', 'pausing'];


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
			catalogError = normalizeLlamaCppErrorMessage(e, $i18n.t('Failed to load catalog'));
			toast.error(catalogError);
			if (catalog.length === 0) {
				catalog = readCachedNeveCatalog();
			}
		}
	};

	const modelNameFor = (modelId?: string | null) =>
		catalog.find((model) => model.id === modelId)?.name || downloadingModelName || 'Modelo';


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


	const showDownloadProgressToast = () => {
		if (!downloading || show || !downloadingModelName) return;
		progressToastVisible = true;
	};

	const dismissDownloadProgressToast = () => {
		if (!progressToastVisible) return;
		progressToastVisible = false;
	};

	$: neveDownloadToast.set(progressToastVisible ? {
		name: downloadLabel(activeDownloadKey),
		progress,
		label: progressLabel,
		cancelling,
		onCancel: handleCancelDownload,
		onPause: handlePauseDownload
	} : null);

	const applyDownloadState = (state: NeveDownloadState) => {
		currentFilename = state.main_filename ?? state.filename ?? state.current_file ?? currentFilename;
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
		cancelling = ['cancelling', 'pausing'].includes(state.status) || pendingControl !== null;
		progress = typeof state.progress === 'number' ? state.progress : progress;

		if (state.status === 'resolving') {
			progressLabel = $i18n.t('Searching for files...');
		} else if (state.status === 'downloading') {
			const sz = (state.downloaded ?? 0) > 0 && (state.total ?? 0) > 0 ? `${fmtBytes(state.downloaded!)} / ${fmtBytes(state.total!)}` : fmtBytes(state.total ?? 0);
			progressLabel = sz;
		} else if (state.status === 'queued') {
			progressLabel = queuedModelIds.length > 0
				? queuedModelIds.length === 1
					? $i18n.t('Queued (1 remaining)...')
					: $i18n.t('Queued ({{count}} remaining)...', { count: queuedModelIds.length })
				: $i18n.t('Queued...');
		} else if (state.status === 'cancelling') {
			progressLabel = $i18n.t('Canceling and cleaning up files...');
		} else if (state.status === 'completed') {
			progress = 1;
			progressLabel = $i18n.t('Download complete');
		} else if (state.status === 'cancelled') {
			progressLabel = $i18n.t('Download canceled');
		} else if (state.status === 'error') {
			progressLabel = $i18n.t('Download failed');
		}
	};

	const clearDownloadState = () => {
		queueRevision++;
		const queueContinues = queuedModelIds.length > 0;
		if (currentEs) {
			currentEs.close();
		}
		downloading = queueContinues;
		cancelling = false;
		progress = 0;
		progressLabel = queueContinues ? $i18n.t('Preparing next download...') : '';
		currentTaskId = null;
		activeDownloadKey = null;
		currentFilename = '';
		pendingControl = null;
		downloadingModelId = null;
		downloadingModelName = '';
		currentEs = null;
		if (!queueContinues) {
			dismissDownloadProgressToast();
		}
	};

	const startNextQueuedDownload = async () => {
		const pending = queuedModelIds.filter((id) => {
			const request = downloadRequests.get(id);
			return request?.source === 'hf' || request?.source === 'neve' && !catalog.find(model => model.id === id)?.installed;
		});
		for (const id of queuedModelIds) if (!pending.includes(id)) downloadRequests.delete(id);
		const [nextId, ...remaining] = pending;
		queuedModelIds = remaining;
		if (!nextId) { clearDownloadState(); return; }

		await startSingleDownload(nextId);
	};

	async function settleInterrupted(taskId: string, state: NeveDownloadState) {
		if (taskId !== currentTaskId || settledTasks.has(taskId)) return;
		settledTasks.add(taskId);
		if (activeDownloadKey) {
			if (state.status === 'paused') {
				pausedKeys = [...new Set([...pausedKeys, activeDownloadKey])];
				pausedTasks.set(activeDownloadKey, taskId);
			} else downloadRequests.delete(activeDownloadKey);
		}
		clearDownloadState();
		hfRevision++;
		await startNextQueuedDownload();
	}

	async function restorePausedDownloads() {
		try {
			const revision = queueRevision;
			const states = await getPausedNeveDownloads(localStorage.token);
			if (revision !== queueRevision) return;
			for (const state of states) {
				const request: ModelDownloadRequest | undefined = state.repo_id && state.filename
					? { source: 'hf', repo: state.repo_id, filename: state.filename, encoder: state.encoder, name: state.name ?? state.repo_id }
					: state.model_id && !state.model_id.startsWith('hf:') ? { source: 'neve', modelId: state.model_id, filename: state.main_filename, name: state.name ?? state.model_id } : undefined;
				if (!request) continue;
				const key = modelDownloadKey(request);
				if (key === activeDownloadKey || queuedModelIds.includes(key) || removingKeys.includes(key)) continue;
				downloadRequests.set(key, request);
				pausedTasks.set(key, state.task_id);
				pausedKeys = [...new Set([...pausedKeys, key])];
			}
		} catch { /* Paused downloads do not block catalog loading. */ }
	}

	const attachToDownload = (taskId: string, initialState?: NeveDownloadState | null) => {
		if (settledTasks.has(taskId)) return;
		if (!activeDownloadKey && initialState?.model_id) {
			const entry: ModelDownloadRequest | undefined = initialState.repo_id && initialState.filename
				? { source: 'hf', repo: initialState.repo_id, filename: initialState.filename, encoder: initialState.encoder, name: initialState.name ?? initialState.repo_id }
				: !initialState.model_id.startsWith('hf:') ? { source: 'neve', modelId: initialState.model_id, name: initialState.name ?? initialState.model_id } : undefined;
			if (entry) { activeDownloadKey = modelDownloadKey(entry); downloadRequests.set(activeDownloadKey, entry); }
		}
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
			(state) => { if (taskId === currentTaskId && !settledTasks.has(taskId)) applyDownloadState(state); },
			async (state) => {
				if (taskId !== currentTaskId || settledTasks.has(taskId)) return;
				settledTasks.add(taskId);
				const completedId = state.model_id ?? downloadingModelId;
				const name = modelNameFor(completedId);
				huggingFaceModels?.markInstalled(activeDownloadKey ? downloadRequests.get(activeDownloadKey) : undefined);
				if (activeDownloadKey) downloadRequests.delete(activeDownloadKey);
				catalog = catalog.map(item => item.id === completedId ? { ...item, installed: true } : item);
				clearDownloadState();
				// New clicks must queue while installation metadata is being refreshed.
				downloading = true;
				hfRevision++;

				if (state.message === 'Já instalado') {
					toast.info($i18n.t('{{name}}: already installed', { name }));
				} else {
					toast.success($i18n.t('{{name}} downloaded successfully', { name }));
				}

				await loadCatalog();
				const refreshed = await getModels(localStorage.token, null, false, true).catch(() => null);
				if (refreshed) models.set(refreshed);
				dispatch('modelsChanged');
				await startNextQueuedDownload();
			},
			(err: any) => {
				if (taskId !== currentTaskId || settledTasks.has(taskId)) return;
				settledTasks.add(taskId);
				if (activeDownloadKey) downloadRequests.delete(activeDownloadKey);
				clearDownloadState();
				hfRevision++;
				toast.error(normalizeLlamaCppErrorMessage(err, $i18n.t('Download failed')));
				void startNextQueuedDownload();
			},
			(state) => { void settleInterrupted(taskId, state); },
			(state) => { void settleInterrupted(taskId, state); }
		);
		if (pendingControl) { const action = pendingControl; pendingControl = null; cancelling = false; void controlActiveDownload(action); }
	};

	const hydrateModal = async () => {
		void restorePausedDownloads();
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
				$i18n.t('Failed to load catalog')
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
		void restorePausedDownloads();
		try {
			const activeDownload = await getActiveNeveDownload(localStorage.token);
			if (activeDownload?.task_id) {
				attachToDownload(activeDownload.task_id, activeDownload);
			} else {
				progressToastVisible = false;
			}
		} catch {
			// The visible modal load path will surface backend/catalog failures when the user opens it.
		}
	};


	$: if (show && !wasShown) {
		wasShown = true;
		query = '';
		void hydrateModal();
	} else if (!show && wasShown) {
		wasShown = false;
		openModelInfoId = null;
		showDownloadDetails = false;
	}

	$: if (downloading && !show && !interfaceBlockersOpen && !$showArtifacts && downloadingModelName) {
		showDownloadProgressToast();
	} else {
		dismissDownloadProgressToast();
	}

	async function startSingleDownload(modelId: string) {
		const entry = downloadRequests.get(modelId);
		if (!entry) return;

		downloading = true;
		cancelling = false;
		activeDownloadKey = modelId;
		downloadingModelId = modelId;
		downloadingModelName = entry.name;
		progress = 0;
		progressLabel = $i18n.t('Connecting...');

		try {
			const activeDownload = await getActiveNeveDownload(localStorage.token);
			if (activeDownload?.task_id) {
				attachToDownload(activeDownload.task_id, activeDownload);
				if (activeDownload.model_id !== modelId) queuedModelIds = [modelId, ...queuedModelIds.filter(id => id !== modelId)];
				activeDownloadKey = activeDownload.model_id ?? null;
				return;
			}

			if (entry.source === 'hf') {
				const task = await downloadHFModel(localStorage.token, entry.repo, entry.filename, entry.encoder);
				attachToDownload(task.task_id, task);
			} else {
				const taskId = await startNeveDownload(localStorage.token, entry.modelId);
				attachToDownload(taskId, { task_id: taskId, model_id: modelId, name: entry.name, status: 'queued', progress: 0 });
			}
		} catch (e: any) {
			downloadRequests.delete(modelId);
			clearDownloadState();
			toast.error(normalizeLlamaCppErrorMessage(e, 'Falha ao iniciar download'));
			await startNextQueuedDownload();
		}
	}

	function queueDownload(request: ModelDownloadRequest) {
		const key = modelDownloadKey(request);
		if (cancelling || removingKeys.includes(key) || key === activeDownloadKey || queuedModelIds.includes(key)) return;
		if (request.source === 'neve' && catalog.find(model => model.id === request.modelId)?.installed) return;
		preserveDownloadControlFocus();
		downloadRequests.set(key, request);
		queueRevision++;
		pausedKeys = pausedKeys.filter(id => id !== key);
		pausedTasks.delete(key);
		if (request.source === 'neve') { const item = catalog.find(item => item.id === request.modelId); if (item) void loadInfoSize(item); }
		if (downloading || currentTaskId) queuedModelIds = [...queuedModelIds, key];
		else void startSingleDownload(key);
	}

	const handleCancelDownload = async () => {
		await controlActiveDownload('cancel');
	};
	const handlePauseDownload = () => controlActiveDownload('pause');

	async function controlActiveDownload(action: 'cancel' | 'pause') {
		if (!downloading || cancelling) return;
		preserveDownloadControlFocus();
		cancelling = true;
		if (!currentTaskId) { pendingControl = action; return; }
		const taskId = currentTaskId;
		try {
			const state = await (action === 'pause' ? pauseNeveDownload : cancelNeveDownload)(localStorage.token, taskId);
			if (taskId !== currentTaskId || settledTasks.has(taskId)) return;
			applyDownloadState(state);
			if (['cancelled', 'paused'].includes(state.status)) await settleInterrupted(taskId, state);
			else if (state.status === 'error') { settledTasks.add(taskId); clearDownloadState(); await startNextQueuedDownload(); }
		} catch (e: any) {
			if (taskId !== currentTaskId || settledTasks.has(taskId)) return;
			cancelling = false;
			toast.error(normalizeLlamaCppErrorMessage(e, 'Falha ao cancelar download'));
		}
	}

	async function cancelQueuedDownload(key: string) {
		if (removingKeys.includes(key)) return;
		preserveDownloadControlFocus();
		queueRevision++;
		removingKeys = [...removingKeys, key];
		const pausedTask = pausedTasks.get(key);
		if (pausedTask) {
			try { await cancelNeveDownload(localStorage.token, pausedTask); }
			catch (error) { toast.error(normalizeLlamaCppErrorMessage(error)); removingKeys = removingKeys.filter(id => id !== key); return; }
		}
		queuedModelIds = queuedModelIds.filter(id => id !== key);
		pausedKeys = pausedKeys.filter(id => id !== key);
		pausedTasks.delete(key);
		downloadRequests.delete(key);
		removingKeys = removingKeys.filter(id => id !== key);
	}

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
		neveDownloadToast.set(null);
		if (currentEs) {
			currentEs.close();
			currentEs = null;
		}
	});
</script>

<svelte:window on:keydown|capture={(event) => {
	if (event.key === 'Escape' && openModelInfoId !== null) {
		event.stopPropagation();
		event.preventDefault();
		openModelInfoId = null;
	}
}} />

{#snippet downloadHub()}
	<div bind:this={downloadHubElement} data-model-download-hub tabindex="-1" class="download-models-shell flex h-full min-h-0 flex-col overflow-hidden outline-none">
		<div
			class="grid grid-cols-[minmax(0,1fr)_auto] md:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center gap-3 mx-4 pt-4 pb-6 shrink-0"
		>
			<div class="order-1 md:order-none flex min-w-0 items-center gap-2 text-lg font-medium text-gray-700 dark:text-gray-100">
				<MobileModalTitle onBack={() => { if (embedded) onBack(); else show = false; }} contentClass="truncate"><span class="truncate">{$i18n.t('Baixar modelos')}</span></MobileModalTitle>
			</div>
			<div class="search-field order-3 md:order-none col-span-2 md:col-span-1 justify-self-center">
				<div class="search-surface flex shrink-0 items-center w-full px-2.5">
					<div class="flex min-w-0 flex-1 items-center">
						<div class="self-center ml-1 mr-3"><Search className="size-3.5" /></div>
						<input maxlength="200" bind:value={query} aria-label={$i18n.t('Search', { context: 'models' })} placeholder={$i18n.t('Search', { context: 'models' })} class="min-w-0 w-full text-sm py-1.5 rounded-r-xl outline-hidden bg-transparent" />
					</div>
				</div>
			</div>
			<div class="order-2 md:order-none h-8 justify-self-end flex items-center gap-1.5">
				{#if downloading || pausedKeys.length > 0 || showDownloadDetails}
					<Dropdown
						bind:show={showDownloadDetails}
						on:change={(event) => { if (!event.detail && downloadMenuElement && downloadHubElement) requestModalFocus?.(downloadHubElement); }}
						align="end"
						triggerClassName="group relative grid size-8 shrink-0 place-items-center p-0"
					>
						<span aria-label="Progresso do download" class="grid size-5 place-items-center">
							<span class="pointer-events-none absolute inset-[3px] rounded-full bg-gray-800 transition group-hover:bg-gray-700 dark:bg-gray-800 dark:group-hover:bg-gray-700"></span>
							<svg
								aria-hidden="true"
								class="pointer-events-none absolute inset-0 size-8 -rotate-90"
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
							<svg data-download-progress-icon aria-hidden="true" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" class="relative z-10 block size-5 text-gray-400">
								<path stroke-linecap="round" stroke-linejoin="round" d="M3 16.5v2.25A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V16.5M16.5 12 12 16.5m0 0L7.5 12m4.5 4.5V3" />
							</svg>
						</span>

						<div slot="content">
							<DropdownMenu.Content
								data-download-progress-menu
								bind:el={downloadMenuElement}
								tabindex={-1}
								class="z-[10002] w-[19rem] rounded-lg border border-gray-200 bg-white {downloading ? 'px-3 pt-3 pb-2' : 'p-3'} shadow-lg dark:border-gray-800 dark:bg-gray-850 dark:text-white"
								side="bottom"
								align="end"
								sideOffset={7}
								transition={(node) => fade(node, { duration: 100 })}
							>
								<!-- svelte-ignore a11y_no_noninteractive_tabindex a11y_no_noninteractive_element_interactions (Focus enters the download group, not Pause; Tab reaches its controls.) -->
								<div tabindex="0" role="group" aria-label={$i18n.t('Downloads')} class="outline-none" on:keydown={(event) => { if (event.key === 'Tab') event.stopPropagation(); }}>
								{#if downloading}
								<div class="mb-2 flex min-w-0 items-center gap-1">
									<div data-current-download class="min-w-0 flex-1 truncate text-sm font-medium">{downloadLabel(activeDownloadKey)}</div>
									<button data-pause-download type="button" title={$i18n.t('Pause')} aria-label={$i18n.t('Pause')} disabled={cancelling} class="grid size-7 shrink-0 place-items-center rounded-md text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800 disabled:opacity-40" on:click={() => controlActiveDownload('pause')}><Pause /></button>
									<button data-cancel-download type="button" title={$i18n.t('Cancel')} aria-label={$i18n.t('Cancel')} disabled={cancelling} class="grid size-7 shrink-0 place-items-center rounded-md text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800 disabled:opacity-40" on:click={handleCancelDownload}>{#if cancelling}<Spinner className="size-4" />{:else}<XCircle />{/if}</button>
								</div>
								<div data-download-progress-bar class="h-1.5 w-full overflow-hidden rounded-full bg-gray-100 dark:bg-gray-800">
									<div
										class="h-full bg-black transition-all dark:bg-white"
										style="width: {Math.min(100, Math.max(0, progress * 100))}%"
									></div>
								</div>
								<div data-download-progress-label class="mt-2 flex justify-between gap-3 text-xs text-gray-500 dark:text-gray-400">
									<span class="min-w-0 truncate">{progressLabel}</span>
									<span class="shrink-0">{Math.round(progress * 100)}%</span>
								</div>
								{/if}
								{#if queuedModelIds.length || pausedKeys.length}
									<div data-download-queue-section class={downloading ? 'mt-3 border-t border-gray-100 pt-2 dark:border-gray-800' : ''}>
									<div data-download-queue class="max-h-36 overflow-y-auto overscroll-contain {queuedModelIds.length + pausedKeys.length > 3 ? 'pr-1 [scrollbar-gutter:stable]' : ''}">
										{#each [...queuedModelIds, ...pausedKeys] as key (key)}
											<div data-queued-download={key} class="flex min-w-0 items-center gap-1 { !downloading && queuedModelIds.length + pausedKeys.length === 1 ? 'py-0' : 'py-1' } text-xs text-gray-500 dark:text-gray-400"><span class="min-w-0 flex-1 truncate">{downloadLabel(key)}</span>{#if pausedKeys.includes(key)}<button data-resume-download type="button" aria-label={$i18n.t('Resume')} title={$i18n.t('Resume')} class="grid size-7 shrink-0 place-items-center rounded-md hover:bg-gray-100 dark:hover:bg-gray-800" on:click={() => { const request = downloadRequests.get(key); if (request) queueDownload(request); }}><svg aria-hidden="true" class="size-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path stroke-linejoin="round" d="m8 5 11 7-11 7Z" /></svg></button>{/if}<button data-cancel-queued type="button" aria-label={$i18n.t('Cancel')} title={$i18n.t('Cancel')} class="grid size-7 shrink-0 place-items-center rounded-md hover:bg-gray-100 dark:hover:bg-gray-800" on:click={() => cancelQueuedDownload(key)}><XCircle /></button></div>
										{/each}
									</div>
									</div>
								{/if}
								</div>
							</DropdownMenu.Content>
						</div>
					</Dropdown>
				{/if}
				<button data-mobile-modal-close aria-label={$i18n.t('Close')}
					class="download-models-close grid size-8 shrink-0 place-items-center self-center p-0 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 transition"
					on:click={() => {
						if (embedded) onBack(); else show = false;
					}}
				>
					<XMark className={'size-5'} />
				</button>
			</div>
		</div>

		<div class="download-models-body flex min-h-0 w-full flex-1 flex-col overflow-hidden px-4 pt-3 pb-7 dark:text-gray-200">
			<div bind:this={catalogScroller} data-download-list class:catalog-section-scroll={!hfDetailOpen} class="download-models-list min-h-0 flex-1 pr-2 [scrollbar-gutter:stable] {hfDetailOpen ? 'overflow-hidden' : 'overflow-y-auto overscroll-contain'}">
				<div data-catalog-section-heading class:hidden={hfDetailOpen || (query.trim().length > 0 && visibleCatalog.length === 0)} class="sticky top-0 z-20 h-10 bg-white dark:bg-gray-900">
					<button type="button" data-neve-section-toggle class:invisible={hfHeaderActive} disabled={!hfHasResults} aria-expanded={neveExpanded} aria-controls="neve-catalog-items" class="mb-2 flex h-8 items-center gap-2 px-3 text-sm text-gray-500 dark:text-gray-400 disabled:cursor-default" on:click={() => { if (hfHasResults) neveExpanded = !neveExpanded; }}>
						<img src={`${NEVEAI_BASE_URL}/static/logoselector.svg`} alt="" class="size-6 brightness-0 opacity-55 dark:invert dark:opacity-65" /><span>Neve</span>{#if hfHasResults}<span class="relative top-px inline-flex shrink-0"><ChevronUpCompact className={`size-3.5 shrink-0 transition-transform ${neveExpanded ? '' : 'rotate-180'}`} /></span>{/if}
					</button>
				</div>
			<section class={neveExpanded ? 'pb-5' : 'pb-1'} class:hidden={hfDetailOpen || (query.trim().length > 0 && visibleCatalog.length === 0)}>
				<div id="neve-catalog-items" hidden={!neveExpanded}>
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
					<div data-download-grid class="grid grid-cols-1 md:grid-cols-2 gap-x-4 gap-y-2">
					{#each visibleCatalog as item (item.id)}
						{@const isCurrentDownload = downloading && (activeDownloadKey ?? downloadingModelId) === item.id}
						{@const isQueuedDownload = queuedModelIds.includes(item.id)}
						<div
							data-catalog-model={item.id} tabindex="-1" role="group" aria-label={item.name} class="catalog-model-card relative box-border h-[72px] min-h-[72px] min-w-0 rounded-lg border bg-gray-50 dark:bg-gray-850/50 outline-none {item.installed
								? 'border-transparent'
								: isCurrentDownload || isQueuedDownload
								? `${downloading ? 'cursor-default' : ''} border-gray-300 dark:border-gray-700`
									: 'border-transparent'}"
						>
							<div class="catalog-model-row grid h-full grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-3 px-3">
								<img
									src={`${NEVEAI_BASE_URL}/static/logoselector.svg`}
									alt=""
									class="size-9 shrink-0 object-contain brightness-0 dark:invert {item.installed ? 'opacity-40' : 'opacity-55 dark:opacity-65'}"
								/>

								<div class="catalog-model-label grid min-w-0 gap-1 self-center {item.installed ? 'opacity-70' : ''}">
									<div class="catalog-model-heading min-w-0 overflow-hidden">
										<span class="catalog-model-name block min-w-0 truncate text-sm font-medium leading-5">
										{item.repo?.split('/').slice(1).join('/') || item.name}
									</span>
									</div>
									<span class="catalog-model-owner block truncate text-xs text-gray-500">{item.repo?.split('/')[0] || 'NeveAI'}</span>
								</div>
								<div class="catalog-model-actions flex w-[calc(4.5rem_-_1ch)] min-w-0 items-center justify-end gap-1 self-center text-sm">
								{#if isCurrentDownload || isQueuedDownload}
									<span data-download-status class="mr-1 text-xs font-medium whitespace-nowrap text-gray-500 dark:text-gray-400">{$i18n.t(isCurrentDownload ? 'Downloading' : 'Queued')}</span>
								{:else}
								<ModelInformation modelId={item.id} bind:openId={openModelInfoId} active={show} description={$i18n.t(item.description ?? '')} size={infoSizes[item.repo]?.length ? fmtBytes(infoSizes[item.repo][0].size) : item.size_label ?? ''} onOpen={() => { void loadInfoSize(item); }} />
								{#if item.installed}
									<button type="button" class="grid size-7 shrink-0 place-items-center rounded-md p-0 text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800 disabled:opacity-50" disabled={uninstallingModelId === item.id} title={$i18n.t('Delete model')} aria-label={$i18n.t('Uninstall {{name}}', { name: item.name })} on:click|preventDefault|stopPropagation={() => requestUninstall(item)}>
										{#if uninstallingModelId === item.id}<Spinner className="size-4" />{:else}<Trash className="block size-4" />{/if}
									</button>
								{/if}
								{#if !item.installed}
									<button type="button" data-download-model={item.id} aria-label={$i18n.t('Download')} title={$i18n.t('Download')} disabled={loading || cancelling} class="grid size-7 shrink-0 place-items-center rounded-md p-0 text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800" on:click={(event) => { event.currentTarget.closest<HTMLElement>('[data-catalog-model]')?.focus({ preventScroll: true }); queueDownload({ source: 'neve', modelId: item.id, name: item.name }); }}><Download className="block size-4" /></button>
								{/if}
								{/if}
								</div>
							</div>

						</div>
					{/each}
					</div>
				{/if}
				</div>
			</section>
			<div class={hfDetailOpen ? 'h-full min-h-0' : ''}><HuggingFaceModels bind:this={huggingFaceModels} {query} stickyActive={hfHeaderActive} onStickyChange={(stuck) => hfHeaderActive = stuck} collapsible={neveExpanded} active={show} bind:detailOpen={hfDetailOpen} bind:hasResults={hfHasResults} bind:settledQuery={hfSettledQuery} activeKey={activeDownloadKey} activeRequest={activeDownloadKey ? downloadRequests.get(activeDownloadKey) : undefined} queuedRequests={queuedModelIds.map(key => downloadRequests.get(key)).filter((request): request is ModelDownloadRequest => !!request)} queuedKeys={queuedModelIds} blocked={cancelling} revision={hfRevision} onQueue={queueDownload} /></div>
			{#if !hfDetailOpen && query.trim() && visibleCatalog.length === 0 && !hfHasResults && hfSettledQuery === query.trim()}
				<div data-catalog-empty class="py-8 text-center text-sm text-gray-500 dark:text-gray-400">{$i18n.t('No models found')}</div>
			{/if}
			</div>
		</div>
	</div>
{/snippet}

{#if embedded}
	<div class="h-full min-h-0" class:hidden={!show}>{@render downloadHub()}</div>
{:else}
	<Modal bind:show mobileFullscreen animated={false} size="w-[44rem]" containerClassName="p-2 sm:p-3" className="bg-white dark:bg-gray-900 rounded-xl h-[min(640px,90dvh)] overflow-hidden">
		{@render downloadHub()}
	</Modal>
{/if}

<ConfirmDialog
	bind:show={showUninstallConfirm}
	animated={false}
	title={$i18n.t('Uninstall model?')}
	message={`Tem certeza que deseja desinstalar ${uninstallTarget?.name ?? 'este modelo'}?`}
	confirmLabel="Confirmar"
	cancelLabel={$i18n.t('Cancel')}
	onConfirm={confirmUninstall}
	on:cancel={() => {
		uninstallTarget = null;
	}}
/>

<style>
	.catalog-section-scroll::-webkit-scrollbar-track { margin-top: 2.5rem; }
	@media (max-width: 767px) {
		.download-models-shell { height: 100%; max-height: 100%; }
		.download-models-close { display: none; }
		.download-models-body { flex: 1; padding-inline: 12px; }
		.download-models-list { flex: 1; height: auto; min-height: 0; }
		.catalog-model-row { grid-template-columns: auto minmax(0, 1fr) auto; gap: 14px; padding-inline: 8px; }
		.catalog-model-row > img { width: 2.25rem; height: 2.25rem; }
		.catalog-model-card { height: 72px; min-height: 72px; max-height: 72px; }
		.catalog-model-heading { flex-wrap: nowrap; }
		.catalog-model-name { flex: 0 1 auto; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
	}
	.catalog-model-row { grid-template-columns: auto minmax(0, 1fr) auto; }
</style>
