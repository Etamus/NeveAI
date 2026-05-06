<script lang="ts">
	import { toast } from 'svelte-sonner';

	import { onMount, getContext, createEventDispatcher } from 'svelte';

	const dispatch = createEventDispatcher();

	import {
		getQuerySettings,
		updateQuerySettings,
		resetVectorDB,
		getEmbeddingConfig,
		updateEmbeddingConfig,
		getRerankingConfig,
		updateRerankingConfig,
		getRAGConfig,
		updateRAGConfig
	} from '$lib/apis/retrieval';

	import { reindexKnowledgeFiles } from '$lib/apis/knowledge';
	import { deleteAllFiles } from '$lib/apis/files';

	import ResetUploadDirConfirmDialog from '$lib/components/common/ConfirmDialog.svelte';
	import ResetVectorDBConfirmDialog from '$lib/components/common/ConfirmDialog.svelte';
	import ReindexKnowledgeFilesConfirmDialog from '$lib/components/common/ConfirmDialog.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import Textarea from '$lib/components/common/Textarea.svelte';
	import Spinner from '$lib/components/common/Spinner.svelte';

	const i18n = getContext('i18n');

	let updateEmbeddingModelLoading = false;
	let updateRerankingModelLoading = false;

	let showResetConfirm = false;
	let showResetUploadDirConfirm = false;
	let showReindexConfirm = false;

	let RAG_EMBEDDING_ENGINE = '';
	let RAG_EMBEDDING_MODEL = '';
	let RAG_EMBEDDING_BATCH_SIZE = 1;
	let ENABLE_ASYNC_EMBEDDING = true;
	let RAG_EMBEDDING_CONCURRENT_REQUESTS = 0;

	let rerankingModel = '';

	let querySettings = {
		template: '',
		r: 0.0,
		k: 4,
		k_reranker: 4,
		hybrid: false
	};

	let RAGConfig = null;

	const embeddingModelUpdateHandler = async () => {
		if (RAG_EMBEDDING_ENGINE === '' && RAG_EMBEDDING_MODEL.split('/').length - 1 > 1) {
			toast.error(
				$i18n.t(
					'Model filesystem path detected. Model shortname is required for update, cannot continue.'
				)
			);
			return;
		}
		if (['openai', 'azure_openai'].includes(RAG_EMBEDDING_ENGINE)) {
			RAG_EMBEDDING_ENGINE = '';
			RAG_EMBEDDING_MODEL = 'sentence-transformers/all-MiniLM-L6-v2';
		}

		console.debug('Update embedding model attempt:', {
			RAG_EMBEDDING_ENGINE,
			RAG_EMBEDDING_MODEL,
			RAG_EMBEDDING_BATCH_SIZE,
			ENABLE_ASYNC_EMBEDDING,
			RAG_EMBEDDING_CONCURRENT_REQUESTS
		});

		updateEmbeddingModelLoading = true;
		const res = await updateEmbeddingConfig(localStorage.token, {
			RAG_EMBEDDING_ENGINE: RAG_EMBEDDING_ENGINE,
			RAG_EMBEDDING_MODEL: RAG_EMBEDDING_MODEL,
			RAG_EMBEDDING_BATCH_SIZE: RAG_EMBEDDING_BATCH_SIZE,
			ENABLE_ASYNC_EMBEDDING: ENABLE_ASYNC_EMBEDDING,
			RAG_EMBEDDING_CONCURRENT_REQUESTS: RAG_EMBEDDING_CONCURRENT_REQUESTS
		}).catch(async (error) => {
			toast.error(`${error}`);
			await setEmbeddingConfig();
			return null;
		});
		updateEmbeddingModelLoading = false;

		if (res) {
			console.debug('embeddingModelUpdateHandler:', res);
		}
	};

	const submitHandler = async () => {
		if (
			RAGConfig.CONTENT_EXTRACTION_ENGINE === 'external' &&
			RAGConfig.EXTERNAL_DOCUMENT_LOADER_URL === ''
		) {
			toast.error($i18n.t('External Document Loader URL required.'));
			return;
		}
		if (RAGConfig.CONTENT_EXTRACTION_ENGINE === 'tika' && RAGConfig.TIKA_SERVER_URL === '') {
			toast.error($i18n.t('Tika Server URL required.'));
			return;
		}
		if (RAGConfig.CONTENT_EXTRACTION_ENGINE === 'docling' && RAGConfig.DOCLING_SERVER_URL === '') {
			toast.error($i18n.t('Docling Server URL required.'));
			return;
		}
		if (
			RAGConfig.CONTENT_EXTRACTION_ENGINE === 'datalab_marker' &&
			RAGConfig.DATALAB_MARKER_ADDITIONAL_CONFIG &&
			RAGConfig.DATALAB_MARKER_ADDITIONAL_CONFIG.trim() !== ''
		) {
			try {
				JSON.parse(RAGConfig.DATALAB_MARKER_ADDITIONAL_CONFIG);
			} catch (e) {
				toast.error($i18n.t('Invalid JSON format in Additional Config'));
				return;
			}
		}

		if (
			RAGConfig.CONTENT_EXTRACTION_ENGINE === 'document_intelligence' &&
			RAGConfig.DOCUMENT_INTELLIGENCE_ENDPOINT === ''
		) {
			toast.error($i18n.t('Document Intelligence endpoint required.'));
			return;
		}
		if (
			RAGConfig.CONTENT_EXTRACTION_ENGINE === 'mistral_ocr' &&
			RAGConfig.MISTRAL_OCR_API_KEY === ''
		) {
			toast.error($i18n.t('Mistral OCR API Key required.'));
			return;
		}

		if (
			RAGConfig.CONTENT_EXTRACTION_ENGINE === 'mineru' &&
			RAGConfig.MINERU_API_MODE === 'cloud' &&
			RAGConfig.MINERU_API_KEY === ''
		) {
			toast.error($i18n.t('MinerU API Key required for Cloud API mode.'));
			return;
		}

		if (!RAGConfig.BYPASS_EMBEDDING_AND_RETRIEVAL) {
			await embeddingModelUpdateHandler();
		}

		if (RAGConfig.DOCLING_PARAMS) {
			try {
				JSON.parse(RAGConfig.DOCLING_PARAMS);
			} catch (e) {
				toast.error(
					$i18n.t('Invalid JSON format in {{NAME}}', {
						NAME: $i18n.t('Docling Parameters')
					})
				);
				return;
			}
		}
		if (RAGConfig.MINERU_PARAMS) {
			try {
				JSON.parse(RAGConfig.MINERU_PARAMS);
			} catch (e) {
				toast.error($i18n.t('Invalid JSON format in MinerU Parameters'));
				return;
			}
		}

		const res = await updateRAGConfig(localStorage.token, {
			...RAGConfig,
			// Convert null (from cleared number inputs) to empty string so the backend
			// can distinguish "clear this field" from "don't change this field"
			FILE_MAX_SIZE: RAGConfig.FILE_MAX_SIZE ?? '',
			FILE_MAX_COUNT: RAGConfig.FILE_MAX_COUNT ?? '',
			FILE_IMAGE_COMPRESSION_WIDTH: RAGConfig.FILE_IMAGE_COMPRESSION_WIDTH ?? '',
			FILE_IMAGE_COMPRESSION_HEIGHT: RAGConfig.FILE_IMAGE_COMPRESSION_HEIGHT ?? '',
			ALLOWED_FILE_EXTENSIONS: RAGConfig.ALLOWED_FILE_EXTENSIONS.split(',')
				.map((ext) => ext.trim())
				.filter((ext) => ext !== ''),
			DOCLING_PARAMS:
				typeof RAGConfig.DOCLING_PARAMS === 'string' && RAGConfig.DOCLING_PARAMS.trim() !== ''
					? JSON.parse(RAGConfig.DOCLING_PARAMS)
					: {},
			MINERU_PARAMS:
				typeof RAGConfig.MINERU_PARAMS === 'string' && RAGConfig.MINERU_PARAMS.trim() !== ''
					? JSON.parse(RAGConfig.MINERU_PARAMS)
					: {}
		});
		dispatch('save');
	};

	const setEmbeddingConfig = async () => {
		const embeddingConfig = await getEmbeddingConfig(localStorage.token);

		if (embeddingConfig) {
			RAG_EMBEDDING_ENGINE = embeddingConfig.RAG_EMBEDDING_ENGINE;
			RAG_EMBEDDING_MODEL = embeddingConfig.RAG_EMBEDDING_MODEL;
			RAG_EMBEDDING_BATCH_SIZE = embeddingConfig.RAG_EMBEDDING_BATCH_SIZE ?? 1;
			ENABLE_ASYNC_EMBEDDING = embeddingConfig.ENABLE_ASYNC_EMBEDDING ?? true;
			RAG_EMBEDDING_CONCURRENT_REQUESTS = embeddingConfig.RAG_EMBEDDING_CONCURRENT_REQUESTS ?? 0;

		}
	};
	onMount(async () => {
		await setEmbeddingConfig();

		const config = await getRAGConfig(localStorage.token);
		config.ALLOWED_FILE_EXTENSIONS = (config?.ALLOWED_FILE_EXTENSIONS ?? []).join(', ');

		config.DOCLING_PARAMS =
			typeof config.DOCLING_PARAMS === 'object'
				? JSON.stringify(config.DOCLING_PARAMS ?? {}, null, 2)
				: config.DOCLING_PARAMS;

		config.MINERU_PARAMS =
			typeof config.MINERU_PARAMS === 'object'
				? JSON.stringify(config.MINERU_PARAMS ?? {}, null, 2)
				: config.MINERU_PARAMS;

		RAGConfig = config;
	});
</script>

<ResetUploadDirConfirmDialog
	bind:show={showResetUploadDirConfirm}
	on:confirm={async () => {
		const res = await deleteAllFiles(localStorage.token).catch((error) => {
			toast.error(`${error}`);
			return null;
		});

		if (res) {
			toast.success($i18n.t('Success'));
		}
	}}
/>

<ResetVectorDBConfirmDialog
	bind:show={showResetConfirm}
	on:confirm={() => {
		const res = resetVectorDB(localStorage.token).catch((error) => {
			toast.error(`${error}`);
			return null;
		});

		if (res) {
			toast.success($i18n.t('Success'));
		}
	}}
/>

<ReindexKnowledgeFilesConfirmDialog
	bind:show={showReindexConfirm}
	on:confirm={async () => {
		const res = await reindexKnowledgeFiles(localStorage.token).catch((error) => {
			toast.error(`${error}`);
			return null;
		});

		if (res) {
			toast.success($i18n.t('Success'));
		}
	}}
/>

<form
	class="flex flex-col h-full justify-between space-y-3 text-sm"
	on:submit|preventDefault={() => {
		submitHandler();
	}}
>
	{#if RAGConfig}
		<div class=" space-y-2.5 overflow-y-scroll scrollbar-hidden h-full pr-1.5">
			<div class="">
				<div class="mb-3">
					<div class=" mt-0.5 mb-2.5 text-base font-medium">{$i18n.t('General')}</div>

					<hr class=" border-gray-100/30 dark:border-gray-850/30 my-2" />
				</div>

				{#if !RAGConfig.BYPASS_EMBEDDING_AND_RETRIEVAL}
					<div class="mb-3">
						<div class=" mt-0.5 mb-2.5 text-base font-medium">{$i18n.t('Embedding')}</div>

						<hr class=" border-gray-100/30 dark:border-gray-850/30 my-2" />

						<div class="  mb-2.5 flex flex-col w-full justify-between">
							<div class="flex w-full justify-between">
								<div class=" self-center text-xs font-medium">
									{$i18n.t('Embedding Model Engine')}
								</div>
								<div class="flex items-center relative">
									<select
										class="w-fit pr-8 rounded-sm px-2 p-1 text-xs bg-transparent outline-hidden text-right"
										bind:value={RAG_EMBEDDING_ENGINE}
										placeholder={$i18n.t('Select an embedding model engine')}
										on:change={(e) => {
											if (e.target.value === '') {
												RAG_EMBEDDING_MODEL = 'sentence-transformers/all-MiniLM-L6-v2';
											}
										}}
									>
										<option value="">{$i18n.t('Default (SentenceTransformers)')}</option>
									</select>
								</div>
							</div>
						</div>

						<div class="  mb-2.5 flex flex-col w-full">
							<div class=" mb-1 text-xs font-medium">{$i18n.t('Embedding Model')}</div>

							<div class="">
								<div class="flex w-full">
										<div class="flex-1 mr-2">
											<input
												class="flex-1 w-full text-sm bg-transparent outline-hidden"
												placeholder={$i18n.t('Set embedding model (e.g. {{model}})', {
													model: RAG_EMBEDDING_MODEL.slice(-40)
												})}
												bind:value={RAG_EMBEDDING_MODEL}
											/>
										</div>

										{#if RAG_EMBEDDING_ENGINE === ''}
											<button
												class="px-2.5 bg-transparent text-gray-800 dark:bg-transparent dark:text-gray-100 rounded-lg transition"
												on:click={() => {
													embeddingModelUpdateHandler();
												}}
												disabled={updateEmbeddingModelLoading}
											>
												{#if updateEmbeddingModelLoading}
													<div class="self-center">
														<Spinner />
													</div>
												{:else}
													<svg
														xmlns="http://www.w3.org/2000/svg"
														viewBox="0 0 16 16"
														fill="currentColor"
														class="w-4 h-4"
													>
														<path
															d="M8.75 2.75a.75.75 0 0 0-1.5 0v5.69L5.03 6.22a.75.75 0 0 0-1.06 1.06l3.5 3.5a.75.75 0 0 0 1.06 0l3.5-3.5a.75.75 0 0 0-1.06-1.06L8.75 8.44V2.75Z"
														/>
														<path
															d="M3.5 9.75a.75.75 0 0 0-1.5 0v1.5A2.75 2.75 0 0 0 4.75 14h6.5A2.75 2.75 0 0 0 14 11.25v-1.5a.75.75 0 0 0-1.5 0v1.5c0 .69-.56 1.25-1.25 1.25h-6.5c-.69 0-1.25-.56-1.25-1.25v-1.5Z"
														/>
													</svg>
												{/if}
											</button>
										{/if}
								</div>
							</div>

							<div class="mt-1 mb-1 text-xs text-gray-400 dark:text-gray-500">
								{$i18n.t(
									'After updating or changing the embedding model, you must reindex the knowledge base for the changes to take effect. You can do this using the "Reindex" button below.'
								)}
							</div>
						</div>

						<div class="  mb-2.5 flex w-full justify-between">
							<div class=" self-center text-xs font-medium">
								{$i18n.t('Embedding Batch Size')}
							</div>

							<div class="">
								<input
									bind:value={RAG_EMBEDDING_BATCH_SIZE}
									type="number"
									class=" bg-transparent text-center w-14 outline-none"
									min="-2"
									max="16000"
									step="1"
								/>
							</div>
						</div>
					</div>

				{/if}
			</div>
		</div>
		<div class="flex justify-end pt-3 text-sm font-medium">
			<button
				class="px-3.5 py-1.5 text-sm font-medium bg-black hover:bg-gray-900 text-white dark:bg-white dark:text-black dark:hover:bg-gray-100 transition rounded-full"
				type="submit"
			>
				{$i18n.t('Save')}
			</button>
		</div>
	{:else}
		<div class="flex items-center justify-center h-full">
			<Spinner className="size-5" />
		</div>
	{/if}
</form>
