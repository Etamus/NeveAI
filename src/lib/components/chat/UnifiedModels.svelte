<script lang="ts" context="module">
	import { get as getStoreValue, writable } from 'svelte/store';

	type LocalModelAction = 'load' | 'unload';
	type LocalModelProcessingState = {
		loading: string[];
		settlingUnload: string[];
		pinnedUnload: string[];
		visualUnload: string[];
		actions: Record<string, LocalModelAction>;
	};

	const localModelProcessingStore = writable<LocalModelProcessingState>({
		loading: [],
		settlingUnload: [],
		pinnedUnload: [],
		visualUnload: [],
		actions: {}
	});
	const localActionRefreshTimers = new Map<string, ReturnType<typeof setTimeout>>();
	const localActionReleaseTimers = new Map<string, ReturnType<typeof setTimeout>>();
	const localVisualUnloadClearTimers = new Map<string, ReturnType<typeof setTimeout>>();
	const localActionReleasePending = new Set<string>();
	const localActionReleaseTokens = new Map<string, number>();
</script>

<script lang="ts">
	import { onMount, onDestroy, getContext, tick, createEventDispatcher } from 'svelte';
	import { marked } from 'marked';
	import { modelGridWheel } from '$lib/utils/modelGridWheel';
	import type { I18nStore } from '$lib/i18n';
	const i18n = getContext<I18nStore>('i18n');

	import { config, models as _models, settings, showSettingsModelId, mobile } from '$lib/stores';
	import { modelAvailability, projectAvailableModels, refreshModelAvailability } from '$lib/stores/modelAvailability';
	import { NEVEAI_API_BASE_URL } from '$lib/constants';
	import { page } from '$app/stores';

	import {
		getLocalModels,
		getLlamaCppStatus,
		getMmProjFiles,
		getLocalVramInfo,
		getLatestLocalModelRuntimeEvent,
		loadLocalModel,
		LOCAL_MODEL_RUNTIME_EVENT,
		normalizeLlamaCppErrorMessage,
		unloadLocalModel,
		deleteLocalModel,
		importLocalModel,
		type LlamaCppStatus,
		type LocalModel,
		type LocalModelRuntimeEventDetail,
		type LocalVramInfo
	} from '$lib/apis/llamacpp';

	import { createNewModel, getBaseModels, deleteModelById, updateModelById } from '$lib/apis/models';
	import ConfirmDialog from '$lib/components/common/ConfirmDialog.svelte';
	import Trash from '$lib/components/icons/Trash.svelte';
	import ArrowUpDown from '$lib/components/icons/ArrowUpDown.svelte';
	import { Columns2, Rows2 } from '@lucide/svelte';
	import { DropdownMenu } from 'bits-ui';
	import UnloadModel from '$lib/components/icons/UnloadModel.svelte';
	import Download from '$lib/components/icons/ModelCatalog.svelte';
	import Upload from '$lib/components/icons/Upload.svelte';
	import { getModels } from '$lib/apis';
	import { toggleModelFavorite } from '$lib/utils/modelFavoriteActions';
	import { toast } from 'svelte-sonner';
	import { findMatchingMmproj } from '$lib/utils/mmproj';
	import { getLocalModelLoadPreferences } from '$lib/utils/llamacppLoadPreferences';
	import { messageSnapshotEqual } from '$lib/utils/messageSnapshot';
	import {
		buildUnifiedAdminModels,
		type UnifiedModelsPreload
	} from '$lib/utils/unifiedModelsData';

	import DownloadNeveModelsModal from '$lib/components/chat/DownloadNeveModelsModal.svelte';
	import MobileModalTitle from '$lib/components/common/MobileModalTitle.svelte';
	import ModelEditor from '$lib/components/workspace/Models/ModelEditor.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import Dropdown from '$lib/components/common/Dropdown.svelte';
	import Spinner from '$lib/components/common/Spinner.svelte';
	import { continuousSpinner } from '$lib/utils/continuousSpinner';
	import Search from '$lib/components/icons/Search.svelte';
	import ChevronDown from '$lib/components/icons/ChevronDown.svelte';
	import ChevronUp from '$lib/components/icons/ChevronUp.svelte';
	import EllipsisHorizontal from '$lib/components/icons/EllipsisHorizontal.svelte';
	import Bookmark from '$lib/components/icons/Bookmark.svelte';
	import CheckCircle from '$lib/components/icons/CheckCircle.svelte';
	import Minus from '$lib/components/icons/Minus.svelte';

	export let preload: UnifiedModelsPreload | null = null;
	export let show = false;

	// ─── LOCAL MODEL STATE ───────────────────────────────────────────────────
	let localModels: LocalModel[] = preload?.loaded ? (preload.localModels ?? []) : [];
	let mmProjFiles: string[] = preload?.loaded ? (preload.mmProjFiles ?? []) : [];
	let localLoading = !preload?.loaded;
	let loadingModels: Set<string> = new Set();
	let settlingUnloadModels: Set<string> = new Set();
	let pinnedUnloadModels: Set<string> = new Set();
	let visualUnloadModels: Set<string> = new Set();
	let reopenedUnloadVisualModels: Set<string> = new Set();
	let localModelActions: Record<string, 'load' | 'unload'> = {};
	let localError = '';
	let localSuccess = '';
	let vramInfo: LocalVramInfo | null = preload?.loaded ? (preload.vramInfo ?? null) : null;
	let llamacppStatus: LlamaCppStatus | null = null;
	let vramPreviewModel: LocalModel | null = null;
	const unsubscribeLocalModelProcessing = localModelProcessingStore.subscribe((state) => {
		loadingModels = new Set(state.loading);
		settlingUnloadModels = new Set(state.settlingUnload);
		pinnedUnloadModels = new Set(state.pinnedUnload);
		visualUnloadModels = new Set(state.visualUnload);
		localModelActions = state.actions;
	});



	let gpuLayers: number = -1;
	let contextSize: number = 8192;


	const getCacheTypeForLoad = () => {
		const { cache } = getLocalModelLoadPreferences();
		return cache === 'default' ? 'f16' : cache;
	};

	const getSpeculativeDecodingForLoad = () => {
		const { speculative } = getLocalModelLoadPreferences();
		return getContextShiftForLoad() === 'on' || getTokenPredictionForLoad() === 'on'
			? 'off'
			: speculative === 'default'
				? 'off'
				: speculative;
	};

	const getTokenPredictionForLoad = () => {
		const { tokenPrediction } = getLocalModelLoadPreferences();
		return tokenPrediction;
	};

	const getContextShiftForLoad = () => {
		const { contextShift } = getLocalModelLoadPreferences();
		return contextShift;
	};

	const clampPercent = (value: number) => Math.max(0, Math.min(100, value));
	const percentOf = (value: number, total: number) => (total > 0 ? clampPercent((value / total) * 100) : 0);
	const formatBytes = (bytes: number) => {
		if (!Number.isFinite(bytes) || bytes <= 0) return '0 B';
		const units = ['B', 'KB', 'MB', 'GB', 'TB'];
		let value = bytes;
		let unitIndex = 0;
		while (value >= 1024 && unitIndex < units.length - 1) {
			value /= 1024;
			unitIndex += 1;
		}
		return `${value.toFixed(value >= 10 || unitIndex === 0 ? 0 : 1)} ${units[unitIndex]}`;
	};
	const getSystemVramBarStyle = (leftPercent: number, widthPercent: number) =>
		`left: ${leftPercent}%; width: ${widthPercent}%; background-color: rgba(107, 114, 128, 0.5); background-image: repeating-linear-gradient(135deg, rgba(255, 255, 255, 0.38) 0, rgba(255, 255, 255, 0.38) 4px, transparent 4px, transparent 8px);`;
	const getModelVramBarStyle = (
		leftPercent: number,
		widthPercent: number,
		hasRamFallback: boolean,
		modelBytes: number,
		totalBytes: number
	) => {
		const color = hasRamFallback
			? 'rgba(239, 68, 68, 0.88)'
			: totalBytes > 0 && modelBytes > totalBytes / 2
				? 'rgba(245, 158, 11, 0.9)'
				: 'rgba(229, 231, 235, 0.95)';
		return `left: ${leftPercent}%; width: ${widthPercent}%; background-color: ${color};`;
	};
	const getSegmentWidthPercent = (bytes: number, total: number, leftPercent: number) =>
		Math.max(0, Math.min(100 - leftPercent, percentOf(bytes, total)));
	const estimateModelVramBytes = (
		model: LocalModel,
		targetContext = contextSize,
		targetGpuLayers = gpuLayers
	) => {
		const cacheType = getCacheTypeForLoad();
		const cacheMultiplier = cacheType === 'f16' ? 2 : cacheType === 'q4_0' ? 0.55 : 1;
		const gpuRatio = targetGpuLayers === -1 ? 1 : Math.max(0, Math.min(1, targetGpuLayers / 80));
		const offloaded = targetGpuLayers !== -1;
		const modelBytes = model.file_size * (targetGpuLayers === 0 ? 0 : offloaded ? Math.max(0.12, gpuRatio) : 1);
		const contextBytes = targetContext * 64 * 1024 * cacheMultiplier * (targetGpuLayers === 0 ? 0 : Math.max(0.25, gpuRatio || 0.25));
		return Math.max(0, Math.round(modelBytes + contextBytes));
	};
	const showVramPreview = (model: LocalModel) => {
		if (loadedLocalModel || loadingModels.size > 0) return;
		vramPreviewModel = model;
	};
	const clearVramPreview = (model: LocalModel) => {
		if (vramPreviewModel?.filename === model.filename) vramPreviewModel = null;
	};

	let manualRuntimeUpdatedAt = 0;
	$: modelsBlocked = !$modelAvailability.known || $modelAvailability.busy;
	$: visibleLocalModels = projectAvailableModels(localModels, $modelAvailability, localModelsSnapshotAt, manualRuntimeUpdatedAt);
	$: loadedLocalModel = visibleLocalModels.find((model) => model.is_loaded) ?? null;
	$: localModelActionInProgress = modelsBlocked || deletingModel || loadingModels.size > 0 || settlingUnloadModels.size > 0;
	$: vramTotalBytes = vramInfo?.total ?? 0;
	$: vramActualUsed = vramInfo?.used ?? 0;
	$: vramPreviewBytes = vramPreviewModel ? estimateModelVramBytes(vramPreviewModel) : 0;
	$: vramPreviewBaselineUsed = vramInfo && vramPreviewModel
		? vramActualUsed
		: vramActualUsed;
	$: vramProjectedUsed = vramInfo && vramPreviewModel ? vramPreviewBaselineUsed + vramPreviewBytes : vramActualUsed;
	$: vramSystemSegmentBytes = vramPreviewModel ? vramPreviewBaselineUsed : vramActualUsed;
	$: vramModelSegmentBytes = vramPreviewModel ? vramPreviewBytes : 0;
	$: vramSystemSegmentPercent = percentOf(vramSystemSegmentBytes, vramTotalBytes);
	$: vramModelSegmentStartPercent = vramSystemSegmentPercent;
	$: vramModelSegmentWidthPercent = getSegmentWidthPercent(
		vramModelSegmentBytes,
		vramTotalBytes,
		vramModelSegmentStartPercent
	);
	$: vramProjectedOffloadBytes = vramInfo && vramPreviewModel ? Math.max(0, vramProjectedUsed - vramInfo.total) : 0;
	$: loadedModelHasOffload = Boolean(
		loadedLocalModel && loadedLocalModel.n_gpu_layers !== null && loadedLocalModel.n_gpu_layers !== -1
	);
	$: vramModelSegmentHasRamFallback = vramPreviewModel ? vramProjectedOffloadBytes > 0 : loadedModelHasOffload;
	$: vramDisplayedUsedBytes = vramPreviewModel ? vramProjectedUsed : vramActualUsed;
	$: vramDisplayedFreeBytes = vramTotalBytes > 0 ? Math.max(0, vramTotalBytes - vramDisplayedUsedBytes) : 0;
	$: if ((loadedLocalModel || loadingModels.size > 0) && vramPreviewModel) {
		vramPreviewModel = null;
	}

	// ─── ADMIN MODEL STATE ───────────────────────────────────────────────────

	let adminModels: any[] = preload?.loaded ? (preload.adminModels ?? []) : [];
	let workspaceModels: any[] | null = preload?.loaded ? (preload.workspaceModels ?? []) : null;
	let baseModels: any[] | null = preload?.loaded ? (preload.baseModels ?? []) : null;
	let selectedModelId: string | null = null;
	export let mobileStep = '';
	let showDownloadModal = false;
	let downloadHub: DownloadNeveModelsModal;
	let importingModel = false;
	let modelImportInput: HTMLInputElement;
	async function importModelFile(event: Event) {
		const input = event.currentTarget as HTMLInputElement;
		const file = input.files?.[0];
		input.value = '';
		if (!file || importingModel) return;
		importingModel = true;
		try {
			await importLocalModel(localStorage.token, file);
			await refreshAfterCatalogChange();
			toast.success($i18n.t('Model imported'));
		} catch (error) {
			toast.error(normalizeLlamaCppErrorMessage(error, $i18n.t('Failed to import model')));
		} finally {
			importingModel = false;
		}
	}
	$: mobileStep = showDownloadModal ? 'downloads' : selectedModelId ?? '';
	let preloadApplied = false;
	let appliedPreload: UnifiedModelsPreload | null = null;
	let localModelsSnapshotAt = 0;
	let preloadVramSignature = '';
	let catalogSnapshotAt = 0;
	let catalogRevision = 0;
	let showDeleteModel = false;
	let modelToDelete: { gguf: LocalModel | null; admin: any } | null = null;
	let deletingModel = false;
	let enablingModel = false;
	let publishedCatalog: unknown = null;
	const dispatch = createEventDispatcher();
	const publishCatalog = (timestamp = Date.now(), force = true) => {
		catalogSnapshotAt = Math.max(catalogSnapshotAt, timestamp);
		const catalog = { adminModels, workspaceModels, baseModels };
		if (!force && messageSnapshotEqual(publishedCatalog, catalog)) return;
		publishedCatalog = catalog;
		dispatch('catalogChange', { catalogUpdatedAt: catalogSnapshotAt, ...catalog });
	};
	let previousShow = false;
	let destroyed = false;
	let openingActionRefreshInProgress = false;
	let unifiedRefreshInFlight: Promise<LocalModel[] | null> | null = null;
	let unifiedRefreshRequested = false;
	let unifiedRefreshRequestedInitial = false;
	let realtimeRefreshTimer: ReturnType<typeof setTimeout> | null = null;
	let lastAdminRefreshAt = 0;
	const ignoredRuntimeOperationIds = new Set<string>();

	const LOCAL_UNLOAD_REOPEN_PIN_MS = 140;
	const LOCAL_UNLOAD_VISUAL_CLEAR_MS = 900;

	$: hasCachedModelRows = localModels.length > 0 || (adminModels?.length ?? 0) > 0;
	$: localAccessError = Boolean(localError && !localModelActionInProgress && !hasCachedModelRows);

	// ─── SHARED SEARCH ──────────────────────────────────────────────────────
	let searchValue = '';

	const uniqueFilenames = (filenames: string[]) => [...new Set(filenames.filter(Boolean))];
	const cancelLocalActionRefresh = (filename: string) => {
		const timer = localActionRefreshTimers.get(filename);
		if (timer) {
			clearTimeout(timer);
			localActionRefreshTimers.delete(filename);
		}
	};
	const cancelLocalActionRelease = (filename: string) => {
		const timer = localActionReleaseTimers.get(filename);
		if (timer) {
			clearTimeout(timer);
			localActionReleaseTimers.delete(filename);
		}
		localActionReleasePending.delete(filename);
		localActionReleaseTokens.set(filename, (localActionReleaseTokens.get(filename) ?? 0) + 1);
	};
	const cancelVisualUnloadClear = (filename: string) => {
		const timer = localVisualUnloadClearTimers.get(filename);
		if (timer) {
			clearTimeout(timer);
			localVisualUnloadClearTimers.delete(filename);
		}
	};
	const clearLocalModelVisualUnload = (filename: string) => {
		cancelVisualUnloadClear(filename);
		localModelProcessingStore.update((state) => ({
			...state,
			visualUnload: state.visualUnload.filter((f) => f !== filename)
		}));
	};
	const scheduleVisualUnloadClear = (filename: string) => {
		cancelVisualUnloadClear(filename);
		const timer = setTimeout(() => {
			localVisualUnloadClearTimers.delete(filename);
			const state = getStoreValue(localModelProcessingStore);
			if (
				state.actions[filename] === 'unload' ||
				state.pinnedUnload.includes(filename) ||
				highlightedLoadedItem?.gguf?.filename === filename
			) {
				scheduleVisualUnloadClear(filename);
				return;
			}
			clearLocalModelVisualUnload(filename);
		}, LOCAL_UNLOAD_VISUAL_CLEAR_MS);
		localVisualUnloadClearTimers.set(filename, timer);
	};
	const cancelOrphanedLocalActionTimers = () => {
		const { actions } = getStoreValue(localModelProcessingStore);
		const activeFilenames = new Set(Object.keys(actions));

		[...localActionRefreshTimers.keys()].forEach((filename) => {
			if (!activeFilenames.has(filename)) cancelLocalActionRefresh(filename);
		});
		[...localActionReleaseTimers.keys()].forEach((filename) => {
			if (!activeFilenames.has(filename)) cancelLocalActionRelease(filename);
		});
		[...localActionReleasePending].forEach((filename) => {
			if (!activeFilenames.has(filename)) localActionReleasePending.delete(filename);
		});
		localModelProcessingStore.update((state) => ({
			...state,
			pinnedUnload: state.pinnedUnload.filter((filename) => activeFilenames.has(filename)),
			visualUnload: state.visualUnload.filter(
				(filename) => activeFilenames.has(filename) || localVisualUnloadClearTimers.has(filename)
			)
		}));
	};
	const cancelAllLocalActionTimers = () => {
		[...localActionRefreshTimers.keys()].forEach(cancelLocalActionRefresh);
		[...localActionReleaseTimers.keys()].forEach(cancelLocalActionRelease);
		[...localVisualUnloadClearTimers.keys()].forEach(cancelVisualUnloadClear);
		localActionReleasePending.clear();
	};
	const setLocalModelAction = (filename: string, action: 'load' | 'unload') => {
		cancelLocalActionRefresh(filename);
		cancelLocalActionRelease(filename);
		cancelVisualUnloadClear(filename);
		localModelProcessingStore.update((state) => ({
			loading: uniqueFilenames([...state.loading, filename]),
			settlingUnload: state.settlingUnload.filter((f) => f !== filename),
			pinnedUnload:
				action === 'unload'
					? uniqueFilenames([...state.pinnedUnload, filename])
					: state.pinnedUnload.filter((f) => f !== filename),
			visualUnload:
				action === 'unload'
					? uniqueFilenames([...state.visualUnload, filename])
					: state.visualUnload.filter((f) => f !== filename),
			actions: { ...state.actions, [filename]: action }
		}));
		scheduleRealtimeRefresh();
	};
	const clearLocalModelUnloadPin = (filename: string) => {
		localModelProcessingStore.update((state) => ({
			...state,
			pinnedUnload: state.pinnedUnload.filter((f) => f !== filename)
		}));
	};
	const clearReopenedUnloadVisual = (filename: string) => {
		if (!reopenedUnloadVisualModels.has(filename)) return;
		const nextModels = new Set(reopenedUnloadVisualModels);
		nextModels.delete(filename);
		reopenedUnloadVisualModels = nextModels;
	};
	const guardReopenedUnloadVisuals = () => {
		const filenames = Object.entries(getStoreValue(localModelProcessingStore).actions)
			.filter(([, action]) => action === 'unload')
			.map(([filename]) => filename);

		if (filenames.length === 0) return;

		reopenedUnloadVisualModels = new Set([...reopenedUnloadVisualModels, ...filenames]);
		localModelProcessingStore.update((state) => ({
			...state,
			pinnedUnload: uniqueFilenames([...state.pinnedUnload, ...filenames]),
			visualUnload: uniqueFilenames([...state.visualUnload, ...filenames])
		}));
	};
	const clearLocalModelProcessing = (filename: string, preserveVisualUnload = false) => {
		cancelLocalActionRefresh(filename);
		cancelLocalActionRelease(filename);
		if (!preserveVisualUnload) {
			clearReopenedUnloadVisual(filename);
		}
		localModelProcessingStore.update((state) => {
			const nextActions = { ...state.actions };
			delete nextActions[filename];
			return {
				loading: state.loading.filter((f) => f !== filename),
				settlingUnload: state.settlingUnload.filter((f) => f !== filename),
				pinnedUnload: state.pinnedUnload.filter((f) => f !== filename),
				visualUnload: preserveVisualUnload
					? state.visualUnload
					: state.visualUnload.filter((f) => f !== filename),
				actions: nextActions
			};
		});
	};
	const setLocalModelUnloadSettling = (filename: string) => {
		localModelProcessingStore.update((state) => ({
			loading: state.loading.filter((f) => f !== filename),
			settlingUnload: uniqueFilenames([...state.settlingUnload, filename]),
			pinnedUnload: uniqueFilenames([...state.pinnedUnload, filename]),
			visualUnload: uniqueFilenames([...state.visualUnload, filename]),
			actions: { ...state.actions, [filename]: 'unload' }
		}));
	};
	const isLocalModelUnloading = (filename: string) =>
		localModelActions[filename] === 'unload' || settlingUnloadModels.has(filename);
	const isLocalModelUnloadPinned = (model: LocalModel) =>
		isLocalModelUnloading(model.filename) &&
		(model.is_loaded || pinnedUnloadModels.has(model.filename));
	const isLocalActionVisuallySettled = (filename: string, action: LocalModelAction) => {
		if (action === 'load') {
			return loadedLocalModel?.filename === filename;
		}

		const model = localModels.find((localModel) => localModel.filename === filename);
		return (
			(!model || !model.is_loaded) &&
			!pinnedUnloadModels.has(filename) &&
			highlightedLoadedItem?.gguf?.filename !== filename
		);
	};
	const waitForPaint = () =>
		new Promise<void>((resolve) => {
			let settled = false;
			let fallbackTimer: ReturnType<typeof setTimeout> | null = null;
			const finish = () => {
				if (settled) return;
				settled = true;
				if (fallbackTimer) clearTimeout(fallbackTimer);
				document.removeEventListener('visibilitychange', handleVisibilityChange);
				resolve();
			};
			const handleVisibilityChange = () => {
				if (document.visibilityState !== 'visible') finish();
			};

			if (typeof requestAnimationFrame === 'function') {
				document.addEventListener('visibilitychange', handleVisibilityChange);
				requestAnimationFrame(finish);
				fallbackTimer = setTimeout(finish, 120);
			} else {
				setTimeout(finish, 0);
			}
		});
	const wait = (duration: number) => new Promise<void>((resolve) => setTimeout(resolve, duration));
	const isDocumentVisible = () =>
		typeof document === 'undefined' || document.visibilityState === 'visible';
	const releasePinnedSettledUnloadsAfterOpen = async () => {
		if (!show || destroyed) return;
		if (!isDocumentVisible()) {
			const state = getStoreValue(localModelProcessingStore);
			state.pinnedUnload.forEach((filename) => {
				if (
					state.actions[filename] === 'unload' &&
					state.settlingUnload.includes(filename) &&
					!state.loading.includes(filename)
				) {
					clearLocalModelProcessing(filename);
				}
			});
			return;
		}

		await tick();
		await waitForPaint();
		await wait(LOCAL_UNLOAD_REOPEN_PIN_MS);

		if (!show || destroyed) return;

		const state = getStoreValue(localModelProcessingStore);
		state.pinnedUnload.forEach((filename) => {
			if (
				state.actions[filename] === 'unload' &&
				state.settlingUnload.includes(filename) &&
				!state.loading.includes(filename)
			) {
				clearLocalModelUnloadPin(filename);
				scheduleLocalActionVisualRelease(filename, 'unload');
			}
		});
	};
	const pinUnsettledUnloadsBeforeClose = () => {
		const state = getStoreValue(localModelProcessingStore);
		const unsettledUnloadFilenames = Object.entries(state.actions)
			.filter(([filename, action]) => action === 'unload' && !isLocalActionVisuallySettled(filename, action))
			.map(([filename]) => filename);

		if (unsettledUnloadFilenames.length === 0) return;

		localModelProcessingStore.update((currentState) => ({
			...currentState,
			pinnedUnload: uniqueFilenames([...currentState.pinnedUnload, ...unsettledUnloadFilenames])
		}));
	};
	const scheduleLocalActionVisualRelease = (filename: string, expectedAction: LocalModelAction) => {
		if (destroyed) return;
		cancelLocalActionRelease(filename);
		const token = localActionReleaseTokens.get(filename) ?? 0;
		localActionReleasePending.add(filename);
		let release: () => Promise<void>;

		const queueReleaseCheck = (delay = 80) => {
			const timer = setTimeout(release, delay);
			localActionReleaseTimers.set(filename, timer);
		};

		release = async () => {
			if ((localActionReleaseTokens.get(filename) ?? 0) !== token) return;
			if (destroyed) return;
			const currentAction = getStoreValue(localModelProcessingStore).actions[filename];
			if (currentAction !== expectedAction) {
				localActionReleaseTimers.delete(filename);
				localActionReleasePending.delete(filename);
				return;
			}
			if (!show || !isDocumentVisible()) {
				localActionReleaseTimers.delete(filename);
				localActionReleasePending.delete(filename);
				clearLocalModelProcessing(filename);
				return;
			}
			if (expectedAction === 'unload' && getStoreValue(localModelProcessingStore).pinnedUnload.includes(filename)) {
				queueReleaseCheck();
				return;
			}
			if (!isLocalActionVisuallySettled(filename, expectedAction)) {
				queueReleaseCheck();
				return;
			}

			await tick();
			await waitForPaint();
			await waitForPaint();

			if ((localActionReleaseTokens.get(filename) ?? 0) !== token) return;
			if (destroyed) return;
			if (!show || !isDocumentVisible()) {
				localActionReleaseTimers.delete(filename);
				localActionReleasePending.delete(filename);
				clearLocalModelProcessing(filename);
				return;
			}
			if (expectedAction === 'unload' && getStoreValue(localModelProcessingStore).pinnedUnload.includes(filename)) {
				queueReleaseCheck();
				return;
			}
			if (!isLocalActionVisuallySettled(filename, expectedAction)) {
				queueReleaseCheck();
				return;
			}

			localActionReleaseTimers.delete(filename);
			localActionReleasePending.delete(filename);
			if (getStoreValue(localModelProcessingStore).actions[filename] === expectedAction) {
				clearLocalModelProcessing(filename, expectedAction === 'unload');
				if (expectedAction === 'unload') {
					scheduleVisualUnloadClear(filename);
				}
			}
		};

		const timer = setTimeout(() => {
			if ((localActionReleaseTokens.get(filename) ?? 0) !== token) return;
			if (destroyed) return;
			void release();
		}, 0);
		localActionReleaseTimers.set(filename, timer);
	};
	const clearSettledLocalModelActions = (refreshedLocalModels: LocalModel[]) => {
		const processingState = getStoreValue(localModelProcessingStore);
		const { actions } = processingState;
		Object.entries(actions).forEach(([filename, action]) => {
			const refreshedModel = refreshedLocalModels.find((model) => model.filename === filename);
			if (action === 'load' && refreshedModel?.is_loaded) {
				if (show) {
					scheduleLocalActionVisualRelease(filename, action);
				} else {
					clearLocalModelProcessing(filename);
				}
			}
			if (action === 'unload' && (!refreshedModel || !refreshedModel.is_loaded)) {
				const requestFinished =
					processingState.settlingUnload.includes(filename) &&
					!processingState.loading.includes(filename);
				if (requestFinished && (!show || !isDocumentVisible())) {
					clearLocalModelProcessing(filename);
				} else if (show && processingState.pinnedUnload.includes(filename)) {
					void releasePinnedSettledUnloadsAfterOpen();
				} else if (requestFinished) {
					scheduleLocalActionVisualRelease(filename, action);
				}
			}
		});
	};
	const scheduleLocalActionRefresh = (filename: string, attempts = 120) => {
		if (destroyed) return;
		const { actions } = getStoreValue(localModelProcessingStore);
		if (
			attempts <= 0 ||
			!actions[filename] ||
			localActionRefreshTimers.has(filename)
		) return;
		const timer = setTimeout(async () => {
			localActionRefreshTimers.delete(filename);
			if (destroyed) return;
			if (!getStoreValue(localModelProcessingStore).actions[filename]) return;
			await refreshUnifiedModelData(false);
			if (getStoreValue(localModelProcessingStore).actions[filename]) {
				scheduleLocalActionRefresh(filename, attempts - 1);
			}
		}, 700);
		localActionRefreshTimers.set(filename, timer);
	};
	const refreshUntilLocalActionSettles = async (filename: string) => {
		if (destroyed) return;
		await refreshUnifiedModelData(false);
		if (getStoreValue(localModelProcessingStore).actions[filename]) {
			scheduleLocalActionRefresh(filename);
		}
	};
	const refreshLocalActionsAfterOpen = async () => {
		if (openingActionRefreshInProgress || destroyed) return;
		openingActionRefreshInProgress = true;
		cancelOrphanedLocalActionTimers();

		try {
			const { actions } = getStoreValue(localModelProcessingStore);
			if (Object.keys(actions).length === 0) return;

			Object.keys(actions).forEach((filename) => {
				cancelLocalActionRefresh(filename);
				cancelLocalActionRelease(filename);
			});

			await refreshUnifiedModelData(false);
			await releasePinnedSettledUnloadsAfterOpen();

			const latestActions = getStoreValue(localModelProcessingStore).actions;
			Object.keys(latestActions).forEach((filename) => {
				if (!localActionReleasePending.has(filename)) {
					scheduleLocalActionRefresh(filename, 120);
				}
			});
		} finally {
			openingActionRefreshInProgress = false;
		}
	};
	const getSpeculativeChipLabel = (speculativeDecoding?: string | null) => {
		if (speculativeDecoding === 'low') return 'Baixo';
		if (speculativeDecoding === 'high') return 'Alto';
		return 'Desligado';
	};

	const getTokenPredictionChipLabel = (tokenPrediction?: string | null) => {
		if (
			tokenPrediction === 'on' ||
			tokenPrediction === 'stable' ||
			tokenPrediction === 'aggressive'
		)
			return 'Ligado';
		return 'Desligado';
	};
	const isTokenPredictionActive = (tokenPrediction?: string | null) =>
		tokenPrediction === 'on' || tokenPrediction === 'stable' || tokenPrediction === 'aggressive';
	const isContextShiftActive = (contextShift?: string | null) => contextShift === 'on';
	const isSpeculativeDecodingActive = (speculativeDecoding?: string | null) =>
		speculativeDecoding === 'low' || speculativeDecoding === 'high';
	const getModelImageVersion = (model: any) =>
		model?.updated_at ?? model?.info?.updated_at ?? model?.meta?.updated_at ?? '';
	const getModelProfileImageUrl = (model: any) => {
		const params = new URLSearchParams({ id: model?.id ?? '' });
		const version = getModelImageVersion(model);
		if (version) params.set('v', `${version}`);
		return `${NEVEAI_API_BASE_URL}/models/model/profile/image?${params.toString()}`;
	};
	const matchesModelSearch = (item: any, query: string) => {
		const q = query.trim().toLowerCase();
		if (!q) return true;
		const gm = item.gguf;
		const am = item.admin;
		return Boolean(
			gm?.filename?.toLowerCase().includes(q) ||
			gm?.id?.toLowerCase().includes(q) ||
			am?.name?.toLowerCase().includes(q) ||
			am?.id?.toLowerCase().includes(q)
		);
	};
	const applyPreload = (data: UnifiedModelsPreload) => {
		const snapshotAt = data.runtimeUpdatedAt ?? 0;
		if (!preloadApplied || snapshotAt > localModelsSnapshotAt) {
			localModels = data.localModels ?? [];
			localModelsSnapshotAt = snapshotAt;
			const runtimeEvent = getLatestLocalModelRuntimeEvent();
			if (runtimeEvent?.phase === 'success' && runtimeEvent.timestamp > snapshotAt) {
				if (runtimeEvent.action === 'load') {
					const loaded = localModels.find((model) => model.filename === runtimeEvent.filename || model.id === runtimeEvent.modelId);
					if (loaded) markLocalModelLoaded(loaded, runtimeEvent.result);
				} else {
					markLocalModelUnloaded(runtimeEvent.filename ?? '', runtimeEvent.modelId);
				}
				localModelsSnapshotAt = runtimeEvent.timestamp;
			}
		}
		mmProjFiles = data.mmProjFiles ?? [];
		if (catalogSnapshotAt === 0 || (data.catalogUpdatedAt ?? 0) > catalogSnapshotAt) {
			adminModels = data.adminModels ?? [];
			workspaceModels = data.workspaceModels ?? [];
			baseModels = data.baseModels ?? [];
			catalogSnapshotAt = data.catalogUpdatedAt ?? 0;
		}
		vramInfo = data.vramInfo ?? null;
		localLoading = false;
	};

	$: if (preload?.loaded && preload !== appliedPreload && (!preloadApplied || (!show && !localModelActionInProgress))) {
		applyPreload(preload);
		appliedPreload = preload;
		preloadApplied = true;
	}
	$: if (preload?.vramInfo) {
		const nextPreloadVramSignature = JSON.stringify(preload.vramInfo);
		if (nextPreloadVramSignature !== preloadVramSignature) {
			vramInfo = preload.vramInfo;
			preloadVramSignature = nextPreloadVramSignature;
		}
	}

	// ─── COMPUTED ────────────────────────────────────────────────────────────
	// Merged single list: GGUFs first (loaded then unloaded), then admin-only models
	// Loaded GGUFs appear ONCE with both load controls and admin controls
	$: mergedModels = (() => {
		const adminById = new Map((adminModels ?? []).map((m: any) => [m.id, m]));
		const ggufIds = new Set(localModels.map((gm) => gm.id).filter(Boolean));

		const ggufItems = visibleLocalModels
			.map((gm) => ({ key: `gguf:${gm.id ?? gm.filename}`, gguf: gm, admin: adminById.get(gm.id) ?? null }));

		// Sort GGUFs: loaded/unloading first, then unloaded. Loading stays in place.
		ggufItems.sort((a, b) => {
			const aPriority =
				a.gguf?.is_loaded || isLocalModelUnloadPinned(a.gguf)
					? 1
					: 0;
			const bPriority =
				b.gguf?.is_loaded || isLocalModelUnloadPinned(b.gguf)
					? 1
					: 0;
			return bPriority - aPriority;
		});

		const adminOnlyItems = (adminModels ?? [])
			.filter((am: any) => !ggufIds.has(am.id))
			.sort((a: any, b: any) => (a?.name ?? a?.id ?? '').localeCompare(b?.name ?? b?.id ?? ''))
			.map((am: any) => ({ key: `admin:${am.id}`, gguf: null, admin: am }));

		return [...ggufItems, ...adminOnlyItems];
	})();

	$: {
		const openingModal = show && !previousShow;
		const closingModal = !show && previousShow;
		previousShow = show;
		if (openingModal) {
			showDownloadModal = false;
			void refreshModelAvailability();
			selectedModelId = null;
			guardReopenedUnloadVisuals();
			void refreshUnifiedModelData(false);
			void refreshLocalActionsAfterOpen();
			scheduleRealtimeRefresh();
		} else if (closingModal) {
			showDownloadModal = false;
			pinUnsettledUnloadsBeforeClose();
			selectedModelId = null;
			scheduleRealtimeRefresh();
		}
	}
	$: highlightedLoadedItem =
		mergedModels.find(
			(item) =>
				item.gguf?.is_loaded ||
				(!modelsBlocked && item.gguf && isLocalModelUnloadPinned(item.gguf))
		) ?? null;
	$: if (reopenedUnloadVisualModels.size > 0) {
		const highlightedFilename = highlightedLoadedItem?.gguf?.filename ?? null;
		const nextModels = new Set(
			[...reopenedUnloadVisualModels].filter(
				(filename) =>
					filename === highlightedFilename ||
					localModelActions[filename] === 'unload' ||
					pinnedUnloadModels.has(filename)
			)
		);
		if (nextModels.size !== reopenedUnloadVisualModels.size) {
			reopenedUnloadVisualModels = nextModels;
		}
	}
	$: modelEmptyTitle = localAccessError
		? $i18n.t('Could not access local models')
		: llamacppStatus && !llamacppStatus.server_binary_exists
			? $i18n.t('llama.cpp not found')
			: searchValue
				? $i18n.t('No models found')
				: $i18n.t('No models installed');
	$: modelEmptyDescription = localAccessError
		? $i18n.t('Check that the backend is running and reopen this window.')
		: llamacppStatus && !llamacppStatus.server_binary_exists
			? $i18n.t('Run the installer to download llama.cpp before loading local models.')
			: searchValue
				? $i18n.t('Adjust your search to find the model you are looking for.')
				: $i18n.t('Click "Download models" to install one, or place .gguf files in the models folder.');
	let modelLayout: 'grid' | 'list' = 'grid';
	let modelSort: 'name' | 'size' = 'name';
	let sortMenuOpen = false;
	let modelList: HTMLElement;
	function spaceForScrollbar(node: HTMLElement, _layout: [number, string, boolean]) {
		const sync = () => node.classList.toggle('pr-2', node.scrollHeight > node.clientHeight);
		const resize = new ResizeObserver(sync);
		resize.observe(node);
		return { update: () => { void tick().then(sync); }, destroy: () => resize.disconnect() };
	}
	const nameOrder = new Intl.Collator(undefined, { numeric: true, sensitivity: 'base' });
	const rowName = (item) => item.admin?.name ?? item.gguf?.filename?.replace(/\.gguf$/i, '') ?? item.admin?.id ?? '';
	$: gridModels = localAccessError ? [] : mergedModels.filter(item => matchesModelSearch(item, searchValue))
		.sort((a, b) => (modelSort === 'size' ? (b.gguf?.file_size ?? -1) - (a.gguf?.file_size ?? -1) : 0)
			|| nameOrder.compare(rowName(a), rowName(b)) || nameOrder.compare(a.key, b.key));
	async function setLayout(next: typeof modelLayout) {
		if (next === modelLayout) return;
		const list = modelList, top = list.getBoundingClientRect().top;
		const anchor = list.scrollTop > 0 && Array.from(list.querySelectorAll<HTMLElement>('[data-model-key]'))
			.find(row => row.getBoundingClientRect().bottom > top);
		const offset = anchor ? anchor.getBoundingClientRect().top - top : 0;
		modelLayout = next;
		localStorage.setItem('neveai.models.layout', next);
		await tick();
		if (anchor && list.contains(anchor)) list.scrollTop += anchor.getBoundingClientRect().top - list.getBoundingClientRect().top - offset;
	}
	async function setOrder(next: typeof modelSort) {
		sortMenuOpen = false;
		if (modelSort === next) return;
		modelSort = next;
		localStorage.setItem('neveai.models.order', next);
		await tick();
		if (modelList) modelList.scrollTop = 0;
	}
	const catalogControl = 'grid size-7 place-items-center rounded-md text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800';


	// ─── LOCAL MODEL FUNCTIONS ───────────────────────────────────────────────
	async function refreshLocalVram() {
		try {
			vramInfo = await getLocalVramInfo(localStorage.token);
		} catch (e: any) {
			vramInfo = {
				available: false,
				source: 'nvidia-smi',
				total: 0,
				used: 0,
				free: 0,
				total_human: '0 B',
				used_human: '0 B',
				free_human: '0 B',
				gpus: [],
				error: normalizeLlamaCppErrorMessage(e, 'Falha ao buscar VRAM')
			};
		}
	}

	async function refreshGlobalModelsStore(useDirectConnections = false) {
		const revision = catalogRevision;
		try {
			const result = await getModels(localStorage.token, useDirectConnections ? $config?.features?.enable_direct_connections && ($settings?.directConnections ?? null) : undefined);
			if (revision === catalogRevision) _models.set(result);
		} catch {
			// Best effort: a post-action refresh should not look like the action failed.
		}
	}

	const isSameLocalModel = (localModel: LocalModel, model: LocalModel) =>
		localModel.id === model.id || localModel.filename === model.filename;
	const localModelDisplayName = (model: LocalModel) =>
		(adminModels ?? []).find((entry: any) =>
			entry.id === model.id ||
			entry.id === `local/${model.filename}` ||
			entry.info?.meta?.filename === model.filename
		)?.name ??
		($_models ?? []).find((entry: any) =>
			entry.id === model.id ||
			entry.id === `local/${model.filename}` ||
			entry.info?.meta?.filename === model.filename
		)?.name ??
		model.filename.replace(/\.gguf$/i, '');

	const markLocalModelLoaded = (model: LocalModel, result: any, mmprojFilename: string | null = null) => {
		localModels = localModels.map((localModel) =>
			isSameLocalModel(localModel, model)
				? {
						...localModel,
						is_loaded: true,
						loaded_at: Date.now(),
						n_gpu_layers: result?.n_gpu_layers ?? gpuLayers,
						n_ctx: result?.n_ctx ?? contextSize,
						context_auto: result?.context_auto ?? false,
						mmproj_filename: result?.mmproj_filename ?? mmprojFilename,
						cache_type: result?.cache_type ?? getCacheTypeForLoad(),
						speculative_decoding:
							result?.speculative_decoding ?? getSpeculativeDecodingForLoad(),
						token_prediction: result?.token_prediction ?? getTokenPredictionForLoad(),
						context_shift: result?.context_shift ?? getContextShiftForLoad(),
						prioritize_gpu: result?.prioritize_gpu ?? getLocalModelLoadPreferences().prioritizeGpu
					}
				: {
						...localModel,
						is_loaded: false,
						loaded_at: null,
						n_gpu_layers: null,
						n_ctx: null,
						mmproj_filename: null,
						cache_type: null,
						speculative_decoding: null,
						token_prediction: null,
						context_shift: null,
						prioritize_gpu: false
					}
		);
	};

	const markLocalModelUnloaded = (filename: string, modelId?: string) => {
		localModels = localModels.map((localModel) =>
			localModel.filename === filename || (modelId && localModel.id === modelId)
				? {
						...localModel,
						is_loaded: false,
						loaded_at: null,
						n_gpu_layers: null,
						n_ctx: null,
						mmproj_filename: null,
						cache_type: null,
						speculative_decoding: null,
						token_prediction: null,
						context_shift: null,
						prioritize_gpu: false
					}
				: localModel
		);
	};

	const synchronizeExternalLocalModelRuntime = async (
		detail: LocalModelRuntimeEventDetail
	) => {
		let filename =
			detail.filename ??
			detail.result?.filename ??
			localModels.find((model) => model.id === (detail.modelId ?? detail.result?.id))?.filename;

		if (!filename) {
			const refreshedModels = await refreshUnifiedModelData(false);
			filename = refreshedModels?.find(
				(model) => model.id === (detail.modelId ?? detail.result?.id)
			)?.filename;
		}
		if (!filename || destroyed) return;

		if (!getStoreValue(localModelProcessingStore).actions[filename]) {
			setLocalModelAction(filename, detail.action);
		}

		if (detail.phase === 'success') {
			manualRuntimeUpdatedAt = detail.timestamp;
			let runtimeStatePatched = false;
			if (detail.action === 'load') {
				const model = localModels.find(
					(localModel) =>
						localModel.filename === filename ||
						localModel.id === (detail.modelId ?? detail.result?.id)
				);
				if (model) {
					markLocalModelLoaded(model, detail.result);
					runtimeStatePatched = true;
				}
			} else {
				setLocalModelUnloadSettling(filename);
				markLocalModelUnloaded(filename, detail.modelId ?? detail.result?.id);
				runtimeStatePatched = true;
			}

			if (!show && runtimeStatePatched) clearLocalModelProcessing(filename);
			await refreshUnifiedModelData(false);
			void refreshGlobalModelsStore();
			return;
		}

		const refreshedModels = await refreshUnifiedModelData(false);
		if (!refreshedModels) return;
		const refreshedModel = refreshedModels.find(
			(model) => model.filename === filename || model.id === detail.modelId
		);
		const actionStillTracked =
			getStoreValue(localModelProcessingStore).actions[filename] === detail.action;
		const actionDidNotComplete =
			detail.action === 'load'
				? !refreshedModel?.is_loaded
				: Boolean(refreshedModel?.is_loaded);
		if (actionStillTracked && actionDidNotComplete) {
			clearLocalModelProcessing(filename);
		}
	};

	const handleLocalModelRuntimeEvent = (detail: LocalModelRuntimeEventDetail | null) => {
		if (!detail || destroyed) return;
		localModelsSnapshotAt = Math.max(localModelsSnapshotAt, detail.timestamp);
		const filename =
			detail.filename ??
			detail.result?.filename ??
			localModels.find((model) => model.id === (detail.modelId ?? detail.result?.id))?.filename;

		if (detail.phase === 'start') {
			if (!filename) return;
			const currentAction = getStoreValue(localModelProcessingStore).actions[filename];
			if (currentAction === detail.action) {
				ignoredRuntimeOperationIds.add(detail.operationId);
				return;
			}
			setLocalModelAction(filename, detail.action);
			return;
		}

		if (ignoredRuntimeOperationIds.delete(detail.operationId)) return;
		void synchronizeExternalLocalModelRuntime(detail);
	};

	const reconcileLocalActionAfterError = async (
		model: LocalModel,
		action: LocalModelAction
	): Promise<boolean> => {
		const refreshedModels = await refreshUnifiedModelData(false);
		if (!refreshedModels) return false;

		const refreshedModel = refreshedModels.find((entry) => isSameLocalModel(entry, model));
		if (action === 'load' && refreshedModel?.is_loaded) {
			localError = '';
			localSuccess = `${model.filename} carregado com sucesso!`;
			void refreshGlobalModelsStore();
			return true;
		}

		if (action === 'unload' && (!refreshedModel || !refreshedModel.is_loaded)) {
			localError = '';
			localSuccess = `${model.filename} descarregado.`;
			setLocalModelUnloadSettling(model.filename);
			clearSettledLocalModelActions(refreshedModels);
			void refreshGlobalModelsStore();
			return true;
		}

		return false;
	};

	async function handleLoad(model: LocalModel) {
		if (localModelActionInProgress) return;
		setLocalModelAction(model.filename, 'load');
		localError = '';
		localSuccess = '';
		let completed = false;
		try {
			const result = await loadLocalModel(
				localStorage.token,
				model.filename,
				gpuLayers,
				contextSize,
				'',
				getCacheTypeForLoad(),
				getSpeculativeDecodingForLoad(),
				getTokenPredictionForLoad(),
				getContextShiftForLoad(),
				localModelDisplayName(model),
				getLocalModelLoadPreferences().prioritizeGpu
			);
			markLocalModelLoaded(model, result);
			localSuccess = `${model.filename} carregado com sucesso!`;
			completed = true;
			await refreshUntilLocalActionSettles(model.filename);
			void refreshGlobalModelsStore();
		} catch (e: any) {
			completed = await reconcileLocalActionAfterError(model, 'load');
			if (!completed) {
				localError = normalizeLlamaCppErrorMessage(e, 'Erro ao carregar modelo');
			}
		} finally {
			if (!completed) {
				clearLocalModelProcessing(model.filename);
			}
		}
	}

	async function startLoadWithPreferences(model: LocalModel) {
		if (localModelActionInProgress || enablingModel) return;
		const saved = adminModels.find(entry => entry.id === model.id);
		if (saved?.is_active === false) {
			enablingModel = true;
			try {
				if (!await upsertModelHandler({ ...saved, is_active: true }, false)) return;
			} finally {
				enablingModel = false;
			}
			if (localModelActionInProgress) return;
		}
		const preferences = getLocalModelLoadPreferences();
		contextSize = preferences.context === 'auto' ? 0 : preferences.context;
		loadWithVisionPreference(model);
	}

	function loadWithVisionPreference(model: LocalModel) {
		const preferences = getLocalModelLoadPreferences();
		const matchingMmproj = findMatchingMmproj(model.filename, mmProjFiles);

		if (matchingMmproj && preferences.vision === 'yes') {
			handleLoadWithMmproj(model, matchingMmproj);
		} else {
			handleLoad(model);
		}
	}

	async function handleLoadWithMmproj(model: LocalModel, mmprojFile: string) {
		if (localModelActionInProgress) return;
		setLocalModelAction(model.filename, 'load');
		localError = '';
		localSuccess = '';
		let completed = false;
		try {
			const result = await loadLocalModel(
				localStorage.token,
				model.filename,
				gpuLayers,
				contextSize,
				mmprojFile,
				getCacheTypeForLoad(),
				getSpeculativeDecodingForLoad(),
				getTokenPredictionForLoad(),
				getContextShiftForLoad(),
				localModelDisplayName(model),
				getLocalModelLoadPreferences().prioritizeGpu
			);
			markLocalModelLoaded(model, result, mmprojFile);
			localSuccess = $i18n.t('{{name}} loaded! (vision: {{file}})', {
				name: model.filename,
				file: mmprojFile
			});
			completed = true;
			await refreshUntilLocalActionSettles(model.filename);
			void refreshGlobalModelsStore();
		} catch (e: any) {
			completed = await reconcileLocalActionAfterError(model, 'load');
			if (!completed) {
				localError = normalizeLlamaCppErrorMessage(e, 'Erro ao carregar modelo');
			}
		} finally {
			if (!completed) {
				clearLocalModelProcessing(model.filename);
			}
		}
	}

	async function handleUnload(model: LocalModel) {
		setLocalModelAction(model.filename, 'unload');
		localError = '';
		localSuccess = '';
		let completed = false;
		try {
			await unloadLocalModel(localStorage.token, model.id, localModelDisplayName(model));
			localSuccess = `${model.filename} descarregado.`;
			markLocalModelUnloaded(model.filename, model.id);
			setLocalModelUnloadSettling(model.filename);
			if (!show) clearLocalModelProcessing(model.filename);
			completed = true;
			await refreshUntilLocalActionSettles(model.filename);
			void refreshGlobalModelsStore();
		} catch (e: any) {
			completed = await reconcileLocalActionAfterError(model, 'unload');
			if (!completed) {
				localError = normalizeLlamaCppErrorMessage(e, 'Erro ao descarregar modelo');
			}
		} finally {
			if (!completed) {
				clearLocalModelProcessing(model.filename);
			}
		}
	}

	// ─── ADMIN MODEL FUNCTIONS ───────────────────────────────────────────────
	const initAdmin = async (localModelSource: LocalModel[] = localModels) => {
		const revision = catalogRevision;
		const startedAt = Date.now();
		try {
			const nextBaseModels = [...$_models];
			const res = await getBaseModels(localStorage.token);
			if (destroyed || revision !== catalogRevision || startedAt < catalogSnapshotAt) return false;
			baseModels = nextBaseModels;
			workspaceModels = Array.isArray(res) ? res : [];
			adminModels = buildUnifiedAdminModels(localModelSource, baseModels, workspaceModels);
			publishCatalog(startedAt, false);
			return true;
		} catch (e) {
			console.error('[UnifiedModels] initAdmin error:', e);
			lastAdminRefreshAt = Date.now();
			if (adminModels.length === 0) adminModels = baseModels ?? [];
			return false;
		}
	};

	async function performUnifiedModelRefresh(initial: boolean): Promise<LocalModel[] | null> {
		void refreshModelAvailability();
		const runtimeUpdatedAt = Date.now();
		if (initial) localLoading = true;
		try {
			const [newLocalModels, newMmProjFiles, newLlamaCppStatus] = await Promise.all([
				getLocalModels(localStorage.token),
				getMmProjFiles(localStorage.token),
				getLlamaCppStatus(localStorage.token).catch(() => null)
			]);
			if (destroyed) return null;
			const localCatalogChanged =
				getLocalModelsCatalogSignature(newLocalModels) !==
				getLocalModelsCatalogSignature(localModels);
			if (initial || localCatalogChanged || Date.now() - lastAdminRefreshAt >= 3000) {
				if (await initAdmin(newLocalModels)) lastAdminRefreshAt = Date.now();
			}
			if (destroyed) return null;
			localError = '';
			if (JSON.stringify(newLocalModels) !== JSON.stringify(localModels)) localModels = newLocalModels;
			localModelsSnapshotAt = Math.max(localModelsSnapshotAt, runtimeUpdatedAt);
			if (JSON.stringify(newMmProjFiles) !== JSON.stringify(mmProjFiles)) mmProjFiles = newMmProjFiles;
			llamacppStatus = newLlamaCppStatus;
			clearSettledLocalModelActions(newLocalModels);
			return newLocalModels;
		} catch (e: any) {
			if (!localModelActionInProgress) {
				localError = normalizeLlamaCppErrorMessage(e, 'Falha ao atualizar');
			}
			return null;
		} finally {
			if (!destroyed) await refreshLocalVram();
			localLoading = false;
		}
	}

	async function refreshUnifiedModelData(initial = true): Promise<LocalModel[] | null> {
		if (unifiedRefreshInFlight) {
			unifiedRefreshRequested = true;
			unifiedRefreshRequestedInitial = unifiedRefreshRequestedInitial || initial;
			return unifiedRefreshInFlight;
		}

		const refreshPromise = performUnifiedModelRefresh(initial);
		unifiedRefreshInFlight = refreshPromise;
		let result: LocalModel[] | null = null;
		try {
			result = await refreshPromise;
		} finally {
			if (unifiedRefreshInFlight === refreshPromise) {
				unifiedRefreshInFlight = null;
			}
		}

		if (unifiedRefreshRequested && !destroyed) {
			const followUpInitial = unifiedRefreshRequestedInitial;
			unifiedRefreshRequested = false;
			unifiedRefreshRequestedInitial = false;
			return refreshUnifiedModelData(followUpInitial);
		}

		return result;
	}

	const getLocalModelsRuntimeSignature = (models: LocalModel[]) =>
		JSON.stringify(
			models.map((model) => ({
				id: model.id,
				filename: model.filename,
				is_loaded: model.is_loaded,
				loaded_at: model.loaded_at,
				n_gpu_layers: model.n_gpu_layers,
				n_ctx: model.n_ctx,
				mmproj_filename: model.mmproj_filename,
				cache_type: model.cache_type,
				speculative_decoding: model.speculative_decoding,
				token_prediction: model.token_prediction,
				context_shift: model.context_shift,
				prioritize_gpu: model.prioritize_gpu
			}))
		);
	const getLocalModelsCatalogSignature = (models: LocalModel[]) =>
		JSON.stringify(
			models.map((model) => ({
				id: model.id,
				filename: model.filename,
				file_size: model.file_size
			}))
		);

	const scheduleRealtimeRefresh = () => {
		if (destroyed) return;
		if (realtimeRefreshTimer) clearTimeout(realtimeRefreshTimer);

		const hasActiveAction = Object.keys(getStoreValue(localModelProcessingStore).actions).length > 0;
		if (!show && !hasActiveAction) {
			realtimeRefreshTimer = null;
			return;
		}
		const delay = hasActiveAction ? 700 : 1000;
		realtimeRefreshTimer = setTimeout(async () => {
			realtimeRefreshTimer = null;
			if (destroyed) return;

			const previousSignature = getLocalModelsRuntimeSignature(localModels);
			const refreshedModels = await refreshUnifiedModelData(false);
			if (
				refreshedModels &&
				getLocalModelsRuntimeSignature(refreshedModels) !== previousSignature
			) {
				await refreshGlobalModelsStore();
			}
			scheduleRealtimeRefresh();
		}, delay);
	};

	const refreshAfterCatalogChange = async () => {
		await refreshUnifiedModelData(false);
		await refreshGlobalModelsStore();
	};

	const upsertModelHandler = async (model: any, showToast = true) => {
		catalogRevision++;
		publishCatalog();
		let saved: any;
		if ((workspaceModels ?? []).find((m) => m.id === model.id)) {
			saved = await updateModelById(localStorage.token, model.id, model).catch(() => null);
		} else {
			saved = await createNewModel(localStorage.token, {
				meta: {},
				id: model.id,
				name: model.name,
				base_model_id: null,
				params: {},
				access_grants: [],
				...model
			}).catch(() => null);
		}
		catalogRevision++;
		if (!saved) { toast.error($i18n.t('Failed to save model')); return; }
		workspaceModels = [...(workspaceModels ?? []).filter((entry) => entry.id !== model.id), { ...model, ...saved }];
		adminModels = adminModels.map((entry) => entry.id === model.id ? { ...entry, ...model, ...saved } : entry);
		publishCatalog();
		if (showToast) toast.success($i18n.t('Model updated successfully'));
		await refreshGlobalModelsStore(true);
		if (showToast) {
			await initAdmin();
		}
		return saved;
	};

	const confirmModelDeletion = async () => {
		if (!modelToDelete || deletingModel || localModelActionInProgress) return;
		const target = modelToDelete;
		deletingModel = true;
		catalogRevision++;
		try {
			if (target.gguf) await deleteLocalModel(localStorage.token, target.gguf.filename);
			else if (target.admin) await deleteModelById(localStorage.token, target.admin.id);
			catalogRevision++;
			const id = target.gguf?.id ?? target.admin?.id;
			adminModels = adminModels.filter(model => model.id !== id);
			workspaceModels = workspaceModels.filter(model => model.id !== id);
			baseModels = baseModels.filter(model => model.id !== id);
			localModels = localModels.filter(model => model.id !== id);
			publishCatalog();
			await refreshAfterCatalogChange();
		} catch (error) {
			toast.error(normalizeLlamaCppErrorMessage(error, 'Falha ao excluir modelo'));
		} finally {
			deletingModel = false;
			modelToDelete = null;
		}
	};




	const favoriteModelHandler = (modelId: string) => toggleModelFavorite(modelId)
		.catch(() => toast.error($i18n.t('Failed to save favorites')));

	onMount(() => {
		modelLayout = localStorage.getItem('neveai.models.layout') === 'list' ? 'list' : 'grid';
		modelSort = localStorage.getItem('neveai.models.order') === 'size' ? 'size' : 'name';
		destroyed = false;
		cancelOrphanedLocalActionTimers();
		const runtimeEventHandler = (event: Event) => {
			handleLocalModelRuntimeEvent(
				(event as CustomEvent<LocalModelRuntimeEventDetail>).detail
			);
		};
		window.addEventListener(LOCAL_MODEL_RUNTIME_EVENT, runtimeEventHandler);

		const latestRuntimeEvent = getLatestLocalModelRuntimeEvent();
		if (
			latestRuntimeEvent &&
			Date.now() - latestRuntimeEvent.timestamp <= 30_000
		) {
			handleLocalModelRuntimeEvent(latestRuntimeEvent);
		}

		if (show || Object.keys(getStoreValue(localModelProcessingStore).actions).length > 0) {
			void (async () => {
				await refreshUnifiedModelData(!preloadApplied);
				await refreshLocalActionsAfterOpen();
				scheduleRealtimeRefresh();
			})();
		}

		const refreshOnFocus = () => {
			if (destroyed) return;
			const hasActiveAction = Object.keys(getStoreValue(localModelProcessingStore).actions).length > 0;
			if (show || hasActiveAction) void refreshUnifiedModelData(false);
			scheduleRealtimeRefresh();
		};
		const refreshOnVisibility = () => {
			if (document.visibilityState === 'visible') refreshOnFocus();
		};
		window.addEventListener('focus', refreshOnFocus);
		document.addEventListener('visibilitychange', refreshOnVisibility);

		void (async () => {
			const id = $page.url.searchParams.get('id') || $showSettingsModelId;
			if (id) {
				selectedModelId = id;
				showSettingsModelId.set('');
			}
		})();

		return () => {
			if (realtimeRefreshTimer) {
				clearTimeout(realtimeRefreshTimer);
				realtimeRefreshTimer = null;
			}
			window.removeEventListener('focus', refreshOnFocus);
			window.removeEventListener(LOCAL_MODEL_RUNTIME_EVENT, runtimeEventHandler);
			document.removeEventListener('visibilitychange', refreshOnVisibility);
		};
	});

	onDestroy(() => {
		destroyed = true;
		unifiedRefreshRequested = false;
		unifiedRefreshRequestedInitial = false;
		if (realtimeRefreshTimer) {
			clearTimeout(realtimeRefreshTimer);
			realtimeRefreshTimer = null;
		}
		cancelAllLocalActionTimers();
		ignoredRuntimeOperationIds.clear();
		unsubscribeLocalModelProcessing();
	});

	export const handleOutsideClick = () => {
		if (showDownloadModal) {
			if (!downloadHub?.closeRepository()) showDownloadModal = false;
			return true;
		}
		if (!selectedModelId) return false;
		selectedModelId = null;
		void initAdmin();
		return true;
	};
</script>

<div class="unified-download-view h-[min(640px,90dvh)] min-h-0" class:hidden={!showDownloadModal}>
	<DownloadNeveModelsModal bind:this={downloadHub} embedded {localModels} show={show && showDownloadModal} onBack={() => { showDownloadModal = false; }} on:modelsChanged={refreshAfterCatalogChange} />
</div>

<ConfirmDialog bind:show={showDeleteModel} animated={false} title={$i18n.t('Delete model?')}
	confirmLabel={$i18n.t('Delete')} onConfirm={confirmModelDeletion}>
	<div class="text-sm text-gray-500">{$i18n.t('This will delete')} <span class="font-semibold">{modelToDelete?.admin?.name ?? modelToDelete?.gguf?.filename}</span>. {$i18n.t('The model files will be permanently removed.')}</div>
</ConfirmDialog>

{#snippet searchBar()}
	<div inert={modelsBlocked} class="search-surface flex shrink-0 items-center w-full px-2.5 {modelsBlocked ? 'opacity-50 grayscale' : ''}">
		<div class="flex min-w-0 flex-1 items-center">
			<div class="self-center ml-1 mr-3">
				<Search className="size-3.5" />
			</div>
			<input
				class="min-w-0 w-full text-sm py-1.5 rounded-r-xl outline-hidden bg-transparent"
				bind:value={searchValue}
				placeholder={$i18n.t('Search models')}
			/>
		</div>
	</div>
{/snippet}

{#snippet vramMeter()}
	<div data-vram-meter class="min-w-0 shrink-0">
		{#if vramInfo === null}
			<div class="px-0 py-2 text-xs text-gray-500 dark:text-gray-400">
				<div class="flex items-center justify-between gap-3">
					<span class="font-medium text-gray-700 dark:text-gray-200">VRAM</span>
					<span>{$i18n.t('Detectando...')}</span>
				</div>
				<div class="mt-2 h-2 rounded-full bg-gray-100 dark:bg-gray-800 overflow-hidden">
					<div class="h-full w-1/4 rounded-full bg-gray-300 dark:bg-gray-700 animate-pulse"></div>
				</div>
			</div>
		{:else if vramInfo.available}
			<div class="px-0 py-2 text-xs text-gray-500 dark:text-gray-400">
				<div class="flex items-center gap-2">
					<div class="flex min-w-0 items-center gap-2">
						<span class="font-medium text-gray-700 dark:text-gray-200">VRAM</span>
					</div>
				</div>

				<div class="relative mt-2 h-2 overflow-hidden rounded-full bg-gray-100 dark:bg-gray-800">
					{#if vramSystemSegmentBytes > 0}
						<div class="absolute inset-y-0 rounded-full" style={getSystemVramBarStyle(0, vramSystemSegmentPercent)}></div>
					{/if}
					{#if vramModelSegmentBytes > 0}
						<div class="absolute inset-y-0 rounded-full" style={getModelVramBarStyle(vramModelSegmentStartPercent, vramModelSegmentWidthPercent, vramModelSegmentHasRamFallback, vramModelSegmentBytes, vramInfo.total)}></div>
					{/if}
				</div>

				<div class="mt-1.5 flex flex-wrap items-center justify-between gap-x-3 gap-y-1">
					<span class="min-w-0">
						{$i18n.t('Uso:')} {formatBytes(vramDisplayedUsedBytes)} / {formatBytes(vramInfo.total)}
					</span>
					{#if vramPreviewModel && vramProjectedOffloadBytes > 0}
						<span class="shrink-0 text-red-600 dark:text-red-300">RAM: {formatBytes(vramProjectedOffloadBytes)}</span>
					{:else if loadedModelHasOffload}
						<span class="shrink-0 text-red-600 dark:text-red-300">RAM: {loadedLocalModel?.process_rss_bytes != null ? formatBytes(loadedLocalModel.process_rss_bytes) : '—'}</span>
					{:else}
						<span class="shrink-0">{$i18n.t('Free')}: {formatBytes(vramDisplayedFreeBytes)}</span>
					{/if}
				</div>
			</div>
		{:else}
			<div data-ram-meter class="px-0 py-2 text-xs text-gray-500 dark:text-gray-400">
				<div class="flex items-center gap-3">
					<span class="font-medium text-gray-700 dark:text-gray-200">RAM</span>
				</div>
				<div class="relative mt-2 h-2 overflow-hidden rounded-full bg-gray-100 dark:bg-gray-800">
					<div class="absolute inset-y-0 rounded-full" style={getSystemVramBarStyle(0, percentOf(vramInfo.ram?.used ?? 0, vramInfo.ram?.total ?? 0))}></div>
				</div>
				<div class="mt-1.5 flex flex-wrap items-center justify-between gap-x-3 gap-y-1">
					<span>{$i18n.t('Uso:')} {vramInfo.ram?.available ? `${formatBytes(vramInfo.ram.used)} / ${formatBytes(vramInfo.ram.total)}` : '—'}</span>
					<span>{$i18n.t('Free')}: {vramInfo.ram?.available ? formatBytes(vramInfo.ram.free) : '—'}</span>
				</div>
			</div>
		{/if}
	</div>
{/snippet}

{#snippet storageMeter()}
	<div data-storage-meter class="min-w-0 py-2 text-xs text-gray-500 dark:text-gray-400">
		<div class="font-medium text-gray-700 dark:text-gray-200">{$i18n.t('Storage')}</div>
		<div class="relative mt-2 h-2 overflow-hidden rounded-full bg-gray-100 dark:bg-gray-800">
			<div class="absolute inset-y-0 rounded-full" style={getSystemVramBarStyle(0, percentOf(vramInfo?.storage?.used ?? 0, vramInfo?.storage?.total ?? 0))}></div>
		</div>
		<div class="mt-1.5 flex flex-wrap justify-between gap-x-3 gap-y-1 tabular-nums">
			<span>{vramInfo?.storage?.available ? `${formatBytes(vramInfo.storage.used)} / ${formatBytes(vramInfo.storage.total)}` : '--'}</span>
			<span>{$i18n.t('Free')}: {vramInfo?.storage?.available ? formatBytes(vramInfo.storage.free) : '--'}</span>
		</div>
	</div>
{/snippet}

{#snippet modelRow(item, isHighlighted)}
	{@const gm = item.gguf}
	{@const am = item.admin}
	{@const modelName = am?.name ?? gm?.filename?.replace('.gguf', '') ?? ''}
	{@const isUnloadVisualProcessing = gm && isHighlighted && (isLocalModelUnloading(gm.filename) || visualUnloadModels.has(gm.filename) || reopenedUnloadVisualModels.has(gm.filename))}
	{@const isLoadProcessing = gm && localModelActions[gm.filename] === 'load' && loadingModels.has(gm.filename)}
	{@const isProcessing = !modelsBlocked && gm && (isLoadProcessing || isUnloadVisualProcessing)}
	<div
		data-model-key={item.key}
		class="unified-model-row flex min-w-0 w-full shrink-0 overflow-hidden py-1"
		id={am ? `model-item-${am.id}` : undefined}
	>
		<div
			class="unified-model-card relative isolate flex h-full min-w-0 gap-3 w-full overflow-hidden border bg-gray-100/80 hover:bg-gray-200/80 dark:bg-gray-850/80 dark:hover:bg-gray-800/80 px-3 py-2 rounded-lg {isHighlighted ? 'border-gray-300 dark:border-gray-700' : 'border-transparent'}"
		>
			{#if am}
				<button type="button" data-edit-model={am.id} aria-label={`${$i18n.t('Edit')}: ${modelName}`} disabled={deletingModel || modelsBlocked}
					class="absolute inset-0 z-[1] rounded-[inherit] focus-visible:outline-offset-[-2px]" on:click={() => { selectedModelId = am.id; }}></button>
			{/if}
			<div class="model-avatar size-9 aspect-square self-center flex-shrink-0 group/avatar relative z-[2]">
				{#if am}
					<div class="w-9 h-9 rounded-full overflow-hidden">
						<img
							src={getModelProfileImageUrl(am)}
							alt="model"
							loading="eager"
							decoding="async"
							class="block size-full object-cover group-hover/avatar:opacity-0 transition-opacity"
						/>
					</div>
					{#if am}
						<button
							class="absolute inset-0 w-9 h-9 rounded-full flex items-center justify-center opacity-0 group-hover/avatar:opacity-100 transition-opacity bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700"
							type="button"
							on:click|stopPropagation={() => favoriteModelHandler(am.id)}
							title={$i18n.t(($settings?.favoriteModels ?? []).includes(am.id) ? 'Remove from favorites' : 'Add to favorites')}
							aria-label={$i18n.t(($settings?.favoriteModels ?? []).includes(am.id) ? 'Remove from favorites' : 'Add to favorites')}
						>
							<Bookmark className="size-4 {($settings?.favoriteModels ?? []).includes(am.id) ? 'fill-current' : ''}" />
						</button>
					{/if}
				{:else}
					<div class="size-9 rounded-full bg-gray-100 dark:bg-gray-800 flex items-center justify-center">
						<svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4 text-gray-400 dark:text-gray-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
							<path stroke-linecap="round" stroke-linejoin="round" d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />
						</svg>
					</div>
				{/if}
			</div>

			<div class="flex-1 min-w-0 self-center">
				<div class="w-full text-left">
					<div class="flex items-center gap-1.5 min-w-0">
						<span class="unified-model-name min-w-0 truncate font-medium text-sm" title={modelName}>
							{$mobile && Array.from(modelName).length > 26 ? Array.from(modelName).slice(0, 23).join('') + '...' : modelName}
						</span>
					</div>
					<div class="unified-model-meta text-xs text-gray-500 dark:text-gray-400 mt-0.5 flex flex-nowrap sm:flex-wrap overflow-x-auto sm:overflow-visible scrollbar-none items-center gap-1.5 [&>span]:shrink-0">
						{#if gm}
							<span>{gm.file_size_human}</span>
						{:else if am}
							<span class="line-clamp-1">
								{am?.meta?.description || am.id}
							</span>
						{/if}
					</div>
				</div>
			</div>

			<div class="relative z-[2] flex flex-shrink-0 items-center justify-end gap-0.5 self-center">
				{#if !gm?.is_loaded && !isHighlighted && !isLoadProcessing}
				<Tooltip content={$i18n.t('Delete')}>
					<button type="button" aria-label={$i18n.t('Delete')} disabled={localModelActionInProgress || !(gm || workspaceModels.some(model => model.id === am?.id))}
						class="grid size-8 place-items-center rounded-lg text-gray-500 dark:text-gray-400 enabled:hover:bg-black/10 dark:enabled:hover:bg-white/10 disabled:opacity-40 disabled:cursor-not-allowed"
						on:click|stopPropagation={() => { modelToDelete = { gguf: gm, admin: am }; showDeleteModel = true; }}><Trash className="size-4" /></button>
				</Tooltip>
				{/if}
				{#if gm}
					{#if isProcessing}
						<div role="status" aria-label={$i18n.t('Processing...')} class="grid size-8 place-items-center text-xs text-gray-500">
							<svg use:continuousSpinner class="w-3 h-3 animate-spin" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
								<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
								<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
							</svg>
						</div>
					{:else if gm.is_loaded}
						<Tooltip content="Descarregar">
							<button
								aria-label="Descarregar"
								class="flex items-center justify-center p-1.5 rounded-lg enabled:hover:bg-black/10 dark:enabled:hover:bg-white/10 transition text-gray-500 dark:text-gray-400 disabled:cursor-not-allowed disabled:opacity-40"
								disabled={localModelActionInProgress}
								on:click={() => {
									if (localModelActionInProgress) return;
									handleUnload(gm);
								}}
							>
								<UnloadModel />
							</button>
						</Tooltip>
					{:else}
						<Tooltip content="Carregar">
							<button
								aria-label="Carregar"
								class="flex items-center justify-center p-1.5 rounded-lg enabled:hover:bg-black/10 dark:enabled:hover:bg-white/10 transition text-gray-500 dark:text-gray-400 disabled:cursor-not-allowed disabled:opacity-40"
								disabled={localModelActionInProgress}
								on:mouseenter={() => showVramPreview(gm)}
								on:mouseleave={() => clearVramPreview(gm)}
								on:focus={() => showVramPreview(gm)}
								on:blur={() => clearVramPreview(gm)}
								on:click={() => {
									if (localModelActionInProgress) return;
									clearVramPreview(gm);
									startLoadWithPreferences(gm);
								}}
							>
								<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" class="size-5">
									<path fill-rule="evenodd" d="M2.25 12c0-5.385 4.365-9.75 9.75-9.75s9.75 4.365 9.75 9.75-4.365 9.75-9.75 9.75S2.25 17.385 2.25 12Zm14.024-.983a1.125 1.125 0 0 1 0 1.966l-5.603 3.113A1.125 1.125 0 0 1 9 15.113V8.887c0-.857.921-1.4 1.671-.983l5.603 3.113Z" clip-rule="evenodd" />
								</svg>
							</button>
						</Tooltip>
					{/if}
				{/if}

			</div>
		</div>
	</div>
{/snippet}

{#if !showDownloadModal}
	{#if selectedModelId === null}
		<div class="unified-models-shell flex h-[min(640px,90dvh)] max-h-[90vh] min-h-0 w-full flex-col overflow-hidden">

			<!-- Header -->
			<div class="grid grid-cols-2 md:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center gap-3 mx-4 pt-4 pb-6 border-b border-gray-200/50 dark:border-gray-800/50 shrink-0">
				<div class="order-1 md:order-none flex items-center gap-2 text-xl font-medium px-0.5">
					<MobileModalTitle><span>{$i18n.t('Models')}</span></MobileModalTitle>
				</div>

				<div class="search-field order-3 md:order-none col-span-2 md:col-span-1 justify-self-center">{@render searchBar()}</div>
				<div class="unified-model-actions order-2 md:order-none flex justify-self-end items-center gap-1">
					<input bind:this={modelImportInput} type="file" accept=".gguf" class="hidden" on:change={importModelFile} />
					<button type="button" class="grid size-8 shrink-0 place-items-center rounded-lg p-0 text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 disabled:opacity-50" aria-label={$i18n.t('Import models')} title={$i18n.t('Import models')} disabled={importingModel || modelsBlocked} on:click={() => modelImportInput.click()}>
						{#if importingModel}<Spinner className="block size-5" />{:else}<Upload className="block size-5" />{/if}
					</button>
					<button
						class="grid size-8 shrink-0 place-items-center rounded-lg p-0 text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 transition"
						type="button"
						aria-label={$i18n.t('Baixar modelos')} title={$i18n.t('Baixar modelos')}
						on:click={() => (showDownloadModal = true)}
					>
						<Download className="block size-5" />
					</button>
				</div>
			</div>

			<div class="unified-models-body flex min-h-0 flex-1 flex-col overflow-hidden px-4 pb-4">
				<div class="grid grid-cols-2 gap-3 sm:gap-6 px-2 pt-1 pb-2 border-b border-gray-200/50 dark:border-gray-800/50">
					{@render vramMeter()}
					{@render storageMeter()}
				</div>
				<div inert={modelsBlocked} aria-disabled={modelsBlocked} data-models-blocked={modelsBlocked}
					class="unified-model-catalog flex min-h-0 flex-1 flex-col overflow-hidden {modelsBlocked ? 'opacity-50 grayscale' : ''}">
					<div class="flex shrink-0 items-center justify-end gap-1 pr-2 pt-1.5 pb-0.5">
						<DropdownMenu.Root bind:open={sortMenuOpen}>
							<Tooltip content={$i18n.t('Sort models')}>
								<DropdownMenu.Trigger aria-label={$i18n.t('Sort models')} class={catalogControl}><ArrowUpDown className="size-3.5" /></DropdownMenu.Trigger>
							</Tooltip>
							<DropdownMenu.Content side="bottom" align="end" sideOffset={4} class="z-[10002] w-40 rounded-md border border-gray-100 dark:border-gray-800 bg-white dark:bg-gray-850 p-1 shadow-md text-sm text-gray-700 dark:text-gray-200">
								{#each ['name', 'size'] as order}
									<DropdownMenu.Item role="menuitemradio" aria-checked={modelSort === order} class="flex items-center justify-between gap-4 rounded-sm px-3 py-1.5 cursor-pointer select-none hover:bg-gray-100 dark:hover:bg-gray-800" on:click={() => setOrder(order === 'size' ? 'size' : 'name')}>
										<span>{$i18n.t(order === 'name' ? 'Name' : 'Size')}</span>
										<span class="size-4">{#if modelSort === order}<CheckCircle strokeWidth="1.7" />{/if}</span>
									</DropdownMenu.Item>
								{/each}
							</DropdownMenu.Content>
						</DropdownMenu.Root>
						<div role="group" aria-label={$i18n.t('View')} class="flex items-center gap-0.5">
							{#each ['grid', 'list'] as layout}
								{@const label = $i18n.t(layout === 'grid' ? 'Grid view' : 'List view')}
								<Tooltip content={label}><button type="button" aria-label={label} aria-pressed={modelLayout === layout} class="{catalogControl} aria-pressed:bg-gray-100 aria-pressed:text-gray-800 dark:aria-pressed:bg-gray-800 dark:aria-pressed:text-gray-100" on:click={() => setLayout(layout === 'grid' ? 'grid' : 'list')}>
									{#if layout === 'grid'}<Columns2 class="size-4" />{:else}<Rows2 class="size-4" />{/if}
								</button></Tooltip>
							{/each}
						</div>
					</div>
					<div class="model-rows-space">
					<div bind:this={modelList} use:modelGridWheel use:spaceForScrollbar={[gridModels.length, modelLayout, localLoading]} class="unified-model-list overflow-y-auto overscroll-contain">
						{#if localLoading && !hasCachedModelRows}
							<div class="h-24"></div>
						{:else if gridModels.length === 0}
							<div class="py-8 px-3 text-center">
								<div class="text-sm font-medium">{modelEmptyTitle}</div>
								<div class="mt-1 text-xs text-gray-500">{modelEmptyDescription}</div>
							</div>
						{:else}
							<div data-model-grid class="grid grid-cols-1 {modelLayout === 'grid' ? 'md:grid-cols-2' : ''} gap-x-4 gap-y-[var(--model-row-gap)]">
								{#each gridModels as item (item.key)}
									{@render modelRow(item, Boolean(item.gguf?.is_loaded || (item.gguf && isLocalModelUnloadPinned(item.gguf))))}
								{/each}
							</div>
						{/if}
					</div>
					</div>
				</div>
			</div>
		</div>

	{:else}
		<!-- ─── Model Editor ──────────────────────────────────────────────── -->
		<div class="unified-model-editor" style="height: min(640px, 90dvh); min-height: 0; width: 100%; display: flex; flex-direction: column; overflow: hidden;">
			<ModelEditor
				edit
				model={adminModels?.find((m) => m.id === selectedModelId)}
				preset={false}
				onSubmit={async (model) => {
					await upsertModelHandler(model, false);
				}}
				onBack={async () => {
					selectedModelId = null;
					await initAdmin();
				}}
			/>
		</div>
	{/if}

{/if}

<style>
	.model-rows-space {
		--model-row-height: max(72px, 4rem);
		--model-row-gap: 4px;
		container-type: size;
		flex: 1;
		min-height: var(--model-row-height);
	}
	.unified-model-list {
		height: 100%;
		scroll-snap-type: y mandatory;
	}
	.unified-model-row {
		scroll-snap-align: start;
		height: var(--model-row-height);
		min-height: var(--model-row-height);
		max-height: var(--model-row-height);
	}
	@supports (height: round(up, 4rem, 1px)) {
		.model-rows-space { --model-row-height: max(72px, round(up, 4rem, 4px)); }
		/* N rows have only N - 1 gaps. The last scroll stop must align just like the first. */
		.unified-model-list {
			height: calc(round(down, 100cqh + var(--model-row-gap), var(--model-row-height) + var(--model-row-gap)) - var(--model-row-gap));
		}
	}
	@media (max-width: 767px) {
		.unified-download-view { height: 100%; }
		.unified-models-shell { height: 100%; max-height: 100%; }
		.unified-model-editor { height: 100% !important; }
		.unified-models-body { flex: 1; overflow-y: auto; scrollbar-gutter: stable; }
		.unified-model-catalog { min-height: min-content; }
		.unified-model-name { max-width: 22ch; }
		.unified-model-meta { margin-top: 3px; }
		.unified-model-card { padding-inline: 12px; column-gap: 14px; }
		.unified-model-actions { flex-wrap: wrap; }
		.unified-model-actions button { min-height: 36px; padding: 0; }
		.model-avatar { width: 2.25rem; height: 2.25rem; overflow: hidden; }
		.model-avatar img { font-size: 0; }
	}
</style>
