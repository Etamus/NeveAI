<script lang="ts">
	import { getContext, onDestroy } from 'svelte';
	import { toast } from 'svelte-sonner';

	import Modal from '$lib/components/common/Modal.svelte';
	import XMark from '$lib/components/icons/XMark.svelte';
	import Spinner from '$lib/components/common/Spinner.svelte';
	import { WEBUI_BASE_URL } from '$lib/constants';

	import {
		getNeveCatalog,
		startNeveDownload,
		streamNeveDownload,
		type NeveCatalogModel
	} from '$lib/apis/llamacpp';

	const i18n = getContext('i18n');

	export let show = false;

	let loading = false;
	let catalog: NeveCatalogModel[] = [];
	let selectedId: string | null = null;

	let downloading = false;
	let progress = 0;
	let progressLabel = '';
	let currentEs: EventSource | null = null;

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

	$: if (show) {
		loadCatalog();
		selectedId = null;
		downloading = false;
		progress = 0;
		progressLabel = '';
	}

	const handleDownload = async () => {
		if (!selectedId || downloading) return;
		const entry = catalog.find((m) => m.id === selectedId);
		if (!entry) return;
		downloading = true;
		progress = 0;
		progressLabel = 'Conectando...';
		try {
			const taskId = await startNeveDownload(localStorage.token, selectedId);
			currentEs = streamNeveDownload(
				taskId,
				(state) => {
					const p = typeof state.progress === 'number' ? state.progress : 0;
					progress = p;
					if (state.status === 'resolving') {
						progressLabel = 'Procurando arquivos...';
					} else if (state.status === 'downloading') {
						const fileLabel = state.file_total > 1 ? ` (${state.file_index}/${state.file_total})` : '';
						const sz = state.total ? `${fmtBytes(state.downloaded)} / ${fmtBytes(state.total)}` : '';
						progressLabel = `Baixando${fileLabel} ${sz}`.trim();
					} else if (state.status === 'queued') {
						progressLabel = 'Na fila...';
					}
				},
				(state) => {
					downloading = false;
					if (state.message === 'Já instalado') {
						toast.info(`${entry.name}: já instalado`);
					} else {
						toast.success(`${entry.name} baixado com sucesso`);
					}
					loadCatalog();
				},
				(err: any) => {
					downloading = false;
					toast.error(err?.message || 'Falha no download');
				}
			);
		} catch (e: any) {
			downloading = false;
			toast.error(e?.message || 'Falha ao iniciar download');
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
				{#each catalog as item (item.id)}
					<label
						class="relative flex items-center gap-3 px-3 py-2 rounded-lg transition border {item.installed
							? 'opacity-60 cursor-default border-transparent'
							: selectedId === item.id
							? 'cursor-pointer border-gray-300 dark:border-gray-600 bg-gray-50 dark:bg-gray-850'
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
							src="{WEBUI_BASE_URL}/static/favicon.png"
							alt=""
							class="size-5 rounded-full object-cover shrink-0"
						/>
						<div class="flex-1 min-w-0 text-sm truncate">{item.name}</div>
						{#if item.installed}
							<span class="text-xs font-medium text-green-600 dark:text-green-500 shrink-0">Instalado</span>
						{:else if item.size_label}
							<span class="text-xs text-gray-400 dark:text-gray-500 shrink-0">{item.size_label}</span>
						{/if}
					</label>
				{/each}
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

			<div class="flex justify-end pt-4">
				<button
					class="px-4 py-1.5 text-xs font-medium bg-black text-white dark:bg-white dark:text-black hover:opacity-90 transition rounded-lg disabled:opacity-40 flex items-center gap-2"
					disabled={!selectedId || downloading}
					on:click={handleDownload}
				>
					{#if downloading}
						<Spinner className="size-3" />
					{/if}
					{$i18n.t('Baixar')}
				</button>
			</div>
		</div>
	</div>
</Modal>
