<script lang="ts">
	import { onMount } from 'svelte';
	import { getModels } from '$lib/apis';
	import { models } from '$lib/stores';
	import {
		getLocalModels,
		getMmProjFiles,
		loadLocalModel,
		unloadLocalModel,
		type LocalModel
	} from '$lib/apis/llamacpp';
	import { findMatchingMmproj } from '$lib/utils/mmproj';

	let localModels: LocalModel[] = [];
	let mmProjFiles: string[] = [];
	let loading = false;
	let loadingModels: Set<string> = new Set();
	let errorMessage = '';
	let successMessage = '';

	// Per-model mmproj confirmation flow
	let confirmVisionCallback: { onNo: () => void; onYes: () => void } | null = null;

	// Load settings
	let gpuLayers: number = -1;
	let contextSize: number = 8192;
	let cacheType: string = localStorage.getItem('llamacpp_cache_type') || 'q8_0';

	// Context size modal
	let contextModalModel: LocalModel | null = null;
	let contextModalSize: number = 8192;

	async function refreshModels() {
		loading = true;
		errorMessage = '';
		try {
			[localModels, mmProjFiles] = await Promise.all([
				getLocalModels(localStorage.token),
				getMmProjFiles(localStorage.token)
			]);
		} catch (e: any) {
			errorMessage = e.message === 'Failed to fetch' ? 'Falha ao buscar' : (e.message || 'Erro ao buscar modelos');
		} finally {
			loading = false;
		}
	}

	async function handleLoad(model: LocalModel) {
		loadingModels = new Set([...loadingModels, model.filename]);
		errorMessage = '';
		successMessage = '';
		try {
			const ct = localStorage.getItem('llamacpp_cache_type') || 'q8_0';
			await loadLocalModel(localStorage.token, model.filename, gpuLayers, contextSize, '', ct);
			successMessage = `${model.filename} carregado com sucesso!`;
			await refreshModels();
			// Refresh global models list so it appears in chat
			models.set(await getModels(localStorage.token));
		} catch (e: any) {
			errorMessage = e.message || 'Erro ao carregar modelo';
		} finally {
			loadingModels = new Set([...loadingModels].filter((f) => f !== model.filename));
		}
	}

	function startLoadWithContextModal(model: LocalModel) {
		contextModalModel = model;
		contextModalSize = 8192;

	}

	function confirmContextAndProceed() {
		const model = contextModalModel;
		if (!model) return;
		contextSize = contextModalSize;
		contextModalModel = null;
		const matchingMmproj = findMatchingMmproj(model.filename, mmProjFiles);
		if (matchingMmproj) {
			confirmVisionCallback = {
				onNo: () => handleLoad(model),
				onYes: () => handleLoadWithMmproj(model, matchingMmproj)
			};
		} else {
			handleLoad(model);
		}
	}

	function openVisionSelector(model: LocalModel) {
		const matchingMmproj = findMatchingMmproj(model.filename, mmProjFiles);
		if (matchingMmproj) {
			confirmVisionCallback = {
				onNo: () => {},
				onYes: () => handleLoadWithMmproj(model, matchingMmproj)
			};
		}
	}

	async function handleLoadWithMmproj(model: LocalModel, mmprojFile: string) {
		loadingModels = new Set([...loadingModels, model.filename]);
		errorMessage = '';
		successMessage = '';
		try {
			const ct = localStorage.getItem('llamacpp_cache_type') || 'q8_0';
			await loadLocalModel(localStorage.token, model.filename, gpuLayers, contextSize, mmprojFile, ct);
			successMessage = `${model.filename} carregado com sucesso! (visão: ${mmprojFile})`;
			await refreshModels();
			models.set(await getModels(localStorage.token));
		} catch (e: any) {
			errorMessage = e.message || 'Erro ao carregar modelo';
		} finally {
			loadingModels = new Set([...loadingModels].filter((f) => f !== model.filename));
		}
	}

	async function handleUnload(model: LocalModel) {
		loadingModels = new Set([...loadingModels, model.filename]);
		errorMessage = '';
		successMessage = '';
		try {
			await unloadLocalModel(localStorage.token, model.id);
			successMessage = `${model.filename} descarregado.`;
			await refreshModels();
			// Refresh global models list
			models.set(await getModels(localStorage.token));
		} catch (e: any) {
			errorMessage = e.message || 'Erro ao descarregar modelo';
		} finally {
			loadingModels = new Set([...loadingModels].filter((f) => f !== model.filename));
		}
	}

	onMount(() => {
		refreshModels();
	});
</script>

<div class="flex flex-col w-full max-h-[80vh] relative">
	<!-- Vision confirmation dialog -->
	{#if confirmVisionCallback}
		<div class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
			<div class="bg-white dark:bg-gray-900 rounded-2xl p-5 shadow-xl mx-4 w-72 flex flex-col gap-3">
				<div class="flex items-center gap-2">
					<div class="size-8 rounded-xl bg-violet-100 dark:bg-violet-900/30 flex items-center justify-center flex-shrink-0">
						<svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4 text-violet-600 dark:text-violet-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
							<path stroke-linecap="round" stroke-linejoin="round" d="M15 10l4.553-2.069A1 1 0 0121 8.87V15.13a1 1 0 01-1.447.899L15 14M3 8h12v8H3z" />
						</svg>
					</div>
					<p class="text-sm font-semibold text-gray-900 dark:text-white">Deseja carregar a visão?</p>
				</div>
				<p class="text-xs text-gray-500 dark:text-gray-400">O modelo será carregado com suporte a análise de imagens.</p>
				<div class="flex justify-end gap-2 mt-1">
					<button
						class="px-4 py-1.5 text-xs rounded-xl bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 transition font-medium"
						on:click={() => { const cb = confirmVisionCallback; confirmVisionCallback = null; cb?.onNo(); }}
					>Não</button>
					<button
						class="px-4 py-1.5 text-xs rounded-xl bg-black text-white dark:bg-white dark:text-black hover:opacity-90 transition font-medium"
						on:click={() => { const cb = confirmVisionCallback; confirmVisionCallback = null; cb?.onYes(); }}
					>Sim</button>
				</div>
			</div>
		</div>
	{/if}

	<!-- Context size modal -->
	{#if contextModalModel}
		<div class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
			<div class="bg-white dark:bg-gray-900 rounded-2xl p-5 shadow-xl mx-4 w-80 flex flex-col gap-3">
				<div class="flex items-center gap-2">
					<div class="size-8 rounded-xl bg-blue-100 dark:bg-blue-900/30 flex items-center justify-center flex-shrink-0">
						<svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4 text-blue-600 dark:text-blue-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
							<path stroke-linecap="round" stroke-linejoin="round" d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4" />
						</svg>
					</div>
					<p class="text-sm font-semibold text-gray-900 dark:text-white">Tamanho do Contexto</p>
				</div>
				<p class="text-xs text-gray-500 dark:text-gray-400">Selecione o tamanho do contexto em tokens para <span class="font-medium text-gray-700 dark:text-gray-300">{contextModalModel.filename.replace('.gguf', '')}</span></p>
				<div class="flex flex-col gap-1.5 max-h-80 overflow-y-auto scrollbar-none">
					{#each [2048, 4096, 8192, 16384, 32768, 65536] as size}
						<button
							class="flex items-center justify-between px-3 py-2 rounded-xl text-xs text-left transition {contextModalSize === size ? 'bg-black text-white dark:bg-white dark:text-black font-medium' : 'text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800'}"
							on:click={() => (contextModalSize = size)}
						>
							<span>{size.toLocaleString()} tokens</span>
							{#if size === 8192}
								<span class="text-[10px] opacity-60">(padrão)</span>
							{/if}
						</button>
					{/each}
				</div>


				<div class="flex justify-end gap-2 mt-1">
					<button
						class="px-4 py-1.5 text-xs rounded-xl bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 transition font-medium"
						on:click={() => (contextModalModel = null)}
					>Cancelar</button>
					<button
						class="px-4 py-1.5 text-xs rounded-xl bg-black text-white dark:bg-white dark:text-black hover:opacity-90 transition font-medium"
						on:click={confirmContextAndProceed}
					>Confirmar</button>
				</div>
			</div>
		</div>
	{/if}

	<!-- Header -->
	<div class="flex items-center justify-between px-4 pt-4 pb-3 shrink-0">
		<div class="flex items-center gap-2 text-xl font-medium px-0.5">
			<span>Modelos Locais</span>
			<span class="text-lg font-medium text-gray-500 dark:text-gray-500">{localModels.length}</span>
		</div>
		<button
			class="flex text-xs items-center gap-1.5 px-3 py-1.5 rounded-xl bg-gray-50 hover:bg-gray-100 dark:bg-gray-850 dark:hover:bg-gray-800 dark:text-gray-200 transition"
			on:click={refreshModels}
			disabled={loading}
		>
			{#if loading}
			<svg class="w-3.5 h-3.5 animate-spin" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
				<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
				<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
			</svg>
		{:else}
			<svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
				<path stroke-linecap="round" stroke-linejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
			</svg>
		{/if}
		<span class="font-medium">Atualizar</span>
		</button>
	</div>

	<!-- Status Messages -->
	<div class="mx-3.5 mb-2 shrink-0">
		<div class="flex flex-col gap-2">
			{#if successMessage}
				<div class="flex items-center gap-1.5 text-xs text-gray-500 dark:text-gray-400">
					<svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5 flex-shrink-0 text-green-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.5">
						<path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7" />
					</svg>
					{successMessage}
				</div>
			{/if}
		</div>
	</div>

	<!-- Status Messages (errors) -->
	{#if errorMessage}
		<div class="mx-3.5 mb-2 px-3.5 py-2.5 rounded-xl border border-red-200 dark:border-red-800/50 bg-red-50 dark:bg-red-950/30 text-red-700 dark:text-red-400 text-xs flex items-center gap-2 shrink-0">
			<svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
				<path stroke-linecap="round" stroke-linejoin="round" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
			</svg>
			{errorMessage}
		</div>
	{/if}

	<!-- Models List -->
	<div class="flex-1 overflow-y-auto px-3.5 pb-4 min-h-0">
		{#if loading && localModels.length === 0}
			<div class="flex flex-col items-center justify-center py-16 text-gray-400">
				<svg class="w-8 h-8 animate-spin mb-3" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
					<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
					<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
				</svg>
				<span class="text-sm">Buscando modelos...</span>
			</div>
		{:else if localModels.length === 0}
			<div class="flex flex-col items-center justify-center py-16 text-center">
				<div class="text-gray-300 dark:text-gray-600 mb-3">
					<svg xmlns="http://www.w3.org/2000/svg" class="w-12 h-12" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1">
						<path stroke-linecap="round" stroke-linejoin="round" d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />
					</svg>
				</div>
				<p class="text-sm font-medium text-gray-600 dark:text-gray-400 mb-1">Nenhum modelo encontrado</p>
				<p class="text-xs text-gray-400 dark:text-gray-500">
					Coloque arquivos <span class="font-mono">.gguf</span> em
					<span class="font-mono">Neve/models/</span>
				</p>
			</div>
		{:else}
			<div
				class="py-2 bg-white dark:bg-gray-900 rounded-3xl border border-gray-100/30 dark:border-gray-850/30"
			>
				{#each localModels as model (model.id)}
					<div class="flex transition w-full p-2.5 hover:bg-gray-50 dark:hover:bg-gray-850/50 rounded-2xl">
						<div class="flex gap-3.5 w-full">
							<!-- Icon -->
							<div class="self-center pl-0.5 flex-shrink-0">
								<div class="size-10 rounded-xl bg-gray-100 dark:bg-gray-800 flex items-center justify-center">
									{#if model.is_loaded}
										<svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5 text-gray-600 dark:text-gray-300" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
											<path stroke-linecap="round" stroke-linejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
										</svg>
									{:else}
										<svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5 text-gray-400 dark:text-gray-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
											<path stroke-linecap="round" stroke-linejoin="round" d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />
										</svg>
									{/if}
								</div>
							</div>

							<!-- Info + Actions -->
							<div class="shrink-0 flex w-full min-w-0 flex-1 pr-1 self-center">
								<div class="flex h-full w-full flex-1 flex-col justify-start self-center">
									<div class="flex items-center justify-between w-full">
										<div class="flex items-center gap-2 min-w-0">
											<span class="font-medium text-sm line-clamp-1 dark:text-white">
												{model.filename.replace('.gguf', '')}
											</span>
											{#if model.is_loaded}
												<span class="text-[10px] text-gray-500 dark:text-gray-400 shrink-0">● Ativo</span>
											{/if}
											{#if model.is_loaded && model.mmproj_filename}
												<span class="text-[10px] px-1.5 py-0.5 rounded-full bg-violet-100 text-violet-700 dark:bg-violet-900/30 dark:text-violet-400 font-medium shrink-0">Visão</span>
											{/if}
										</div>

										<!-- Actions -->
										<div class="flex items-center gap-1.5 flex-shrink-0 mt-1">
											{#if loadingModels.has(model.filename)}
												<div class="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs text-gray-500">
													<svg class="w-3.5 h-3.5 animate-spin" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
														<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
														<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
													</svg>
													Processando...
												</div>
											{:else if model.is_loaded}

												{#if findMatchingMmproj(model.filename, mmProjFiles)}
													<button
														class="flex items-center gap-1 px-2.5 py-1.5 text-xs rounded-xl bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 transition text-gray-600 dark:text-gray-400"
														on:click={() => openVisionSelector(model)}
													>
														<svg xmlns="http://www.w3.org/2000/svg" class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
<path stroke-linecap="round" stroke-linejoin="round" d="M15 10l4.553-2.069A1 1 0 0121 8.87V15.13a1 1 0 01-1.447.899L15 14M3 8h12v8H3z" />
														</svg>
														{model.mmproj_filename ? 'Trocar visão' : 'Adicionar visão'}
													</button>
												{/if}
												<button
													class="flex items-center gap-1 px-2.5 py-1.5 text-xs rounded-xl hover:bg-black/5 dark:hover:bg-white/5 transition text-gray-600 dark:text-gray-400"
													on:click={() => handleUnload(model)}
												>
													<svg xmlns="http://www.w3.org/2000/svg" class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
														<path stroke-linecap="round" stroke-linejoin="round" d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636" />
													</svg>
													Descarregar
												</button>
											{:else}
												<button
													class="flex items-center gap-1 px-2.5 py-1.5 text-xs rounded-xl bg-black text-white dark:bg-white dark:text-black hover:opacity-90 transition font-medium"
													on:click={() => startLoadWithContextModal(model)}
												>
													<svg xmlns="http://www.w3.org/2000/svg" class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
														<path stroke-linecap="round" stroke-linejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
													</svg>
													Carregar
												</button>
											{/if}
										</div>
									</div>

									<div class="flex items-center gap-3 mt-0.5 text-xs text-gray-500 dark:text-gray-400">
										<span>{model.file_size_human}</span>
										{#if model.is_loaded && model.n_gpu_layers !== null}
											<span>GPU: {model.n_gpu_layers === -1 ? 'Todas' : model.n_gpu_layers} camadas</span>
											<span>CTX: {model.n_ctx}</span>
										{/if}
									</div>

								</div>
							</div>
						</div>
					</div>
				{/each}
			</div>
		{/if}
	</div>

</div>
