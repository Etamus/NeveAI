<script lang="ts">
	import { onMount } from 'svelte';
	import { config, settings, models as globalModels, showLocalModelsModal } from '$lib/stores';
	import Modal from '$lib/components/common/Modal.svelte';
	import UnifiedModels from '$lib/components/chat/UnifiedModels.svelte';
	import { getLocalModels, getMmProjFiles, getLocalVramInfo, type LocalVramInfo } from '$lib/apis/llamacpp';
	import { getBaseModels } from '$lib/apis/models';
	import { getModels } from '$lib/apis';
	import { NEVEAI_API_BASE_URL } from '$lib/constants';
	import {
		buildUnifiedAdminModels,
		type UnifiedModelsPreload
	} from '$lib/utils/unifiedModelsData';

	let unifiedModelsPreload: UnifiedModelsPreload | null = null;
	let unifiedModelsPreloadPromise: Promise<void> | null = null;
	let unifiedModelsVramInfo: LocalVramInfo | null = null;
	let unifiedModelsVramPromise: Promise<void> | null = null;
	let unifiedModels: UnifiedModels | null = null;
	let unifiedModelMobileStep = '';
	const unifiedModelsVramCacheKey = 'neveai.unifiedModels.vramInfo';
	const unifiedModelsPreloadCacheKey = 'neveai.unifiedModels.preload';

	const getCachedUnifiedModelsVram = () => {
		if (typeof localStorage === 'undefined') return null;
		try {
			const cached = JSON.parse(localStorage.getItem(unifiedModelsVramCacheKey) ?? 'null');
			if (!cached?.data || !cached?.timestamp) return null;
			if (Date.now() - cached.timestamp > 5 * 60 * 1000) return null;
			return cached.data as LocalVramInfo;
		} catch {
			return null;
		}
	};

	const setCachedUnifiedModelsVram = (data: LocalVramInfo) => {
		if (typeof localStorage === 'undefined') return;
		try {
			localStorage.setItem(
				unifiedModelsVramCacheKey,
				JSON.stringify({ timestamp: Date.now(), data })
			);
		} catch {}
	};

	const getCachedUnifiedModelsPreload = () => {
		if (typeof localStorage === 'undefined') return null;
		try {
			const cached = JSON.parse(localStorage.getItem(unifiedModelsPreloadCacheKey) ?? 'null');
			if (!cached?.data || !cached?.timestamp) return null;
			if (Date.now() - cached.timestamp > 5 * 60 * 1000) return null;
			// Persisted catalog data is useful, but cannot confirm a running model.
			return { ...cached.data, loaded: false } as UnifiedModelsPreload;
		} catch {
			return null;
		}
	};

	const setCachedUnifiedModelsPreload = (data: UnifiedModelsPreload) => {
		if (typeof localStorage === 'undefined') return;
		try {
			localStorage.setItem(
				unifiedModelsPreloadCacheKey,
				JSON.stringify({ timestamp: Date.now(), data })
			);
		} catch {}
	};
	const acceptUnifiedCatalog = (event: CustomEvent) => {
		if (!unifiedModelsPreload || (event.detail.catalogUpdatedAt ?? 0) < (unifiedModelsPreload.catalogUpdatedAt ?? 0)) return;
		unifiedModelsPreload = { ...unifiedModelsPreload, ...event.detail };
		setCachedUnifiedModelsPreload(unifiedModelsPreload);
	};

	const getModelImageVersion = (model: any) =>
		model?.updated_at ?? model?.info?.updated_at ?? model?.meta?.updated_at ?? '';
	const getModelProfileImageUrl = (model: any) => {
		const params = new URLSearchParams({ id: model?.id ?? '' });
		const version = getModelImageVersion(model);
		if (version) params.set('v', `${version}`);
		return `${NEVEAI_API_BASE_URL}/models/model/profile/image?${params.toString()}`;
	};

	const preloadUnifiedModelImages = (adminModels: any[]) => {
		if (typeof Image === 'undefined') return;
		const urls = [...new Set(adminModels.filter((model) => model?.id).map(getModelProfileImageUrl))].slice(
			0,
			80
		);
		for (const url of urls) {
			const image = new Image();
			image.decoding = 'async';
			image.src = url;
		}
	};

	const refreshUnifiedModelsVram = async () => {
		if (unifiedModelsVramPromise) return unifiedModelsVramPromise;

		unifiedModelsVramPromise = getLocalVramInfo(localStorage.token)
			.then((result) => {
				unifiedModelsVramInfo = result;
				setCachedUnifiedModelsVram(result);
				if (unifiedModelsPreload?.loaded) {
					unifiedModelsPreload = { ...unifiedModelsPreload, vramInfo: result };
				}
			})
			.catch(() => {})
			.finally(() => {
				unifiedModelsVramPromise = null;
			});

		return unifiedModelsVramPromise;
	};

	const refreshUnifiedModelsPreload = async () => {
		if (unifiedModelsPreloadPromise) return unifiedModelsPreloadPromise;
		if (!unifiedModelsPreload) {
			unifiedModelsPreload = getCachedUnifiedModelsPreload();
		}
		if (!unifiedModelsVramInfo) unifiedModelsVramInfo = getCachedUnifiedModelsVram();
		refreshUnifiedModelsVram();

		unifiedModelsPreloadPromise = (async () => {
			const runtimeUpdatedAt = Date.now();
			const catalogUpdatedAt = Date.now();
			const localModelsPromise = getLocalModels(localStorage.token).catch(() => []);
			const mmProjFilesPromise = getMmProjFiles(localStorage.token).catch(() => []);
			const workspaceModelsPromise = getBaseModels(localStorage.token).catch(() => null);
			const baseModelsPromise = $globalModels?.length
				? Promise.resolve([...$globalModels])
				: getModels(
						localStorage.token,
						$config?.features?.enable_direct_connections && ($settings?.directConnections ?? null)
					).catch(() => null);

			const [localModels, mmProjFiles] = await Promise.all([
				localModelsPromise,
				mmProjFilesPromise
			]);
			const currentWorkspaceModels = unifiedModelsPreload?.workspaceModels ?? [];
			const currentBaseModels = $globalModels?.length
				? [...$globalModels]
				: (unifiedModelsPreload?.baseModels ?? []);
			const currentAdminModels = buildUnifiedAdminModels(
				localModels,
				currentBaseModels,
				currentWorkspaceModels
			);
			preloadUnifiedModelImages(currentAdminModels);
			unifiedModelsPreload = {
				loaded: true,
				runtimeUpdatedAt,
				catalogUpdatedAt: unifiedModelsPreload?.catalogUpdatedAt ?? 0,
				localModels,
				mmProjFiles,
				workspaceModels: currentWorkspaceModels,
				baseModels: currentBaseModels,
				adminModels: currentAdminModels,
				vramInfo: unifiedModelsVramInfo
			};
			setCachedUnifiedModelsPreload(unifiedModelsPreload);

			const [workspaceModelsResult, baseModels] = await Promise.all([
				workspaceModelsPromise,
				baseModelsPromise
			]);

			const workspaceModels = Array.isArray(workspaceModelsResult) ? workspaceModelsResult : (unifiedModelsPreload?.workspaceModels ?? []);
			const resolvedBaseModels = Array.isArray(baseModels) ? baseModels : (unifiedModelsPreload?.baseModels ?? []);
			const adminModels = buildUnifiedAdminModels(localModels, resolvedBaseModels, workspaceModels);
			preloadUnifiedModelImages(adminModels);

			unifiedModelsPreload = {
				loaded: true,
				runtimeUpdatedAt,
				localModels,
				mmProjFiles,
				...((unifiedModelsPreload?.catalogUpdatedAt ?? 0) >= catalogUpdatedAt
					? { catalogUpdatedAt: unifiedModelsPreload.catalogUpdatedAt, workspaceModels: unifiedModelsPreload.workspaceModels, baseModels: unifiedModelsPreload.baseModels, adminModels: unifiedModelsPreload.adminModels }
					: { catalogUpdatedAt: Array.isArray(workspaceModelsResult) ? catalogUpdatedAt : (unifiedModelsPreload?.catalogUpdatedAt ?? 0), workspaceModels, baseModels: resolvedBaseModels, adminModels }),
				vramInfo: unifiedModelsVramInfo
			};
			setCachedUnifiedModelsPreload(unifiedModelsPreload);
		})().finally(() => {
			unifiedModelsPreloadPromise = null;
		});

		return unifiedModelsPreloadPromise;
	};

	$: if ($showLocalModelsModal) {
		refreshUnifiedModelsPreload();
		refreshUnifiedModelsVram();
	}

	onMount(() => {
		unifiedModelsVramInfo = getCachedUnifiedModelsVram();
		unifiedModelsPreload = getCachedUnifiedModelsPreload();
		refreshUnifiedModelsPreload();
		refreshUnifiedModelsVram();
	});
</script>

{#if unifiedModelsPreload?.loaded}
	<Modal
		size={unifiedModelMobileStep && unifiedModelMobileStep !== 'downloads' ? 'w-[40rem]' : 'w-[44rem]'}
		mobileFullscreen
		mobileStep={unifiedModelMobileStep}
		onMobileStepBack={() => unifiedModels?.handleOutsideClick()}
		className="bg-white dark:bg-gray-900 rounded-xl"
		bind:show={$showLocalModelsModal}
		keepMounted
		onOutsideClick={() => unifiedModels?.handleOutsideClick() ?? false}
	>
		<UnifiedModels bind:this={unifiedModels} bind:mobileStep={unifiedModelMobileStep} preload={unifiedModelsPreload} show={$showLocalModelsModal} on:catalogChange={acceptUnifiedCatalog} />
	</Modal>
{/if}


