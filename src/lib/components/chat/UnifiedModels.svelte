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
	import { onMount, onDestroy, getContext, tick } from 'svelte';
	import { fade, slide } from 'svelte/transition';
	import { marked } from 'marked';
	import fileSaver from 'file-saver';
	const { saveAs } = fileSaver;
	const i18n = getContext('i18n');

	import { config, models as _models, settings, user, showSettingsModelId } from '$lib/stores';
	import { NEVEAI_API_BASE_URL } from '$lib/constants';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';

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
		type LlamaCppStatus,
		type LocalModel,
		type LocalModelRuntimeEventDetail,
		type LocalVramInfo
	} from '$lib/apis/llamacpp';

	import {
		createNewModel,
		getBaseModels,
		toggleModelById,
		updateModelById,
		importModels
	} from '$lib/apis/models';
	import { getModels } from '$lib/apis';
	import { updateUserSettings } from '$lib/apis/users';
	import { toast } from 'svelte-sonner';
	import { DropdownMenu } from 'bits-ui';
	import { flyAndScale } from '$lib/utils/transitions';
	import { findMatchingMmproj } from '$lib/utils/mmproj';
	import { getLocalModelLoadPreferences, LOCAL_MODEL_CONTEXT_OPTIONS } from '$lib/utils/llamacppLoadPreferences';
	import {
		buildUnifiedAdminModels,
		type UnifiedModelsPreload
	} from '$lib/utils/unifiedModelsData';

	import ModelSettingsModal from '$lib/components/admin/Settings/Models/ModelSettingsModal.svelte';
	import ManageModelsModal from '$lib/components/admin/Settings/Models/ManageModelsModal.svelte';
	import DownloadNeveModelsModal from '$lib/components/chat/DownloadNeveModelsModal.svelte';
	import ModelEditor from '$lib/components/workspace/Models/ModelEditor.svelte';
	import ModelMenu from '$lib/components/admin/Settings/Models/ModelMenu.svelte';
	import Pagination from '$lib/components/common/Pagination.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import Dropdown from '$lib/components/common/Dropdown.svelte';
	import Spinner from '$lib/components/common/Spinner.svelte';
	import XMark from '$lib/components/icons/XMark.svelte';
	import Search from '$lib/components/icons/Search.svelte';
	import ChevronDown from '$lib/components/icons/ChevronDown.svelte';
	import ChevronUp from '$lib/components/icons/ChevronUp.svelte';
	import EllipsisHorizontal from '$lib/components/icons/EllipsisHorizontal.svelte';
	import Pin from '$lib/components/icons/Pin.svelte';
	import PinSlash from '$lib/components/icons/PinSlash.svelte';
	import CheckCircle from '$lib/components/icons/CheckCircle.svelte';
	import Minus from '$lib/components/icons/Minus.svelte';

	export let preload: UnifiedModelsPreload | null = null;
	export let show = false;

	// ─── LOCAL MODEL STATE ───────────────────────────────────────────────────
	let localModels: LocalModel[] = [];
	let mmProjFiles: string[] = [];
	let localLoading = false;
	let loadingModels: Set<string> = new Set();
	let settlingUnloadModels: Set<string> = new Set();
	let pinnedUnloadModels: Set<string> = new Set();
	let visualUnloadModels: Set<string> = new Set();
	let reopenedUnloadVisualModels: Set<string> = new Set();
	let localModelActions: Record<string, 'load' | 'unload'> = {};
	let localError = '';
	let localSuccess = '';
	let vramInfo: LocalVramInfo | null = null;
	let llamacppStatus: LlamaCppStatus | null = null;
	let vramPreviewModel: LocalModel | null = null;
	const unsubscribeLocalModelProcessing = localModelProcessingStore.subscribe((state) => {
		loadingModels = new Set(state.loading);
		settlingUnloadModels = new Set(state.settlingUnload);
		pinnedUnloadModels = new Set(state.pinnedUnload);
		visualUnloadModels = new Set(state.visualUnload);
		localModelActions = state.actions;
	});

	let loadModalMmprojFile: string = '';

	// ─── Unified load modal state ────────────────────────────────────────────
	let loadModalModel: LocalModel | null = null;
	let loadModalStep: 'context' | 'vision' = 'context';
	let loadModalFromContext = false;

	let gpuLayers: number = -1;
	let contextSize: number = 8192;

	let contextModalModel: LocalModel | null = null;
	let contextModalSize: number = 8192;

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
		const { tokenPrediction, contextShift } = getLocalModelLoadPreferences();
		if (contextShift === 'on') return 'off';
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

	$: loadedLocalModel = localModels.find((model) => model.is_loaded) ?? null;
	$: localModelActionInProgress = loadingModels.size > 0 || settlingUnloadModels.size > 0;
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
	let modelsImportInProgress = false;
	let importFiles: FileList;
	let modelsImportInputElement: HTMLInputElement;

	let adminModels: any[] = [];
	let workspaceModels: any[] | null = null;
	let baseModels: any[] | null = null;
	let selectedModelId: string | null = null;
	let showConfigModal = false;
	let showManageModal = false;
	let showDownloadModal = false;
	let viewOption = '';
	let preloadApplied = false;
	let preloadVramSignature = '';
	let highlightedLoadedModelId: string | null = null;
	let modelsBelowLoadedCollapsed = false;
	let previousShow = false;
	let collapseAnimationEnabled = false;
	let collapseAnimationTimer: ReturnType<typeof setTimeout> | null = null;
	let destroyed = false;
	let openingActionRefreshInProgress = false;
	let unifiedRefreshInFlight: Promise<LocalModel[] | null> | null = null;
	let unifiedRefreshRequested = false;
	let unifiedRefreshRequestedInitial = false;
	let realtimeRefreshTimer: ReturnType<typeof setTimeout> | null = null;
	let lastAdminRefreshAt = 0;
	const ignoredRuntimeOperationIds = new Set<string>();

	const perPage = 30;
	const MODEL_ROW_HEIGHT_PX = 72;
	const HIGHLIGHTED_MODEL_ROW_HEIGHT_PX = 72;
	const NORMAL_LIST_VISIBLE_ROWS = 6;
	const HIGHLIGHTED_LIST_VISIBLE_ROWS = 3;
	const LOCAL_UNLOAD_REOPEN_PIN_MS = 140;
	const LOCAL_UNLOAD_VISUAL_CLEAR_MS = 900;
	let currentPage = 1;

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
	const isLocalModelLoading = (filename: string) => localModelActions[filename] === 'load';
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
	const disableCollapseAnimation = () => {
		collapseAnimationEnabled = false;
		if (collapseAnimationTimer) {
			clearTimeout(collapseAnimationTimer);
			collapseAnimationTimer = null;
		}
	};
	const toggleModelsBelowLoaded = () => {
		collapseAnimationEnabled = true;
		modelsBelowLoadedCollapsed = !modelsBelowLoadedCollapsed;
		if (collapseAnimationTimer) clearTimeout(collapseAnimationTimer);
		collapseAnimationTimer = setTimeout(() => {
			collapseAnimationEnabled = false;
			collapseAnimationTimer = null;
		}, 240);
	};
	const getCacheChipLabel = (cacheType?: string | null) => {
		const normalized = (cacheType || 'f16').toLowerCase();
		if (normalized === 'f16') return 'FP16';
		if (normalized === 'f32') return 'FP32';
		return normalized.toUpperCase();
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
		localModels = data.localModels ?? [];
		mmProjFiles = data.mmProjFiles ?? [];
		adminModels = data.adminModels ?? [];
		workspaceModels = data.workspaceModels ?? [];
		baseModels = data.baseModels ?? [];
		vramInfo = data.vramInfo ?? null;
		localLoading = false;
	};

	$: if (preload?.loaded && !preloadApplied) {
		applyPreload(preload);
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
	$: filteredLocalModels = localModels.filter((m) => {
		if (searchValue === '') return true;
		const q = searchValue.toLowerCase();
		if (m.filename.toLowerCase().includes(q)) return true;
		const adm = (adminModels ?? []).find((am: any) => am.id === m.id);
		if (adm && (adm.name ?? '').toLowerCase().includes(q)) return true;
		return false;
	});

	$: filteredAdminModels = (adminModels ?? [])
		.filter(
			(m) =>
				searchValue === '' ||
				(m.name ?? '').toLowerCase().includes(searchValue.toLowerCase()) ||
				(m.id ?? '').toLowerCase().includes(searchValue.toLowerCase())
		)
		.filter((m) => {
			if (viewOption === 'enabled') return m?.is_active ?? true;
			if (viewOption === 'disabled') return !(m?.is_active ?? true);
			if (viewOption === 'visible') return !(m?.meta?.hidden ?? false);
			if (viewOption === 'hidden') return m?.meta?.hidden === true;
			return true;
		})
		.sort((a, b) => (a?.name ?? a?.id ?? '').localeCompare(b?.name ?? b?.id ?? ''));

	// Merged single list: GGUFs first (loaded then unloaded), then admin-only models
	// Loaded GGUFs appear ONCE with both load controls and admin controls
	$: mergedModels = (() => {
		const adminById = new Map((adminModels ?? []).map((m: any) => [m.id, m]));
		const ggufIds = new Set(localModels.map((gm) => gm.id).filter(Boolean));

		const ggufItems = localModels
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
			.filter((am: any) => {
				if (viewOption === 'enabled') return am?.is_active ?? true;
				if (viewOption === 'disabled') return !(am?.is_active ?? true);
				if (viewOption === 'visible') return !(am?.meta?.hidden ?? false);
				if (viewOption === 'hidden') return am?.meta?.hidden === true;
				return true;
			})
			.sort((a: any, b: any) => (a?.name ?? a?.id ?? '').localeCompare(b?.name ?? b?.id ?? ''))
			.map((am: any) => ({ key: `admin:${am.id}`, gguf: null, admin: am }));

		return [...ggufItems, ...adminOnlyItems];
	})();

	$: unloadingLocalModel = localModels.find((model) => isLocalModelUnloadPinned(model)) ?? null;
	$: activeHighlightedModelKey = loadedLocalModel?.filename ?? unloadingLocalModel?.filename ?? null;
	$: if (activeHighlightedModelKey && activeHighlightedModelKey !== highlightedLoadedModelId) {
		disableCollapseAnimation();
		highlightedLoadedModelId = activeHighlightedModelKey;
		modelsBelowLoadedCollapsed = true;
		currentPage = 1;
	} else if (!activeHighlightedModelKey && highlightedLoadedModelId) {
		disableCollapseAnimation();
		highlightedLoadedModelId = null;
		modelsBelowLoadedCollapsed = false;
	}
	$: {
		const openingModal = show && !previousShow;
		const closingModal = !show && previousShow;
		previousShow = show;
		if (openingModal) {
			selectedModelId = null;
			guardReopenedUnloadVisuals();
			disableCollapseAnimation();
			currentPage = 1;
			modelsBelowLoadedCollapsed = true;
			void refreshUnifiedModelData(false);
			void refreshLocalActionsAfterOpen();
		} else if (closingModal) {
			pinUnsettledUnloadsBeforeClose();
			disableCollapseAnimation();
			modelsBelowLoadedCollapsed = true;
			selectedModelId = null;
		}
	}
	$: highlightedLoadedItem =
		mergedModels.find(
			(item) =>
				item.gguf?.is_loaded ||
				(item.gguf && isLocalModelUnloadPinned(item.gguf))
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
	$: hasHighlightedLoadedModel = Boolean(highlightedLoadedItem);
	$: scrollableMergedModels = highlightedLoadedItem ? mergedModels.filter((item) => item.key !== highlightedLoadedItem.key) : mergedModels;
	$: filteredScrollableMergedModels = localAccessError
		? []
		: hasHighlightedLoadedModel
		? scrollableMergedModels
		: scrollableMergedModels.filter((item) => matchesModelSearch(item, searchValue));
	$: hasCollapsibleModelsBelow = hasHighlightedLoadedModel && scrollableMergedModels.length > 0;
	$: modelListPageSize = perPage;
	$: modelListPaginationCount = filteredScrollableMergedModels.length;
	$: visibleMergedModels = hasHighlightedLoadedModel && modelsBelowLoadedCollapsed
		? []
		: filteredScrollableMergedModels.slice((currentPage - 1) * modelListPageSize, currentPage * modelListPageSize);
	$: modelListVisibleRows = hasHighlightedLoadedModel ? HIGHLIGHTED_LIST_VISIBLE_ROWS : NORMAL_LIST_VISIBLE_ROWS;
	$: modelListMaxHeight = `${modelListVisibleRows * (hasHighlightedLoadedModel ? HIGHLIGHTED_MODEL_ROW_HEIGHT_PX : MODEL_ROW_HEIGHT_PX)}px`;
	$: modelListHasOverflow = modelListPaginationCount > modelListVisibleRows;
	$: modelListViewportStyle = modelListPaginationCount === 0
		? `height: ${modelListMaxHeight};`
		: modelListHasOverflow
			? `height: ${modelListMaxHeight}; max-height: ${modelListMaxHeight}; scrollbar-gutter: stable;`
			: `max-height: ${modelListMaxHeight}; scrollbar-gutter: stable;`;
	$: modelEmptyTitle = localAccessError
		? 'Não foi possível acessar modelos locais'
		: llamacppStatus && !llamacppStatus.server_binary_exists
			? 'llama.cpp não encontrado'
			: searchValue
				? 'Nenhum modelo encontrado'
				: 'Nenhum modelo instalado';
	$: modelEmptyDescription = localAccessError
		? 'Verifique se o backend está em execução e tente reabrir esta janela.'
		: llamacppStatus && !llamacppStatus.server_binary_exists
			? 'Execute o instalador para baixar o llama.cpp antes de carregar modelos locais.'
			: searchValue
				? 'Tente ajustar sua pesquisa para encontrar o modelo que está procurando.'
				: 'Clique em "Baixar modelos" para instalar um modelo ou coloque arquivos .gguf na pasta models.';
	$: if (hasHighlightedLoadedModel && searchValue) {
		searchValue = '';
	}

	$: if (searchValue || viewOption !== undefined) {
		currentPage = 1;
	}

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

	async function refreshGlobalModelsStore() {
		try {
			_models.set(await getModels(localStorage.token));
		} catch {
			// Best effort: a post-action refresh should not look like the action failed.
		}
	}

	const isSameLocalModel = (localModel: LocalModel, model: LocalModel) =>
		localModel.id === model.id || localModel.filename === model.filename;

	const markLocalModelLoaded = (model: LocalModel, result: any, mmprojFilename: string | null = null) => {
		localModels = localModels.map((localModel) =>
			isSameLocalModel(localModel, model)
				? {
						...localModel,
						is_loaded: true,
						loaded_at: Date.now(),
						n_gpu_layers: result?.n_gpu_layers ?? gpuLayers,
						n_ctx: result?.n_ctx ?? contextSize,
						mmproj_filename: result?.mmproj_filename ?? mmprojFilename,
						cache_type: result?.cache_type ?? getCacheTypeForLoad(),
						speculative_decoding:
							result?.speculative_decoding ?? getSpeculativeDecodingForLoad(),
						token_prediction: result?.token_prediction ?? getTokenPredictionForLoad(),
						context_shift: result?.context_shift ?? getContextShiftForLoad()
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
						context_shift: null
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
						context_shift: null
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
				getContextShiftForLoad()
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

	function startLoadWithContextModal(model: LocalModel) {
		if (localModelActionInProgress) return;
		const preferences = getLocalModelLoadPreferences();
		if (preferences.context !== 'ask') {
			contextSize = preferences.context;
			continueAfterContextSelection(model);
			return;
		}

		loadModalModel = model;
		loadModalStep = 'context';
		loadModalFromContext = true;
		contextModalModel = model;
		contextModalSize = 8192;
	}

	function continueAfterContextSelection(model: LocalModel) {
		const preferences = getLocalModelLoadPreferences();
		const matchingMmproj = findMatchingMmproj(model.filename, mmProjFiles);

		if (matchingMmproj) {
			if (preferences.vision === 'ask') {
				loadModalModel = model;
				loadModalMmprojFile = matchingMmproj;
				loadModalStep = 'vision';
				loadModalFromContext = true;
				return;
			}

			if (preferences.vision === 'yes') {
				loadModalModel = null;
				loadModalMmprojFile = '';
				handleLoadWithMmproj(model, matchingMmproj);
				return;
			}
		}

		loadModalModel = null;
		loadModalMmprojFile = '';
		handleLoad(model);
	}

	function confirmContextAndProceed() {
		const model = contextModalModel ?? loadModalModel;
		if (!model) return;
		contextSize = contextModalSize;
		contextModalModel = null;
		continueAfterContextSelection(model);
	}

	function handleVisionNo() {
		const model = loadModalModel;
		const fromContext = loadModalFromContext;
		loadModalModel = null;
		loadModalMmprojFile = '';
		loadModalFromContext = false;
		if (fromContext && model) handleLoad(model);
	}

	function handleVisionYes() {
		const model = loadModalModel;
		const mmprojFile = loadModalMmprojFile;
		if (!model || !mmprojFile) return;
		handleLoadWithMmproj(model, mmprojFile);
	}

	async function handleLoadWithMmproj(model: LocalModel, mmprojFile: string) {
		if (localModelActionInProgress) return;
		loadModalModel = null;
		loadModalMmprojFile = '';
		loadModalFromContext = false;
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
				getContextShiftForLoad()
			);
			markLocalModelLoaded(model, result, mmprojFile);
			localSuccess = `${model.filename} carregado! (visão: ${mmprojFile})`;
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
		currentPage = 1;
		setLocalModelAction(model.filename, 'unload');
		localError = '';
		localSuccess = '';
		let completed = false;
		try {
			await unloadLocalModel(localStorage.token, model.id);
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
		try {
			baseModels = [...$_models];
			try {
				const res = await getBaseModels(localStorage.token);
				workspaceModels = Array.isArray(res) ? res : [];
			} catch (e) {
				workspaceModels = [];
			}
			adminModels = buildUnifiedAdminModels(localModelSource, baseModels, workspaceModels ?? []);
		} catch (e) {
			console.error('[UnifiedModels] initAdmin error:', e);
			if (adminModels.length === 0) adminModels = baseModels ?? [];
		}
	};

	async function performUnifiedModelRefresh(initial: boolean): Promise<LocalModel[] | null> {
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
				await initAdmin(newLocalModels);
				lastAdminRefreshAt = Date.now();
			}
			if (destroyed) return null;
			localError = '';
			if (JSON.stringify(newLocalModels) !== JSON.stringify(localModels)) localModels = newLocalModels;
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
			if (initial) localLoading = false;
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
				context_shift: model.context_shift
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
		const delay = hasActiveAction ? 700 : show ? 1000 : 2500;
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
		if ((workspaceModels ?? []).find((m) => m.id === model.id)) {
			const res = await updateModelById(localStorage.token, model.id, model).catch(() => null);
			if (res && showToast) toast.success($i18n.t('Model updated successfully'));
		} else {
			const res = await createNewModel(localStorage.token, {
				meta: {},
				id: model.id,
				name: model.name,
				base_model_id: null,
				params: {},
				access_grants: [],
				...model
			}).catch(() => null);
			if (res && showToast) toast.success($i18n.t('Model updated successfully'));
		}
		if (showToast) {
			await initAdmin();
		}
		_models.set(
			await getModels(
				localStorage.token,
				$config?.features?.enable_direct_connections && ($settings?.directConnections ?? null)
			)
		);
	};

	const toggleModelHandler = async (model: any) => {
		if (!Object.keys(model).includes('base_model_id')) {
			await createNewModel(localStorage.token, {
				id: model.id,
				name: model.name,
				base_model_id: null,
				meta: {},
				params: {},
				access_grants: [],
				is_active: model.is_active
			}).catch(() => null);
		} else {
			await toggleModelById(localStorage.token, model.id);
		}
		_models.set(
			await getModels(
				localStorage.token,
				$config?.features?.enable_direct_connections && ($settings?.directConnections ?? null)
			)
		);
		await initAdmin();
	};

	const enableAllHandler = async () => {
		const toEnable = filteredAdminModels.filter((m) => !(m.is_active ?? true));
		toEnable.forEach((m) => (m.is_active = true));
		adminModels = adminModels;
		await Promise.all(toEnable.map((m) => toggleModelById(localStorage.token, m.id)));
	};

	const disableAllHandler = async () => {
		const toDisable = filteredAdminModels.filter((m) => m.is_active ?? true);
		toDisable.forEach((m) => (m.is_active = false));
		adminModels = adminModels;
		await Promise.all(toDisable.map((m) => toggleModelById(localStorage.token, m.id)));
	};

	const exportModelHandler = async (model: any) => {
		const blob = new Blob([JSON.stringify([model])], { type: 'application/json' });
		saveAs(blob, `${model.id}-${Date.now()}.json`);
	};

	const cloneHandler = async (model: any) => {
		sessionStorage.model = JSON.stringify({
			...model,
			base_model_id: model.id,
			id: `${model.id}-clone`,
			name: `${model.name} (Clone)`
		});
		goto('/workspace/models/create');
	};

	const pinModelHandler = async (modelId: string) => {
		let pinnedModels = $settings?.pinnedModels ?? [];
		if (pinnedModels.includes(modelId)) {
			pinnedModels = pinnedModels.filter((id) => id !== modelId);
		} else {
			pinnedModels = [...new Set([...pinnedModels, modelId])];
		}
		settings.set({ ...$settings, pinnedModels });
		await updateUserSettings(localStorage.token, { ui: $settings });
	};

	onMount(() => {
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

		void (async () => {
			await refreshUnifiedModelData(!preloadApplied);
			await refreshLocalActionsAfterOpen();
			scheduleRealtimeRefresh();
		})();

		const refreshOnFocus = () => {
			if (destroyed) return;
			void refreshUnifiedModelData(false);
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
		disableCollapseAnimation();
		cancelAllLocalActionTimers();
		ignoredRuntimeOperationIds.clear();
		unsubscribeLocalModelProcessing();
	});
</script>

<!-- ─── Unified load modal ──────────────────────────────────────────────── -->
{#if loadModalModel}
	<div class="fixed inset-0 z-[10001] flex items-center justify-center bg-black/40" in:fade={{ duration: 80 }} out:fade={{ duration: 60 }}>
		<div class="bg-white dark:bg-gray-900 rounded-2xl p-5 shadow-xl mx-4 w-80 flex flex-col gap-3">

			{#if loadModalStep === 'context'}
				<p class="text-sm font-semibold text-gray-900 dark:text-white">Tamanho do Contexto</p>
				<div class="flex flex-col gap-1.5 max-h-80 overflow-y-auto scrollbar-none">
					{#each LOCAL_MODEL_CONTEXT_OPTIONS as sz}
						<button
							class="flex items-center justify-between px-3 py-2 rounded-lg text-xs text-left transition {contextModalSize === sz ? 'bg-black text-white dark:bg-white dark:text-black' : 'text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800'}"
							on:click={() => (contextModalSize = sz)}
						>
							<span>{sz.toLocaleString()} tokens</span>
							{#if sz === 8192}
								<span class="text-[11px] opacity-60">Padrão</span>
							{/if}
						</button>
					{/each}
				</div>
				<div class="flex justify-end gap-2 mt-1">
					<button
						class="px-4 py-1.5 text-xs rounded-lg bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 transition font-medium"
						on:click={() => (loadModalModel = null)}
					>Cancelar</button>
					<button
						class="px-4 py-1.5 text-xs rounded-lg bg-black text-white dark:bg-white dark:text-black hover:opacity-90 transition font-medium"
						on:click={confirmContextAndProceed}
					>Confirmar</button>
				</div>

			{:else if loadModalStep === 'vision'}
				<p class="text-sm font-semibold text-gray-900 dark:text-white">Deseja carregar a visão?</p>
				<p class="text-xs text-gray-500 dark:text-gray-400">O modelo será carregado com suporte a análise de imagens.</p>
				<div class="flex justify-end gap-2 mt-1">
					<button
						class="px-4 py-1.5 text-xs rounded-lg bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 transition font-medium"
						on:click={handleVisionNo}
					>Não</button>
					<button
						class="px-4 py-1.5 text-xs rounded-lg bg-black text-white dark:bg-white dark:text-black hover:opacity-90 transition font-medium"
						on:click={handleVisionYes}
					>Sim</button>
				</div>

			{/if}

		</div>
	</div>
{/if}

<ModelSettingsModal bind:show={showConfigModal} initHandler={initAdmin} />
<ManageModelsModal bind:show={showManageModal} />
<DownloadNeveModelsModal
	bind:show={showDownloadModal}
	on:modelsChanged={refreshAfterCatalogChange}
/>

{#snippet searchBar()}
	<div class="px-3.5 flex shrink-0 items-center w-full space-x-2 py-0.5 pb-2">
		<div class="flex flex-1 items-center">
			<div class="self-center ml-1 mr-3">
				<Search className="size-3.5" />
			</div>
			<input
				class="w-full text-sm py-1 rounded-r-xl outline-hidden bg-transparent"
				bind:value={searchValue}
				placeholder={$i18n.t('Search Models')}
			/>
			{#if searchValue}
				<div class="self-center pl-1.5 translate-y-[0.5px]">
					<button
						class="p-0.5 rounded-full hover:bg-gray-100 dark:hover:bg-gray-900 transition"
						on:click={() => (searchValue = '')}
					>
						<XMark className="size-3" strokeWidth="2" />
					</button>
				</div>
			{/if}
		</div>
	</div>
{/snippet}

{#snippet vramMeter()}
	<div class="px-3.5 pb-2 shrink-0">
		{#if vramInfo === null}
			<div class="rounded-xl border border-gray-200/70 dark:border-gray-800 px-3 py-2 text-xs text-gray-500 dark:text-gray-400">
				<div class="flex items-center justify-between gap-3">
					<span class="font-medium text-gray-700 dark:text-gray-200">VRAM</span>
					<span>Detectando...</span>
				</div>
				<div class="mt-2 h-2 rounded-full bg-gray-100 dark:bg-gray-800 overflow-hidden">
					<div class="h-full w-1/4 rounded-full bg-gray-300 dark:bg-gray-700 animate-pulse"></div>
				</div>
			</div>
		{:else if vramInfo.available}
			<div class="rounded-xl border border-gray-200/70 dark:border-gray-800 px-3 py-2 text-xs text-gray-500 dark:text-gray-400">
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

				<div class="mt-1.5 flex items-center justify-between gap-3">
					<span class="min-w-0 truncate">
						Uso: {formatBytes(vramDisplayedUsedBytes)} / {formatBytes(vramInfo.total)}
					</span>
					{#if vramPreviewModel && vramProjectedOffloadBytes > 0}
						<span class="shrink-0 text-red-600 dark:text-red-300">RAM: {formatBytes(vramProjectedOffloadBytes)}</span>
					{:else if loadedModelHasOffload}
						<span class="shrink-0 text-red-600 dark:text-red-300">RAM: uso parcial</span>
					{:else}
						<span class="shrink-0">Livre: {formatBytes(vramDisplayedFreeBytes)}</span>
					{/if}
				</div>
			</div>
		{:else}
			<div class="rounded-xl border border-dashed border-gray-200/80 dark:border-gray-800 px-3 py-2 text-xs text-gray-500 dark:text-gray-400">
				<div class="flex items-center gap-3">
					<span class="font-medium text-gray-700 dark:text-gray-200">VRAM</span>
				</div>
				<div class="mt-1">
					Use modelos CPU ou instale drivers compatíveis.
				</div>
			</div>
		{/if}
	</div>
{/snippet}

{#snippet modelRow(item, isHighlighted)}
	{@const gm = item.gguf}
	{@const am = item.admin}
	{@const isUnloadVisualProcessing = gm && isHighlighted && (isLocalModelUnloading(gm.filename) || visualUnloadModels.has(gm.filename) || reopenedUnloadVisualModels.has(gm.filename))}
	{@const isLoadProcessing = gm && localModelActions[gm.filename] === 'load' && loadingModels.has(gm.filename)}
	{@const isProcessing = gm && (isLoadProcessing || isUnloadVisualProcessing)}
	{@const rowHeight = HIGHLIGHTED_MODEL_ROW_HEIGHT_PX}
	<div
		class="flex w-full snap-start shrink-0 overflow-hidden px-3 py-1 {(am?.meta?.hidden || (am && !(am?.is_active ?? true))) ? 'opacity-50' : ''}"
		style={`height: ${rowHeight}px; min-height: ${rowHeight}px; max-height: ${rowHeight}px;`}
		id={am ? `model-item-${am.id}` : undefined}
	>
		<div
			class="flex h-full min-w-0 gap-3 w-full overflow-hidden px-2 py-2 rounded-lg transition-colors cursor-pointer {(gm?.is_loaded || isProcessing) ? 'border border-gray-200 dark:border-gray-700 bg-gray-50/50 dark:bg-gray-800/30' : 'hover:bg-gray-50 dark:hover:bg-gray-850/50'}"
			on:click={(e) => {
				if (am && (am?.is_active ?? true) && !(e.target as HTMLElement).closest('button') && !(e.target as HTMLElement).closest('[data-melt-dropdown-menu]')) {
					selectedModelId = am.id;
				}
			}}
		>
			<div class="self-center flex-shrink-0 group/avatar relative">
				{#if am}
					<div class="w-9 h-9 rounded-full overflow-hidden {(am?.is_active ?? true) ? '' : 'opacity-50'}">
						<img
							src={getModelProfileImageUrl(am)}
							alt="model"
							loading="eager"
							decoding="async"
							class="w-full h-full object-cover group-hover/avatar:opacity-0 transition-opacity"
						/>
					</div>
					{#if (am?.is_active ?? true)}
						<button
							class="absolute inset-0 w-9 h-9 rounded-full flex items-center justify-center opacity-0 group-hover/avatar:opacity-100 transition-opacity bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700"
							type="button"
							on:click|stopPropagation={() => pinModelHandler(am.id)}
							title={($settings?.pinnedModels ?? []).includes(am.id) ? 'Desfixar' : 'Fixar'}
						>
							{#if ($settings?.pinnedModels ?? []).includes(am.id)}
								<PinSlash />
							{:else}
								<Pin />
							{/if}
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
					<div class="flex items-center gap-1.5 flex-wrap">
						<span class="font-medium text-sm line-clamp-1">
							{am?.name ?? gm?.filename?.replace('.gguf', '') ?? ''}
						</span>
					</div>
					<div class="text-xs text-gray-500 dark:text-gray-400 mt-0.5 flex flex-wrap items-center gap-1.5">
						{#if gm}
							{#if gm.is_loaded}
								{#if gm.n_ctx !== null}
									<span class="inline-flex h-5 items-center rounded-md bg-gray-100 px-1.5 text-[11px] font-medium text-gray-700 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-200">CTX: {gm.n_ctx}</span>
								{/if}
								<span class="inline-flex h-5 items-center rounded-md bg-gray-100 px-1.5 text-[11px] font-medium text-gray-700 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-200">KV: {getCacheChipLabel(gm.cache_type)}</span>
								{#if isContextShiftActive(gm.context_shift)}
									<span class="inline-flex h-5 items-center rounded-md bg-gray-100 px-1.5 text-[11px] font-medium text-gray-700 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-200">DC: Ligado</span>
								{:else if isTokenPredictionActive(gm.token_prediction)}
									<span class="inline-flex h-5 items-center rounded-md bg-gray-100 px-1.5 text-[11px] font-medium text-gray-700 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-200">PT: {getTokenPredictionChipLabel(gm.token_prediction)}</span>
								{:else if isSpeculativeDecodingActive(gm.speculative_decoding)}
									<span class="inline-flex h-5 items-center rounded-md bg-gray-100 px-1.5 text-[11px] font-medium text-gray-700 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-200">DE: {getSpeculativeChipLabel(gm.speculative_decoding)}</span>
								{/if}
								{#if gm?.mmproj_filename}
									<span class="inline-flex h-5 items-center rounded-md bg-gray-100 px-1.5 text-[11px] font-medium text-gray-700 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-200">Visão: Sim</span>
								{:else}
									<span class="inline-flex h-5 items-center rounded-md bg-gray-100 px-1.5 text-[11px] font-medium text-gray-700 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-200">Visão: Não</span>
								{/if}
							{:else}
								<span>{gm.file_size_human}</span>
							{/if}
						{:else if am}
							<span class="line-clamp-1">
								{!!am?.meta?.description
									? am?.meta?.description
									: am?.ollama?.digest
										? `${am.id} (${am?.ollama?.digest})`
										: am.id}
							</span>
						{/if}
					</div>
				</div>
			</div>

			<div class="flex w-32 flex-shrink-0 items-center justify-end gap-0.5 self-center">
				{#if gm && (am?.is_active ?? true)}
					{#if isProcessing}
						<div class="flex items-center gap-1.5 px-3 py-1.5 text-xs text-gray-500">
							<svg class="w-3 h-3 animate-spin" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
								<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
								<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
							</svg>
							Processando...
						</div>
					{:else if gm.is_loaded}
						<Tooltip content="Descarregar">
							<button
								class="flex items-center justify-center p-1.5 rounded-lg hover:bg-black/5 dark:hover:bg-white/5 transition text-gray-500 dark:text-gray-400 disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-transparent dark:disabled:hover:bg-transparent"
								disabled={localModelActionInProgress}
								on:click={() => {
									if (localModelActionInProgress) return;
									handleUnload(gm);
								}}
							>
								<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" class="size-5">
									<path fill-rule="evenodd" d="M2.25 12c0-5.385 4.365-9.75 9.75-9.75s9.75 4.365 9.75 9.75-4.365 9.75-9.75 9.75S2.25 17.385 2.25 12Zm6-2.438c0-.724.588-1.312 1.313-1.312h4.874c.725 0 1.313.588 1.313 1.313v4.874c0 .725-.588 1.313-1.313 1.313H9.564a1.312 1.312 0 0 1-1.313-1.313V9.564Z" clip-rule="evenodd" />
								</svg>
							</button>
						</Tooltip>
					{:else}
						<Tooltip content="Carregar">
							<button
								class="flex items-center justify-center p-1.5 rounded-lg hover:bg-black/5 dark:hover:bg-white/5 transition text-gray-500 dark:text-gray-400 disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-transparent dark:disabled:hover:bg-transparent"
								disabled={localModelActionInProgress}
								on:mouseenter={() => showVramPreview(gm)}
								on:mouseleave={() => clearVramPreview(gm)}
								on:focus={() => showVramPreview(gm)}
								on:blur={() => clearVramPreview(gm)}
								on:click={() => {
									if (localModelActionInProgress) return;
									clearVramPreview(gm);
									startLoadWithContextModal(gm);
								}}
							>
								<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" class="size-5">
									<path fill-rule="evenodd" d="M2.25 12c0-5.385 4.365-9.75 9.75-9.75s9.75 4.365 9.75 9.75-4.365 9.75-9.75 9.75S2.25 17.385 2.25 12Zm14.024-.983a1.125 1.125 0 0 1 0 1.966l-5.603 3.113A1.125 1.125 0 0 1 9 15.113V8.887c0-.857.921-1.4 1.671-.983l5.603 3.113Z" clip-rule="evenodd" />
								</svg>
							</button>
						</Tooltip>
					{/if}
				{/if}

				{#if gm && am}<div class="w-2 flex-shrink-0"></div>{/if}
				{#if am}
					{#if !(gm && (gm.is_loaded || isProcessing))}
						<div class="ml-1">
							<Tooltip content={(am?.is_active ?? true) ? $i18n.t('Enabled') : $i18n.t('Disabled')}>
								<button
									type="button"
									class="flex h-[1.125rem] min-h-[1.125rem] w-8 shrink-0 cursor-pointer items-center rounded-full px-[2px] mx-[1px] transition-colors outline outline-1 outline-gray-100 dark:outline-gray-800 {(am?.is_active ?? true) ? 'bg-blue-500 dark:bg-blue-600' : 'bg-gray-200 dark:bg-transparent'}"
									on:click|stopPropagation={() => {
										const newActive = !(am.is_active ?? true);
										adminModels = adminModels.map((m) =>
											m.id === am.id ? { ...m, is_active: newActive } : m
										);
										toggleModelHandler({ ...am, is_active: newActive });
									}}
								>
									<span
										class="pointer-events-none block size-3 shrink-0 rounded-full bg-white shadow-sm transition-transform {(am?.is_active ?? true) ? 'translate-x-4' : 'translate-x-0'}"
									></span>
								</button>
							</Tooltip>
						</div>
					{/if}
				{/if}
			</div>
		</div>
	</div>
{/snippet}

{#if true}
	{#if selectedModelId === null}
		<div class="flex max-h-[90vh] min-h-0 w-full flex-col overflow-hidden">

			<!-- Header -->
			<div class="flex items-center justify-between px-4 pt-4 pb-2 shrink-0">
				<div class="flex items-center gap-2 text-xl font-medium px-0.5">
					<span>Modelos</span>
				</div>

				<div class="flex items-center gap-1.5">
					<button
						class="flex text-xs items-center gap-1 px-3 py-1.5 rounded-lg bg-gray-50 hover:bg-gray-100 dark:bg-gray-850 dark:hover:bg-gray-800 dark:text-gray-200 transition font-medium"
						type="button"
						on:click={() => (showDownloadModal = true)}
					>
						<span>{$i18n.t('Baixar modelos')}</span>
					</button>
					<button
						class="flex text-xs items-center gap-1 px-3 py-1.5 rounded-lg bg-black hover:bg-gray-900 text-white dark:bg-white dark:hover:bg-gray-100 dark:text-black transition font-medium"
						type="button"
						on:click={() => (showConfigModal = true)}
					>
						<span>{$i18n.t('Configura\u00e7\u00f5es globais')}</span>
					</button>
				</div>
			</div>

			<!-- Fixed controls + scrollable models -->
			<div class="min-h-0 overflow-hidden px-3.5 pb-2">
				<div class="flex max-h-full min-h-0 flex-col overflow-hidden rounded-3xl bg-white py-2 dark:bg-gray-900">
					{#if !hasHighlightedLoadedModel}
						{@render searchBar()}
					{/if}

					{@render vramMeter()}

					{#if highlightedLoadedItem}
						<div class="shrink-0 mb-2">
							{@render modelRow(highlightedLoadedItem, true)}
						</div>
					{/if}

					{#if !hasHighlightedLoadedModel || !modelsBelowLoadedCollapsed}
						<div class="min-h-0 overflow-hidden" transition:slide={{ duration: collapseAnimationEnabled ? 180 : 0 }}>
							<div
								class="min-h-0 snap-y snap-mandatory overscroll-contain pb-0 {modelListPaginationCount === 0 ? 'mr-0 overflow-hidden pr-0' : 'mr-1 overflow-y-auto pr-1'}"
								style={modelListViewportStyle}
							>
								{#if localLoading && localModels.length === 0 && (adminModels?.length ?? 0) === 0}
									<div class="py-8"></div>
								{:else if modelListPaginationCount === 0}
									<div
										class="flex w-full flex-col items-center justify-center px-6 text-center"
										style={`height: ${modelListMaxHeight};`}
									>
										<div class="max-w-md text-center">
											<div class="text-lg font-medium mb-1">{$i18n.t(modelEmptyTitle)}</div>
											<div class="text-gray-500 text-center text-xs">
												{$i18n.t(modelEmptyDescription)}
											</div>
										</div>
									</div>
								{:else if visibleMergedModels.length > 0}
									{#each visibleMergedModels as item (item.key)}
										{@render modelRow(item, false)}
									{/each}
								{/if}

								{#if !modelsBelowLoadedCollapsed && modelListPaginationCount > modelListPageSize}
									<Pagination bind:page={currentPage} count={modelListPaginationCount} perPage={modelListPageSize} />
								{/if}
							</div>
						</div>
						{/if}

					{#if hasCollapsibleModelsBelow}
						<div class="flex shrink-0 justify-center px-3 pt-2 pb-1">
							<Tooltip content={modelsBelowLoadedCollapsed ? 'Mostrar modelos' : 'Ocultar modelos'}>
								<button
									type="button"
									class="flex size-7 items-center justify-center rounded-full border border-gray-200 bg-white text-gray-500 shadow-sm transition hover:bg-gray-50 hover:text-gray-800 dark:border-gray-800 dark:bg-gray-900 dark:text-gray-400 dark:hover:bg-gray-850 dark:hover:text-gray-100"
									on:click={toggleModelsBelowLoaded}
									aria-label={modelsBelowLoadedCollapsed ? 'Mostrar modelos' : 'Ocultar modelos'}
								>
									{#if modelsBelowLoadedCollapsed}
										<ChevronUp className="size-4" />
									{:else}
										<ChevronDown className="size-4" />
									{/if}
								</button>
							</Tooltip>
						</div>
					{/if}
				</div>
			</div>
		</div>

	{:else}
		<!-- ─── Model Editor ──────────────────────────────────────────────── -->
		<div style="height: 600px; min-height: 0; width: 100%; display: flex; flex-direction: column; overflow: hidden;">
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

{:else}
	<!-- Loading admin models — focus-trap needs at least one tabbable node -->
	<div class="flex items-center justify-center py-16 px-8">
		<button class="sr-only" tabindex="0" aria-hidden="true"> </button>
	</div>
{/if}
