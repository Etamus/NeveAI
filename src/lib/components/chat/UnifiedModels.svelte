<script lang="ts">
	import { onMount, onDestroy, getContext } from 'svelte';
	import { fade } from 'svelte/transition';
	import { marked } from 'marked';
	import fileSaver from 'file-saver';
	const { saveAs } = fileSaver;
	const i18n = getContext('i18n');

	import { config, models as _models, settings, user, showSettingsModelId } from '$lib/stores';
	import { WEBUI_API_BASE_URL } from '$lib/constants';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';

	import {
		getLocalModels,
		getMmProjFiles,
		loadLocalModel,
		unloadLocalModel,
		type LocalModel
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
	import EllipsisHorizontal from '$lib/components/icons/EllipsisHorizontal.svelte';
	import EyeSlash from '$lib/components/icons/EyeSlash.svelte';
	import Eye from '$lib/components/icons/Eye.svelte';
	import Pin from '$lib/components/icons/Pin.svelte';
	import PinSlash from '$lib/components/icons/PinSlash.svelte';
	import CheckCircle from '$lib/components/icons/CheckCircle.svelte';
	import Minus from '$lib/components/icons/Minus.svelte';

	// ─── LOCAL MODEL STATE ───────────────────────────────────────────────────
	let localModels: LocalModel[] = [];
	let mmProjFiles: string[] = [];
	let localLoading = false;
	let loadingModels: Set<string> = new Set();
	let localError = '';
	let localSuccess = '';

	let loadModalMmprojFile: string = '';

	// ─── Unified load modal state ────────────────────────────────────────────
	let loadModalModel: LocalModel | null = null;
	let loadModalStep: 'context' | 'vision' = 'context';
	let loadModalFromContext = false;

	let gpuLayers: number = -1;
	let contextSize: number = 8192;

	let contextModalModel: LocalModel | null = null;
	let contextModalSize: number = 8192;

	// ─── ADMIN MODEL STATE ───────────────────────────────────────────────────
	let shiftKey = false;
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

	const perPage = 30;
	let currentPage = 1;

	// ─── SHARED SEARCH ──────────────────────────────────────────────────────
	let searchValue = '';

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
		const q = searchValue.toLowerCase();

		const ggufItems = localModels
			.filter((gm) => {
				if (!q) return true;
				if (gm.filename.toLowerCase().includes(q)) return true;
				const adm = adminById.get(gm.id);
				if (adm && (adm.name ?? '').toLowerCase().includes(q)) return true;
				return false;
			})
			.map((gm) => ({ key: `gguf:${gm.id ?? gm.filename}`, gguf: gm, admin: adminById.get(gm.id) ?? null }));

		// Sort GGUFs: loaded first, then unloaded
		ggufItems.sort((a, b) => {
			const aLoaded = a.gguf?.is_loaded ? 1 : 0;
			const bLoaded = b.gguf?.is_loaded ? 1 : 0;
			return bLoaded - aLoaded;
		});

		const adminOnlyItems = (adminModels ?? [])
			.filter((am: any) => !ggufIds.has(am.id))
			.filter((am: any) => !q || (am.name ?? '').toLowerCase().includes(q) || (am.id ?? '').toLowerCase().includes(q))
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

	$: if (searchValue || viewOption !== undefined) {
		currentPage = 1;
	}

	// ─── LOCAL MODEL FUNCTIONS ───────────────────────────────────────────────
	async function refreshLocalModels(initial = true) {
		if (initial) localLoading = true;
		localError = '';
		try {
			const [newLocalModels, newMmProjFiles] = await Promise.all([
				getLocalModels(localStorage.token),
				getMmProjFiles(localStorage.token)
			]);
			if (JSON.stringify(newLocalModels) !== JSON.stringify(localModels)) localModels = newLocalModels;
			if (JSON.stringify(newMmProjFiles) !== JSON.stringify(mmProjFiles)) mmProjFiles = newMmProjFiles;
		} catch (e: any) {
			localError =
				e.message === 'Failed to fetch'
					? 'Falha ao buscar'
					: e.message || 'Erro ao buscar modelos locais';
		} finally {
			if (initial) localLoading = false;
		}
	}

	async function handleLoad(model: LocalModel) {
		loadingModels = new Set([...loadingModels, model.filename]);
		localError = '';
		localSuccess = '';
		try {
			const ct = localStorage.getItem('llamacpp_cache_type') || 'q8_0';
			await loadLocalModel(localStorage.token, model.filename, gpuLayers, contextSize, '', ct);
			localSuccess = `${model.filename} carregado com sucesso!`;
			await refreshLocalModels();
			_models.set(await getModels(localStorage.token));
			await initAdmin();
		} catch (e: any) {
			localError = e.message || 'Erro ao carregar modelo';
		} finally {
			loadingModels = new Set([...loadingModels].filter((f) => f !== model.filename));
		}
	}

	function startLoadWithContextModal(model: LocalModel) {
		loadModalModel = model;
		loadModalStep = 'context';
		loadModalFromContext = true;
		contextModalModel = model;
		contextModalSize = 8192;
	}

	function confirmContextAndProceed() {
		const model = contextModalModel ?? loadModalModel;
		if (!model) return;
		contextSize = contextModalSize;
		contextModalModel = null;
		const matchingMmproj = findMatchingMmproj(model.filename, mmProjFiles);
		if (matchingMmproj) {
			loadModalMmprojFile = matchingMmproj;
			loadModalStep = 'vision';
		} else {
			loadModalModel = null;
			loadModalMmprojFile = '';
			handleLoad(model);
		}
	}

	function handleVisionNo() {
		const model = loadModalModel;
		const fromContext = loadModalFromContext;
		loadModalModel = null;
		loadModalMmprojFile = '';
		if (fromContext && model) handleLoad(model);
	}

	function handleVisionYes() {
		const model = loadModalModel;
		const mmprojFile = loadModalMmprojFile;
		if (!model || !mmprojFile) return;
		handleLoadWithMmproj(model, mmprojFile);
	}

	async function handleLoadWithMmproj(model: LocalModel, mmprojFile: string) {
		loadModalModel = null;
		loadModalMmprojFile = '';
		loadingModels = new Set([...loadingModels, model.filename]);
		localError = '';
		localSuccess = '';
		try {
			const ct = localStorage.getItem('llamacpp_cache_type') || 'q8_0';
			await loadLocalModel(
				localStorage.token,
				model.filename,
				gpuLayers,
				contextSize,
				mmprojFile,
				ct
			);
			localSuccess = `${model.filename} carregado! (visão: ${mmprojFile})`;
			await refreshLocalModels();
			_models.set(await getModels(localStorage.token));
			await initAdmin();
		} catch (e: any) {
			localError = e.message || 'Erro ao carregar modelo';
		} finally {
			loadingModels = new Set([...loadingModels].filter((f) => f !== model.filename));
		}
	}

	async function handleUnload(model: LocalModel) {
		loadingModels = new Set([...loadingModels, model.filename]);
		localError = '';
		localSuccess = '';
		try {
			await unloadLocalModel(localStorage.token, model.id);
			localSuccess = `${model.filename} descarregado.`;
			await refreshLocalModels();
			_models.set(await getModels(localStorage.token));
			await initAdmin();
		} catch (e: any) {
			localError = e.message || 'Erro ao descarregar modelo';
		} finally {
			loadingModels = new Set([...loadingModels].filter((f) => f !== model.filename));
		}
	}

	// ─── ADMIN MODEL FUNCTIONS ───────────────────────────────────────────────
	const initAdmin = async () => {
		try {
			baseModels = [...$_models];
			try {
				const res = await getBaseModels(localStorage.token);
				workspaceModels = Array.isArray(res) ? res : [];
			} catch (e) {
				workspaceModels = [];
			}
			const baseIds = new Set(baseModels.map((m: any) => m.id));
			// Local GGUF IDs that currently exist on disk
			const localIds = new Set(localModels.map((gm) => gm.id).filter(Boolean));
			// Only include workspace models whose backing resource still exists:
			// either currently active in $_models, or a local GGUF file still on disk.
			const validIds = new Set([
				...baseIds,
				...workspaceModels
					.filter((wm: any) => baseIds.has(wm.id) || localIds.has(wm.id))
					.map((wm: any) => wm.id)
			]);
			let newAdminModels = [...validIds]
				.map((id: string) => {
					const base = baseModels.find((m: any) => m.id === id);
					const wm = workspaceModels.find((m: any) => m.id === id);
					if (base && wm) return { ...base, ...wm };
					if (wm) return { ...wm };
					if (base) return { ...base, is_active: true };
					return null;
				})
				.filter((m): m is any => m !== null);

			// Synthetic entries for GGUF files on disk not yet registered in the DB.
			// Without this, brand-new files show only the "Carregar" button and
			// never get the edit pencil, "..." menu, or toggle controls.
			const registeredIds = new Set(newAdminModels.map((m: any) => m.id));
			newAdminModels = [
				...newAdminModels,
				...localModels
					.filter((gm) => gm.id && !registeredIds.has(gm.id))
					.map((gm) => ({
						id: gm.id,
						name: gm.filename.replace(/\.gguf$/i, ''),
						meta: {},
						params: {},
						is_active: true,
					}))
			];
			adminModels = newAdminModels;
		} catch (e) {
			console.error('[UnifiedModels] initAdmin error:', e);
			if (adminModels.length === 0) adminModels = baseModels ?? [];
		}
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

	const hideModelHandler = async (model: any) => {
		model.meta = { ...model.meta, hidden: !(model?.meta?.hidden ?? false) };
		upsertModelHandler(model, false);
		toast.success(
			model.meta.hidden
				? $i18n.t('Model {{name}} is now hidden', { name: model.id })
				: $i18n.t('Model {{name}} is now visible', { name: model.id })
		);
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

	onMount(async () => {
		// refreshLocalModels must complete first so localModels is ready for initAdmin
		await refreshLocalModels();
		await initAdmin();

		// Auto-refresh: poll for new GGUF files every 3 seconds
		const pollInterval = setInterval(async () => {
			const prevIds = new Set(localModels.map((m) => m.id).filter(Boolean));
			await refreshLocalModels(false);
			const currIds = new Set(localModels.map((m) => m.id).filter(Boolean));
			// If models changed (added/removed), also refresh the global models store
			const changed = prevIds.size !== currIds.size ||
				[...prevIds].some((id) => !currIds.has(id)) ||
				[...currIds].some((id) => !prevIds.has(id));
			if (changed) {
				_models.set(await getModels(localStorage.token));
			}
			await initAdmin();
		}, 3000);

		const id = $page.url.searchParams.get('id') || $showSettingsModelId;
		if (id) {
			selectedModelId = id;
			showSettingsModelId.set('');
		}

		const onKeyDown = (e: KeyboardEvent) => {
			if (e.key === 'Shift') shiftKey = true;
		};
		const onKeyUp = (e: KeyboardEvent) => {
			if (e.key === 'Shift') shiftKey = false;
		};
		const onBlur = () => {
			shiftKey = false;
		};

		window.addEventListener('keydown', onKeyDown);
		window.addEventListener('keyup', onKeyUp);
		window.addEventListener('blur', onBlur);

		return () => {
			clearInterval(pollInterval);
			window.removeEventListener('keydown', onKeyDown);
			window.removeEventListener('keyup', onKeyUp);
			window.removeEventListener('blur', onBlur);
		};
	});
</script>

<!-- ─── Unified load modal ──────────────────────────────────────────────── -->
{#if loadModalModel}
	<div class="fixed inset-0 z-[10001] flex items-center justify-center bg-black/40" in:fade={{ duration: 80 }} out:fade={{ duration: 60 }}>
		<div class="bg-white dark:bg-gray-900 rounded-2xl p-5 shadow-xl mx-4 w-80 flex flex-col gap-3">

			{#if loadModalStep === 'context'}
				<p class="text-sm font-semibold text-gray-900 dark:text-white">Tamanho do Contexto</p>
				<div class="flex flex-col gap-1.5 max-h-72 overflow-y-auto scrollbar-none">
					{#each [2048, 4096, 8192, 16384, 32768, 65536] as sz}
						<button
							class="flex items-center justify-between px-3 py-2 rounded-lg text-xs text-left transition {contextModalSize === sz ? 'bg-black text-white dark:bg-white dark:text-black' : 'text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800'}"
							on:click={() => (contextModalSize = sz)}
						>
							<span>{sz.toLocaleString()} tokens</span>
							{#if sz === 8192}
								<span class="text-[10px] opacity-60">(padrão)</span>
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
<DownloadNeveModelsModal bind:show={showDownloadModal} />

{#if true}
	{#if selectedModelId === null}
		<div class="flex flex-col w-full max-h-[80vh]">

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
						<span>{$i18n.t('Baixar')}</span>
					</button>
					<button
						class="flex text-xs items-center gap-1 px-3 py-1.5 rounded-lg bg-black hover:bg-gray-900 text-white dark:bg-white dark:hover:bg-gray-100 dark:text-black transition font-medium"
						type="button"
						on:click={() => (showConfigModal = true)}
					>
						<span>{$i18n.t('Settings')}</span>
					</button>
				</div>
			</div>

			<!-- Scrollable list -->
			<div class="overflow-y-auto flex-1 min-h-0 px-3.5 pb-4">
				<div class="py-2 bg-white dark:bg-gray-900 rounded-3xl">

					<!-- Search bar -->
					<div class="px-3.5 flex flex-1 items-center w-full space-x-2 py-0.5 pb-2">
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

					<!-- ─── UNIFIED MODEL LIST ──────────────────────────────────── -->
					{#if localLoading && localModels.length === 0 && (adminModels?.length ?? 0) === 0}
						<div class="py-8"></div>
					{:else if mergedModels.length === 0}
						<div class="w-full flex flex-col justify-center items-center my-12 mb-20">
							<div class="max-w-md text-center">
								<div class="text-lg font-medium mb-1">{$i18n.t('No models found')}</div>
								<div class="text-gray-500 text-center text-xs">
									{$i18n.t('Try adjusting your search or filter to find what you are looking for.')}
								</div>
							</div>
						</div>
					{:else}
						{#each mergedModels.slice((currentPage - 1) * perPage, currentPage * perPage) as item (item.key)}
							{@const gm = item.gguf}
							{@const am = item.admin}
							{@const isProcessing = gm && loadingModels.has(gm.filename)}
							<div
								class="flex w-full px-3 py-0.5 {(am?.meta?.hidden || (am && !(am?.is_active ?? true))) ? 'opacity-50' : ''}"
								id={am ? `model-item-${am.id}` : undefined}
							>
								<div
								class="flex gap-3 w-full px-2 py-2 rounded-2xl transition cursor-pointer {gm?.is_loaded ? 'border border-gray-200 dark:border-gray-700 bg-gray-50/50 dark:bg-gray-800/30' : 'hover:bg-gray-50 dark:hover:bg-gray-850/50'}"
							on:click={(e) => {
								if (am && (am?.is_active ?? true) && !(e.target as HTMLElement).closest('button') && !(e.target as HTMLElement).closest('[data-melt-dropdown-menu]')) {
									selectedModelId = am.id;
								}
							}}
						>

									<!-- Avatar with pin-on-hover -->
									<div class="self-center flex-shrink-0 group/avatar relative">
										{#if am}
											<div class="w-9 h-9 rounded-full overflow-hidden {(am?.is_active ?? true) ? '' : 'opacity-50'}">
												<img
													src={`${WEBUI_API_BASE_URL}/models/model/profile/image?id=${am.id}`}
													alt="model"
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
											<!-- GGUF not yet loaded/registered -->
											<div class="size-9 rounded-full bg-gray-100 dark:bg-gray-800 flex items-center justify-center">
												<svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4 text-gray-400 dark:text-gray-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
													<path stroke-linecap="round" stroke-linejoin="round" d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />
												</svg>
											</div>
										{/if}
									</div>

									<!-- Info -->
									<div class="flex-1 min-w-0 self-center">
											<div class="w-full text-left">
											<div class="flex items-center gap-1.5 flex-wrap">
												<span class="font-medium text-sm line-clamp-1">
													{am?.name ?? gm?.filename?.replace('.gguf', '') ?? ''}
												</span>
											</div>
											<div class="text-xs text-gray-500 dark:text-gray-400 line-clamp-1 mt-0.5 flex items-center gap-2">
												{#if gm}
													<span>{gm.file_size_human}</span>
													{#if gm.is_loaded && gm.n_gpu_layers !== null}
														<span>GPU: {gm.n_gpu_layers === -1 ? 'Todas' : gm.n_gpu_layers} · CTX: {gm.n_ctx}{#if gm?.mmproj_filename}&nbsp;· Visão{/if}</span>
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

									<!-- Actions -->
									<div class="flex items-center gap-0.5 flex-shrink-0 self-center">
										<!-- GGUF load/unload controls -->
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
														class="flex items-center justify-center p-1.5 rounded-lg hover:bg-black/5 dark:hover:bg-white/5 transition text-gray-500 dark:text-gray-400"
														on:click={() => handleUnload(gm)}
													>
														<!-- Circle Stop -->
															<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" class="size-5">
															<path fill-rule="evenodd" d="M2.25 12c0-5.385 4.365-9.75 9.75-9.75s9.75 4.365 9.75 9.75-4.365 9.75-9.75 9.75S2.25 17.385 2.25 12Zm6-2.438c0-.724.588-1.312 1.313-1.312h4.874c.725 0 1.313.588 1.313 1.313v4.874c0 .725-.588 1.313-1.313 1.313H9.564a1.312 1.312 0 0 1-1.313-1.313V9.564Z" clip-rule="evenodd" />
														</svg>
													</button>
												</Tooltip>
											{:else}
												<Tooltip content="Carregar">
													<button
														class="flex items-center justify-center p-1.5 rounded-lg hover:bg-black/5 dark:hover:bg-white/5 transition text-gray-500 dark:text-gray-400"
														on:click={() => startLoadWithContextModal(gm)}
													>
														<!-- Circle Play -->
															<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" class="size-5">
															<path fill-rule="evenodd" d="M2.25 12c0-5.385 4.365-9.75 9.75-9.75s9.75 4.365 9.75 9.75-4.365 9.75-9.75 9.75S2.25 17.385 2.25 12Zm14.024-.983a1.125 1.125 0 0 1 0 1.966l-5.603 3.113A1.125 1.125 0 0 1 9 15.113V8.887c0-.857.921-1.4 1.671-.983l5.603 3.113Z" clip-rule="evenodd" />
														</svg>
													</button>
												</Tooltip>
											{/if}
										{/if}



									<!-- separator entre controles GGUF e admin -->
									{#if gm && am}<div class="w-2 flex-shrink-0"></div>{/if}
										<!-- Admin controls (only if model is registered in the system) -->
										{#if am}
											{#if shiftKey}
												<Tooltip content={am?.meta?.hidden ? $i18n.t('Show') : $i18n.t('Hide')}>
													<button
														class="self-center w-fit text-sm px-2 py-2 dark:text-gray-300 dark:hover:text-white hover:bg-black/5 dark:hover:bg-white/5 rounded-xl"
														type="button"
														on:click={() => hideModelHandler(am)}
													>
														{#if am?.meta?.hidden}
															<EyeSlash />
														{:else}
															<Eye />
														{/if}
													</button>
												</Tooltip>
											{:else}
												{#if !(gm && (gm.is_loaded || isProcessing))}
													<div class="ml-1">
														<Tooltip content={(am?.is_active ?? true) ? $i18n.t('Enabled') : $i18n.t('Disabled')}>
															<button
																type="button"
																class="flex h-[1.125rem] min-h-[1.125rem] w-8 shrink-0 cursor-pointer items-center rounded-full px-[2px] mx-[1px] transition-colors outline outline-1 outline-gray-100 dark:outline-gray-800 {(am?.is_active ?? true) ? 'bg-emerald-500 dark:bg-emerald-700' : 'bg-gray-200 dark:bg-transparent'}"
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
										{/if}

									</div>
								</div>
							</div>
						{/each}
					{/if}

					{#if mergedModels.length > perPage}
						<Pagination bind:page={currentPage} count={mergedModels.length} {perPage} />
					{/if}

				</div>
			</div>
		</div>

	{:else}
		<!-- ─── Model Editor ──────────────────────────────────────────────── -->
		<div style="height: 55vh; min-height: 0; width: 100%; display: flex; flex-direction: column; overflow: hidden;">
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
