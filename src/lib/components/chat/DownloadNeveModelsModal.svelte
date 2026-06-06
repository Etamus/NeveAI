<script lang="ts">
	import { getContext, onDestroy } from 'svelte';
	import { toast } from 'svelte-sonner';

	import Modal from '$lib/components/common/Modal.svelte';
	import XMark from '$lib/components/icons/XMark.svelte';
	import Spinner from '$lib/components/common/Spinner.svelte';
	import { NEVEAI_BASE_URL } from '$lib/constants';

	import {
		cancelNeveDownload,
		getActiveNeveDownload,
		getNeveCatalog,
		startNeveDownload,
		streamNeveDownload,
		type NeveCatalogModel,
		type NeveDownloadState
	} from '$lib/apis/llamacpp';

	const i18n = getContext('i18n');

	export let show = false;

	let loading = false;
	let catalog: NeveCatalogModel[] = [];
	let selectedId: string | null = null;
	let wasShown = false;

	let downloading = false;
	let cancelling = false;
	let progress = 0;
	let progressLabel = '';
	let currentTaskId: string | null = null;
	let downloadingModelId: string | null = null;
	let downloadingModelName = '';
	let currentEs: EventSource | null = null;

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
			catalog = await getNeveCatalog(localStorage.token);
		} catch (e: any) {
			toast.error(e?.message || 'Falha ao carregar catálogo');
			catalog = [];
		}
	};

	const modelNameFor = (modelId?: string | null) => {
		return catalog.find((model) => model.id === modelId)?.name || downloadingModelName || 'Modelo';
	};

	const applyDownloadState = (state: NeveDownloadState) => {
		if (state.task_id) {
			currentTaskId = state.task_id;
		}
		if (state.model_id) {
			downloadingModelId = state.model_id;
			selectedId = state.model_id;
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
			progressLabel = `Baixando${fileLabel} ${sz}`.trim();
		} else if (state.status === 'queued') {
			progressLabel = 'Na fila...';
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

	const clearDownloadState = (keepSelectedId: string | null = null) => {
		downloading = false;
		cancelling = false;
		progress = 0;
		progressLabel = '';
		currentTaskId = null;
		downloadingModelId = null;
		downloadingModelName = '';
		selectedId = keepSelectedId;
		currentEs = null;
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
				const name = modelNameFor(state.model_id ?? downloadingModelId);
				clearDownloadState(null);
				if (state.message === 'Já instalado') {
					toast.info(`${name}: já instalado`);
				} else {
					toast.success(`${name} baixado com sucesso`);
				}
				await loadCatalog();
			},
			(err: any) => {
				const retryId = downloadingModelId;
				clearDownloadState(retryId);
				toast.error(err?.message || 'Falha no download');
			},
			async (state) => {
				const retryId = state.model_id ?? downloadingModelId;
				const name = modelNameFor(retryId);
				clearDownloadState(retryId ?? null);
				toast.info(`${name}: download cancelado e arquivos parciais removidos`);
				await loadCatalog();
			}
		);
	};

	const hydrateModal = async () => {
		loading = true;
		const [catalogResult, activeResult] = await Promise.allSettled([
			getNeveCatalog(localStorage.token),
			getActiveNeveDownload(localStorage.token)
		]);

		if (catalogResult.status === 'fulfilled') {
			catalog = catalogResult.value;
		} else {
			toast.error(catalogResult.reason?.message || 'Falha ao carregar catálogo');
			catalog = [];
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

	$: if (show && !wasShown) {
		wasShown = true;
		void hydrateModal();
	} else if (!show && wasShown) {
		wasShown = false;
	}

	const handleDownload = async () => {
		if (!selectedId || downloading) return;
		const entry = catalog.find((m) => m.id === selectedId);
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
					toast.info('Já existe um download de modelo em andamento');
				}
				return;
			}

			const taskId = await startNeveDownload(localStorage.token, selectedId);
			attachToDownload(taskId, {
				task_id: taskId,
				model_id: entry.id,
				name: entry.name,
				status: 'queued',
				progress: 0
			});
		} catch (e: any) {
			clearDownloadState(selectedId);
			toast.error(e?.message || 'Falha ao iniciar download');
		}
	};

	const handleCancelDownload = async () => {
		if (!currentTaskId || !downloading || cancelling) return;

		cancelling = true;
		progressLabel = 'Cancelando e limpando arquivos...';
		try {
			const state = await cancelNeveDownload(localStorage.token, currentTaskId);
			applyDownloadState(state);
			if (state.status === 'cancelled') {
				const retryId = state.model_id ?? downloadingModelId;
				clearDownloadState(retryId ?? null);
				await loadCatalog();
			}
		} catch (e: any) {
			cancelling = false;
			toast.error(e?.message || 'Falha ao cancelar download');
		}
	};

	onDestroy(() => {
		if (currentEs) {
			currentEs.close();
			currentEs = null;
		}
	});
</script>

<Modal bind:show size="w-[22rem]">
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
			<div class="flex flex-col gap-1 max-h-[22rem] overflow-y-auto pr-1">
				{#if loading && catalog.length === 0}
					<div class="flex justify-center py-8">
						<Spinner className="size-5" />
					</div>
				{:else if catalog.length === 0}
					<div class="text-center text-xs text-gray-500 dark:text-gray-400 py-8">
						{$i18n.t('Nenhum modelo disponível')}
					</div>
				{:else}
					{#each catalog as item (item.id)}
					<label
						class="relative flex items-center gap-3 px-3 py-2 rounded-lg transition border {item.installed
							? 'opacity-60 cursor-default border-transparent'
							: selectedId === item.id
							? `${downloading ? 'cursor-default' : 'cursor-pointer'} border-gray-300 dark:border-gray-600 bg-gray-50 dark:bg-gray-850`
							: 'cursor-pointer border-transparent hover:bg-gray-50 dark:hover:bg-gray-850/50'}"
					>
						<input
							type="radio"
							name="neve-model"
							class="sr-only"
							value={item.id}
							bind:group={selectedId}
							disabled={downloading || item.installed}
						/>
						<img
							src="{NEVEAI_BASE_URL}/static/favicon.png"
							alt=""
							class="size-5 rounded-full object-cover shrink-0"
						/>
						<div class="flex-1 min-w-0 text-sm truncate">{item.name}</div>
						{#if item.installed}
							<span class="text-xs font-medium text-black-600 dark:text-white-500 shrink-0">Instalado</span>
						{:else if downloading && downloadingModelId === item.id}
							<span class="text-xs font-medium text-black-600 dark:text-white-400 shrink-0">Baixando</span>
						{:else if item.size_label}
							<span class="text-xs text-gray-400 dark:text-gray-500 shrink-0">{item.size_label}</span>
						{/if}
					</label>
					{/each}
				{/if}
			</div>

			{#if downloading}
				<div class="mt-4">
					<div class="flex justify-between text-xs text-gray-500 dark:text-gray-400 mb-1">
						<span>{progressLabel}</span>
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

			<div class="flex justify-end gap-2 pt-4">
				{#if downloading}
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
					<button
						class="px-4 py-1.5 text-xs font-medium bg-black text-white dark:bg-white dark:text-black hover:opacity-90 transition rounded-lg disabled:opacity-40 flex items-center gap-2"
						disabled={!selectedId || loading}
						on:click={handleDownload}
					>
						{$i18n.t('Baixar')}
					</button>
				{/if}
			</div>
		</div>
	</div>
</Modal>
