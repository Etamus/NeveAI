<script lang="ts">
	import { toast } from 'svelte-sonner';
	import dayjs from 'dayjs';

	import { createEventDispatcher, onDestroy } from 'svelte';
	import { onMount, tick, getContext } from 'svelte';
	import type { Writable } from 'svelte/store';
	import type { i18n as i18nType, t } from 'i18next';

	const i18n = getContext<Writable<i18nType>>('i18n');

	const dispatch = createEventDispatcher();


	import { audioQueue, config, models, settings, TTSWorker, user } from '$lib/stores';
	import { copyToClipboard as _copyToClipboard, getMessageContentParts, removeAllDetails, removeReasoningControlTokens } from '$lib/utils';
	import { NEVEAI_BASE_URL } from '$lib/constants';

	import Name from './Name.svelte';
	import ProfileImage from './ProfileImage.svelte';
	import Skeleton from './Skeleton.svelte';
	import Image from '$lib/components/common/Image.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import WebSearchResults from './ResponseMessage/WebSearchResults.svelte';
	import Sparkles from '$lib/components/icons/Sparkles.svelte';

	import DeleteConfirmDialog from '$lib/components/common/ConfirmDialog.svelte';

	import ErrorDisplay from './Error.svelte';
	import Citations from './Citations.svelte';
	import CodeExecutions from './CodeExecutions.svelte';
	import ContentRenderer from './ContentRenderer.svelte';
	import { KokoroWorker } from '$lib/workers/KokoroWorker';
	import FileItem from '$lib/components/common/FileItem.svelte';
	import { fade } from 'svelte/transition';
	import StatusHistory from './ResponseMessage/StatusHistory.svelte';
	import FullHeightIframe from '$lib/components/common/FullHeightIframe.svelte';
	import GeneratedMusicPlayer from './GeneratedMusicPlayer.svelte';
	import GeneratedVideoPlayer from './GeneratedVideoPlayer.svelte';
	import GeneratedMediaProgress from './GeneratedMediaProgress.svelte';

	interface MessageType {
		[key: string]: any;
		id: string;
		model: string;
		content: string;
		files?: {
			[key: string]: any;
			id?: string;
			type: string;
			url: string;
			name?: string;
			content_type?: string;
			size?: number;
		}[];
		timestamp: number;
		role: string;
		statusHistory?: {
			hidden?: boolean;
			done: boolean;
			action: string;
			description: string;
			progress?: number;
			quality?: string;
			resolution?: string;
			width?: number;
			height?: number;
			error?: boolean;
			urls?: string[];
			query?: string;
		}[];
		status?: {
			done: boolean;
			action: string;
			description: string;
			urls?: string[];
			query?: string;
		};
		done: boolean;
		error?: boolean | { content: string };
		sources?: string[];
		code_executions?: {
			uuid: string;
			name: string;
			code: string;
			language?: string;
			result?: {
				error?: string;
				output?: string;
				files?: { name: string; url: string }[];
			};
		}[];
		info?: {
			openai?: boolean;
			prompt_tokens?: number;
			completion_tokens?: number;
			total_tokens?: number;
			eval_count?: number;
			eval_duration?: number;
			prompt_eval_count?: number;
			prompt_eval_duration?: number;
			total_duration?: number;
			load_duration?: number;
			usage?: unknown;
		};
		annotation?: { type: string; rating: number };
	}

	export let chatId = '';
	export let history: any;
	export let messageId: string;
	export let selectedModels: any[] = [];

	let message: MessageType = structuredClone(history.messages[messageId]);
	$: hasGeneratedDocument = (message?.files ?? []).some(
		(file) => file?.generated &&
			!['image', 'audio', 'video'].includes(file.type) &&
			!/^(image|audio|video)\//.test(file.content_type ?? '')
	);
	$: if (history.messages) {
		const source = history.messages[messageId];
		if (source) {
			// Fast path: O(1) check on the fields that change most often (content during streaming, done at end)
			// Avoids 2x O(n) JSON.stringify calls that are always true during streaming anyway
			if (message.content !== source.content || message.done !== source.done) {
				message = structuredClone(source);
			} else if (JSON.stringify(message) !== JSON.stringify(source)) {
				// Slow path: full comparison for infrequent changes (sources, annotations, status, etc.)
				message = structuredClone(source);
			}
		}
	}

	export let siblings: any[] = [];

	export let setInputText: Function = () => {};
	export let gotoMessage: Function = () => {};
	export let showPreviousMessage: Function;
	export let showNextMessage: Function;

	export let updateChat: Function;
	export let editMessage: Function;
	export let saveMessage: Function;
	export let rateMessage: Function;
	export let actionMessage: Function;
	export let deleteMessage: Function;

	export let submitMessage: Function;
	export let continueResponse: Function;
	export let regenerateResponse: Function;

	export let addMessages: Function;

	export let isLastMessage = true;
	export let readOnly = false;
	export let editCodeBlock = false;
	export let topPadding = false;

	let ctrlPressed = false;
	$: currentMessageIndex = Math.max(
		0,
		(siblings ?? []).findIndex((sibling: any) => sibling?.id === messageId)
	);

	const updateControlKey = (event: KeyboardEvent) => {
		ctrlPressed = event.ctrlKey || event.metaKey;
	};
	const clearControlKey = () => {
		ctrlPressed = false;
	};

	onMount(() => {
		window.addEventListener('keydown', updateControlKey);
		window.addEventListener('keyup', updateControlKey);
		window.addEventListener('blur', clearControlKey);
	});

	onDestroy(() => {
		window.removeEventListener('keydown', updateControlKey);
		window.removeEventListener('keyup', updateControlKey);
		window.removeEventListener('blur', clearControlKey);
	});

	let citationsElement: any;

	let contentContainerElement: HTMLDivElement;
	let buttonsContainerElement: HTMLDivElement;
	let showDeleteConfirm = false;

	let model: any = null;
	$: model = $models.find((m) => m.id === message.model);

	let edit = false;
	let editedContent = '';
	let editTextAreaElement: HTMLTextAreaElement;

	let messageIndexEdit = false;

	let speaking = false;
	let speakingIdx: number | undefined;

	let loadingSpeech = false;

	$: isGeneratedImageResponse = Boolean(
		message?.files?.some(
			(file) => file.type === 'image' || (file?.content_type ?? '').startsWith('image/')
		) && message?.statusHistory?.some((status) => status.action === 'stable_diffusion')
	);
	$: isGeneratedMusicResponse = Boolean(
		message?.files?.some(
			(file) => file.type === 'audio' || (file?.content_type ?? '').startsWith('audio/')
		) && message?.statusHistory?.some((status) => status.action === 'music_generation')
	);
	$: isGeneratedVideoResponse = Boolean(
		message?.files?.some(
			(file) => file.type === 'video' || (file?.content_type ?? '').startsWith('video/')
		) && message?.statusHistory?.some((status) => status.action === 'video_generation')
	);
	$: isGeneratedMediaResponse =
		isGeneratedImageResponse || isGeneratedMusicResponse || isGeneratedVideoResponse;
	$: latestVisualGenerationStatus = [...(message?.statusHistory ?? [])]
		.reverse()
		.find((status) => ['stable_diffusion', 'video_generation'].includes(status?.action));
	$: visualGenerationFileReady = Boolean(
		latestVisualGenerationStatus?.action === 'video_generation'
			? message?.files?.some(
					(file) => file.type === 'video' || (file?.content_type ?? '').startsWith('video/')
				)
			: message?.files?.some(
					(file) => file.type === 'image' || (file?.content_type ?? '').startsWith('image/')
				)
	);
	$: showVisualGenerationProgress = Boolean(
		latestVisualGenerationStatus &&
			!latestVisualGenerationStatus.error &&
			!visualGenerationFileReady
	);
	const visualResolutionAspectRatios: Record<string, number> = {
		'1:1': 1,
		'16:9': 16 / 9,
		'9:16': 9 / 16,
		'4:3': 4 / 3,
		'3:4': 3 / 4
	};
	$: generatedVisualAspectRatio = Math.max(
		0.01,
		Number(latestVisualGenerationStatus?.width) > 0 &&
			Number(latestVisualGenerationStatus?.height) > 0
			? Number(latestVisualGenerationStatus.width) /
				Number(latestVisualGenerationStatus.height)
			: visualResolutionAspectRatios[latestVisualGenerationStatus?.resolution ?? ''] ?? 16 / 9
	);
	$: generatedImageDisplayWidth = Math.min(26, 26 * generatedVisualAspectRatio);
	$: isVisualGenerationInProgress = Boolean(
		latestVisualGenerationStatus &&
			latestVisualGenerationStatus.done !== true &&
			!latestVisualGenerationStatus.error
	);

	const copyToClipboard = async (text) => {
		text = removeAllDetails(text);

		if (($config?.ui?.response_watermark ?? '').trim() !== '') {
			text = `${text}\n\n${$config?.ui?.response_watermark}`;
		}

		const res = await _copyToClipboard(text, null, $settings?.copyFormatted ?? false);
		if (res) {
			toast.success($i18n.t('Copying to clipboard was successful!'));
		}
	};

	const copyGeneratedImage = async () => {
		const file = message?.files?.find(
			(file) => file.type === 'image' || (file?.content_type ?? '').startsWith('image/')
		);
		if (!file?.url || !navigator.clipboard?.write || typeof ClipboardItem === 'undefined') {
			toast.error($i18n.t('Failed to copy image'));
			return;
		}

		try {
			const imageUrl = file.url.startsWith('/') ? `${NEVEAI_BASE_URL}${file.url}` : file.url;
			const response = await fetch(imageUrl, { credentials: 'include' });
			if (!response.ok) throw new Error(`HTTP ${response.status}`);
			let blob = await response.blob();

			if (blob.type !== 'image/png') {
				const bitmap = await createImageBitmap(blob);
				const canvas = document.createElement('canvas');
				canvas.width = bitmap.width;
				canvas.height = bitmap.height;
				canvas.getContext('2d')?.drawImage(bitmap, 0, 0);
				bitmap.close();
				blob = await new Promise<Blob>((resolve, reject) => {
					canvas.toBlob(
						(result) => (result ? resolve(result) : reject(new Error('PNG conversion failed'))),
						'image/png'
					);
				});
			}

			await navigator.clipboard.write([new ClipboardItem({ 'image/png': blob })]);
			toast.success($i18n.t('Copying to clipboard was successful!'));
		} catch (error) {
			console.error('Failed to copy generated image:', error);
			toast.error($i18n.t('Failed to copy image'));
		}
	};

	const stopAudio = () => {
		try {
			speechSynthesis.cancel();
			$audioQueue.stop();
		} catch {}

		if (speaking) {
			speaking = false;
			speakingIdx = undefined;
		}
	};

	const speak = async () => {
		if (!(message?.content ?? '').trim().length) {
			toast.info($i18n.t('No content to speak'));
			return;
		}

		speaking = true;
		const content = removeAllDetails(message.content);
		const getVoiceId = () => {
			if (model?.info?.meta?.tts?.voice) return model.info.meta.tts.voice;
			if ($settings?.audio?.tts?.defaultVoice === $config.audio.tts.voice) {
				return $settings?.audio?.tts?.voice ?? $config?.audio?.tts?.voice;
			}
			return $config?.audio?.tts?.voice;
		};

		if ($settings.audio?.tts?.engine === 'browser-kokoro') {
			$audioQueue.setId(`${message.id}`);
			$audioQueue.setPlaybackRate($settings.audio?.tts?.playbackRate ?? 1);
			$audioQueue.onStopped = () => {
				speaking = false;
				speakingIdx = undefined;
			};
			loadingSpeech = true;
			const messageContentParts: string[] = getMessageContentParts(
				content,
				$config?.audio?.tts?.split_on ?? 'punctuation'
			);
			if (!messageContentParts.length) {
				toast.info($i18n.t('No content to speak'));
				speaking = false;
				loadingSpeech = false;
				return;
			}
			if (!$TTSWorker) {
				await TTSWorker.set(
					new KokoroWorker($settings.audio?.tts?.engineConfig?.dtype ?? 'fp32')
				);
				await $TTSWorker.init();
			}
			for (const sentence of messageContentParts) {
				const url = await $TTSWorker
					.generate({ text: sentence, voice: getVoiceId() })
					.catch((error) => {
						console.error(error);
						toast.error(`${error}`);
						speaking = false;
						loadingSpeech = false;
					});
				if (url && speaking) {
					$audioQueue.enqueue(url);
					loadingSpeech = false;
				}
			}
			return;
		}

		let voices = [];
		const getVoicesLoop = setInterval(() => {
			voices = speechSynthesis.getVoices();
			if (voices.length === 0) return;
			clearInterval(getVoicesLoop);
			const voice = voices.find((item) => item.voiceURI === getVoiceId());
			const speech = new SpeechSynthesisUtterance(content);
			speech.rate = $settings.audio?.tts?.playbackRate ?? 1;
			speech.onend = () => {
				speaking = false;
				if ($settings.conversationMode) {
					document.getElementById('voice-input-button')?.click();
				}
			};
			if (voice) speech.voice = voice;
			speechSynthesis.speak(speech);
		}, 100);
	};

	let preprocessedDetailsCache = [];

	function preprocessForEditing(content: string): string {
		const detailsBlocks = [];
		const cleaned = content.replace(/<details[\s\S]*?<\/details>/gi, (match) => {
			detailsBlocks.push(match);
			return '';
		});
		preprocessedDetailsCache = detailsBlocks;
		return cleaned.replace(/^\s+/, '');
	}

	function postprocessAfterEditing(content: string): string {
		if (preprocessedDetailsCache.length === 0) return content;
		return preprocessedDetailsCache.join('\n') + '\n' + content;
	}

	const editMessageHandler = async () => {
		edit = true;

		editedContent = preprocessForEditing(message.content);

		await tick();

		const messagesContainer = document.getElementById('messages-container');
		const savedScrollTop = messagesContainer?.scrollTop;

		editTextAreaElement.style.height = '';
		editTextAreaElement.style.height = `${editTextAreaElement.scrollHeight}px`;

		if (messagesContainer) messagesContainer.scrollTop = savedScrollTop;
	};

	const editMessageConfirmHandler = async () => {
		const messageContent = postprocessAfterEditing(editedContent ? editedContent : '');
		editMessage(message.id, { content: messageContent }, false);

		edit = false;
		editedContent = '';

		await tick();
	};

	const saveAsCopyHandler = async () => {
		const messageContent = postprocessAfterEditing(editedContent ? editedContent : '');

		editMessage(message.id, { content: messageContent });

		edit = false;
		editedContent = '';

		await tick();
	};

	const cancelEditMessage = async () => {
		edit = false;
		editedContent = '';
		await tick();
	};


	const deleteMessageHandler = async () => {
		deleteMessage(message.id);
	};

	$: if (!edit) {
		(async () => {
			await tick();
		})();
	}

	const buttonsWheelHandler = (event: WheelEvent) => {
		if (buttonsContainerElement) {
			if (buttonsContainerElement.scrollWidth <= buttonsContainerElement.clientWidth) {
				// If the container is not scrollable, horizontal scroll
				return;
			} else {
				event.preventDefault();

				if (event.deltaY !== 0) {
					// Adjust horizontal scroll position based on vertical scroll
					buttonsContainerElement.scrollLeft += event.deltaY;
				}
			}
		}
	};

	const contentCopyHandler = (e) => {
		if (contentContainerElement) {
			e.preventDefault();
			// Get the selected HTML
			const selection = window.getSelection();
			const range = selection.getRangeAt(0);
			const tempDiv = document.createElement('div');

			// Remove background, color, and font styles
			tempDiv.appendChild(range.cloneContents());

			tempDiv.querySelectorAll('table').forEach((table) => {
				table.style.borderCollapse = 'collapse';
				table.style.width = 'auto';
				table.style.tableLayout = 'auto';
			});

			tempDiv.querySelectorAll('th').forEach((th) => {
				th.style.whiteSpace = 'nowrap';
				th.style.padding = '4px 8px';
			});

			// Put cleaned HTML + plain text into clipboard
			e.clipboardData.setData('text/html', tempDiv.innerHTML);
			e.clipboardData.setData('text/plain', selection.toString());
		}
	};

	onMount(async () => {

		await tick();
		if (buttonsContainerElement) {
			buttonsContainerElement.addEventListener('wheel', buttonsWheelHandler);
		}

		if (contentContainerElement) {
			contentContainerElement.addEventListener('copy', contentCopyHandler);
		}
	});

	onDestroy(() => {
		if (buttonsContainerElement) {
			buttonsContainerElement.removeEventListener('wheel', buttonsWheelHandler);
		}

		if (contentContainerElement) {
			contentContainerElement.removeEventListener('copy', contentCopyHandler);
		}
	});
</script>

<DeleteConfirmDialog
	bind:show={showDeleteConfirm}
	title={$i18n.t('Delete message?')}
	on:confirm={() => {
		deleteMessageHandler();
	}}
/>

{#key message.id}
	<div
		class=" flex w-full message-{message.id}"
		class:document-response={hasGeneratedDocument}
		id="message-{message.id}"
		dir={$settings.chatDirection}
		style="scroll-margin-top: 3rem;"
		in:fade={{ duration: 150, delay: 50 }}
	>
		<div class="flex-auto w-0 pl-1.5 relative">
			<div>
				<div class="chat-{message.role} w-full min-w-full markdown-prose">
					<div>
						{#if model?.info?.meta?.capabilities?.status_updates ?? true}
							<div class="mt-1 pl-3">
								<StatusHistory statusHistory={message?.statusHistory} />
							</div>
						{/if}

						{#if showVisualGenerationProgress}
							<div class="my-2 w-full">
								<GeneratedMediaProgress
									kind={latestVisualGenerationStatus.action === 'video_generation' ? 'video' : 'image'}
									progress={latestVisualGenerationStatus.progress ??
										(latestVisualGenerationStatus.done ? 100 : 0)}
									width={latestVisualGenerationStatus.width ??
										(latestVisualGenerationStatus.quality === 'neve_image_2' ? 16 : 1)}
									height={latestVisualGenerationStatus.height ??
										(latestVisualGenerationStatus.quality === 'neve_image_2' ? 9 : 1)}
								/>
							</div>
						{/if}

						{#if message?.files && message.files.some((file) => file.type === 'image' || file.type === 'audio' || file.type === 'video' || (file?.content_type ?? '').startsWith('image/') || (file?.content_type ?? '').startsWith('audio/') || (file?.content_type ?? '').startsWith('video/'))}
							<div
								class="my-1 w-full flex overflow-x-auto gap-2 flex-wrap"
								dir={$settings?.chatDirection ?? 'auto'}
							>
								{#each message.files.filter((file) => file.type === 'image' || file.type === 'audio' || file.type === 'video' || (file?.content_type ?? '').startsWith('image/') || (file?.content_type ?? '').startsWith('audio/') || (file?.content_type ?? '').startsWith('video/')) as file}
									<div
										class={file.type === 'video' ||
										(file?.content_type ?? '').startsWith('video/') ||
										((file.type === 'image' || (file?.content_type ?? '').startsWith('image/')) &&
											message?.statusHistory?.some((status) => status.action === 'stable_diffusion'))
											? 'w-full'
											: ''}
									>
										{#if file.type === 'image' || (file?.content_type ?? '').startsWith('image/')}
											{#if message?.statusHistory?.some((status) => status.action === 'stable_diffusion')}
												<div
													data-generated-visual-media
													class="relative w-full overflow-hidden rounded-lg"
													style={`aspect-ratio: ${generatedVisualAspectRatio}; width: min(100%, ${generatedImageDisplayWidth}rem); max-height: 26rem;`}
												>
													<Image
														src={file.url}
														alt={message.content}
														containerClassName="size-full"
														className="block size-full outline-hidden focus:outline-hidden"
														imageClassName="block size-full rounded-lg object-contain"
													/>
												</div>
											{:else}
												<Image src={file.url} alt={message.content} imageClassName="rounded-lg" />
											{/if}
										{:else if file.type === 'audio' || (file?.content_type ?? '').startsWith('audio/')}
											{#if message?.statusHistory?.some((status) => status.action === 'music_generation')}
												<GeneratedMusicPlayer
													src={file.url}
													fileId={file.id ?? null}
													name={file.name ?? 'musica.mp3'}
												/>
											{:else}
												<div
													class="mx-auto self-center w-full min-w-0 max-w-md rounded-md border border-gray-200 bg-gray-50 px-3 py-2.5 dark:border-gray-700/70 dark:bg-gray-800/50"
												>
													<audio
														controls
														preload="metadata"
														src={file.url.startsWith('/')
															? `${NEVEAI_BASE_URL}${file.url}`
															: file.url}
														class="h-10 w-full"
													></audio>
												</div>
											{/if}
										{:else if file.type === 'video' || (file?.content_type ?? '').startsWith('video/')}
											<GeneratedVideoPlayer
												src={file.url}
												fileId={file.id ?? null}
												name={file.name ?? 'video.mp4'}
												initialAspectRatio={generatedVisualAspectRatio}
											/>
										{/if}
									</div>
								{/each}
							</div>
						{/if}

						{#if message?.embeds && message.embeds.length > 0}
							<div
								class="my-1 w-full flex overflow-x-auto gap-2 flex-wrap"
								id={`${message.id}-embeds-container`}
							>
								{#each message.embeds as embed, idx}
									<div class="my-2 w-full" id={`${message.id}-embeds-${idx}`}>
										<FullHeightIframe
											src={embed}
											allowScripts={true}
											allowForms={true}
											allowSameOrigin={$settings?.iframeSandboxAllowSameOrigin ?? false}
											allowPopups={true}
										/>
									</div>
								{/each}
							</div>
						{/if}

						{#if edit === true}
							<div class="w-full bg-gray-50 dark:bg-gray-800 rounded-3xl px-5 py-3 my-2">
								<textarea
									id="message-edit-{message.id}"
									bind:this={editTextAreaElement}
									class=" bg-transparent outline-hidden w-full resize-none"
									bind:value={editedContent}
									on:input={(e) => {
										const messagesContainer = document.getElementById('messages-container');
										const savedScrollTop = messagesContainer?.scrollTop;
										const textarea = e.currentTarget as HTMLTextAreaElement;

										textarea.style.height = '';
										textarea.style.height = `${textarea.scrollHeight}px`;

										if (messagesContainer) messagesContainer.scrollTop = savedScrollTop;
									}}
									on:keydown={(e) => {
										if (e.key === 'Escape') {
											document.getElementById('close-edit-message-button')?.click();
										}

										const isCmdOrCtrlPressed = e.metaKey || e.ctrlKey;
										const isEnterPressed = e.key === 'Enter';

										if (isCmdOrCtrlPressed && isEnterPressed) {
											document.getElementById('confirm-edit-message-button')?.click();
										}
									}}
								/>

								<div class=" mt-2 mb-1 flex justify-end text-sm font-medium">
									<div class="flex space-x-1.5 items-center">
										<button
											id="close-edit-message-button"
											class="px-4 py-1.5 text-xs font-medium bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 transition rounded-lg inline-flex items-center"
											on:click={() => {
												cancelEditMessage();
											}}
										>
											{$i18n.t('Cancel')}
										</button>

										<button
											id="confirm-edit-message-button"
											class="px-4 py-1.5 text-xs font-medium bg-black text-white dark:bg-white dark:text-black hover:opacity-90 transition rounded-lg inline-flex items-center"
											on:click={() => {
												editMessageConfirmHandler();
											}}
										>
											{$i18n.t('Save')}
										</button>
									</div>
								</div>
							</div>
						{/if}

						<div
							bind:this={contentContainerElement}
							class="w-full flex flex-col relative {edit ? 'hidden' : ''}"
							id="response-content-container"
						>
							{#if (message.content ?? '').trim() === '' && !message.error && ((model?.info?.meta?.capabilities?.status_updates ?? true) ? (message?.statusHistory ?? [...(message?.status ? [message?.status] : [])]).length === 0 || (message?.statusHistory?.at(-1)?.hidden ?? false) : true)}
								<Skeleton size={message?.done !== true ? 'sm' : 'md'} />
							{:else if (message.content ?? '').trim() !== '' && message.error !== true}
								<!-- always show message contents even if there's an error -->
								<!-- unless message.error === true which is legacy error handling, where the error message is stored in message.content -->
								<ContentRenderer
									id={`${chatId}-${message.id}`}
									messageId={message.id}
									{history}
									{selectedModels}
									content={removeReasoningControlTokens(message.content)}
									sources={message.sources}
									floatingButtons={message?.done &&
										!readOnly &&
										($settings?.showFloatingActionButtons ?? true)}
									save={!readOnly}
									preview={!readOnly}
									{editCodeBlock}
									{topPadding}
									done={($settings?.chatFadeStreamingText ?? true)
										? (message?.done ?? false)
										: true}
									messageDone={message?.done ?? false}
									{model}
									onTaskClick={async (e) => {
										console.log(e);
									}}
									onSourceClick={async (id) => {
										console.log(id);

										if (citationsElement) {
											citationsElement?.showSourceModal(id);
										}
									}}
									onAddMessages={({ modelId, parentId, messages }) => {
										addMessages({ modelId, parentId, messages });
									}}
									onSave={({ raw, oldContent, newContent }) => {
										history.messages[message.id].content = history.messages[
											message.id
										].content.replace(raw, raw.replace(oldContent, newContent));

										updateChat();
									}}
								/>
							{/if}

							{#if message?.error}
								<ErrorDisplay
									content={typeof message.error === 'object' ? message.error.content : message.content}
								/>
							{/if}

							{#if (message?.sources || message?.citations) && (model?.info?.meta?.capabilities?.citations ?? true)}
								<Citations
									bind:this={citationsElement}
									id={message?.id}
									{chatId}
									sources={message?.sources ?? message?.citations}
									{readOnly}
								/>
							{/if}

							{#if message.code_executions}
								<CodeExecutions codeExecutions={message.code_executions} />
							{/if}
						</div>

						{#if message?.files?.some((file) => file?.generated)}
							<div
								class="mt-3 mb-5 flex w-full flex-col gap-2"
								dir={$settings?.chatDirection ?? 'auto'}
							>
								{#each message.files.filter((file) => file?.generated) as file}
									<FileItem
										item={file}
										chatAttachment={true}
										url={file.url ?? file.id}
										name={file.name ?? file?.meta?.name ?? 'Arquivo'}
										type={file.type ?? 'file'}
										size={file?.size ?? file?.meta?.size}
										className="w-full max-w-[30rem]"
									/>
								{/each}
							</div>
						{/if}
					</div>
				</div>

				{#if !edit && !isVisualGenerationInProgress}
					<div
						bind:this={buttonsContainerElement}
						class="flex items-center gap-1 buttons text-gray-600 dark:text-gray-500 mt-1"
					>
						{#if message.done || siblings.length > 1}
							{#if siblings.length > 1}
								<div class="flex self-center min-w-fit" dir="ltr">
									<button
										aria-label={$i18n.t('Previous message')}
										class="self-center p-1 hover:bg-black/5 dark:hover:bg-white/5 dark:hover:text-white hover:text-black rounded-md transition"
										on:click={() => {
											showPreviousMessage(message);
										}}
									>
										<svg
											xmlns="http://www.w3.org/2000/svg"
											fill="none"
											viewBox="0 0 24 24"
											stroke-width="2.3"
											aria-hidden="true"
											stroke="currentColor"
											class="size-3.5"
										>
											<path
												stroke-linecap="round"
												stroke-linejoin="round"
												d="M15.75 19.5 8.25 12l7.5-7.5"
											/>
										</svg>
									</button>
									<div class="text-xs font-bold self-center dark:text-white" dir="ltr">
										{currentMessageIndex + 1}/{siblings.length}
									</div>
									<button
										aria-label={$i18n.t('Next message')}
										class="self-center p-1 hover:bg-black/5 dark:hover:bg-white/5 dark:hover:text-white hover:text-black rounded-md transition"
										on:click={() => {
											showNextMessage(message);
										}}
									>
										<svg
											xmlns="http://www.w3.org/2000/svg"
											fill="none"
											viewBox="0 0 24 24"
											stroke-width="2.3"
											aria-hidden="true"
											stroke="currentColor"
											class="size-3.5"
										>
											<path
												stroke-linecap="round"
												stroke-linejoin="round"
												d="M8.25 4.5l7.5 7.5-7.5 7.5"
											/>
										</svg>
									</button>
								</div>
							{/if}
							{#if message.done && !readOnly && !isGeneratedMusicResponse && !isGeneratedVideoResponse}
								<Tooltip content={$i18n.t('Copy')} placement="bottom">
									<button
										aria-label={$i18n.t('Copy')}
										class="p-1 hover:bg-black/5 dark:hover:bg-white/5 rounded-full dark:hover:text-white hover:text-black transition copy-response-button"
										on:click={() => {
											if (isGeneratedImageResponse) {
												copyGeneratedImage();
											} else {
												copyToClipboard(message.content);
											}
										}}
									>
										<svg
											xmlns="http://www.w3.org/2000/svg"
											fill="none"
											aria-hidden="true"
											viewBox="0 0 24 24"
											stroke-width="2.3"
											stroke="currentColor"
											class="w-4 h-4"
										>
											<path
												stroke-linecap="round"
												stroke-linejoin="round"
												d="M15.666 3.888A2.25 2.25 0 0013.5 2.25h-3c-1.03 0-1.9.693-2.166 1.638m7.332 0c.055.194.084.4.084.612v0a.75.75 0 01-.75.75H9a.75.75 0 01-.75-.75v0c0-.212.03-.418.084-.612m7.332 0c.646.049 1.288.11 1.927.184 1.1.128 1.907 1.077 1.907 2.185V19.5a2.25 2.25 0 01-2.25 2.25H6.75A2.25 2.25 0 014.5 19.5V6.257c0-1.108.806-2.057 1.907-2.185a48.208 48.208 0 011.927-.184"
											/>
										</svg>
									</button>
								</Tooltip>
							{/if}
							{#if message.done}
								{#if !readOnly}
									{#if $user?.role === 'admin' || ($user?.permissions?.chat?.regenerate_response ?? true)}
										<Tooltip content={$i18n.t('Regenerate')} placement="bottom">
											<button
												type="button"
												aria-label={$i18n.t('Regenerate')}
												class="p-1 hover:bg-black/5 dark:hover:bg-white/5 rounded-full dark:hover:text-white hover:text-black transition regenerate-response-button"
												on:click={() => {
													regenerateResponse(message);
													(model?.actions ?? []).forEach((action) => {
														dispatch('action', {
															id: action.id,
															event: { id: 'regenerate-response', data: { messageId: message.id } }
														});
													});
												}}
											>
												<svg
													xmlns="http://www.w3.org/2000/svg"
													fill="none"
													viewBox="0 0 24 24"
													stroke-width="2.3"
													aria-hidden="true"
													stroke="currentColor"
													class="w-4 h-4"
												>
													<path
														stroke-linecap="round"
														stroke-linejoin="round"
														d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182m0-4.991v4.99"
													/>
												</svg>
											</button>
										</Tooltip>
									{/if}
									{#if !isGeneratedMediaResponse && isLastMessage && ($user?.role === 'admin' || ($user?.permissions?.chat?.continue_response ?? true))}
										<Tooltip content={$i18n.t('Continuar')} placement="bottom">
											<button
												aria-label={$i18n.t('Continuar')}
												type="button"
												id="continue-response-button"
												class="p-1 hover:bg-black/5 dark:hover:bg-white/5 rounded-full dark:hover:text-white hover:text-black transition"
												on:click={() => {
													continueResponse();
												}}
											>
												<svg
													aria-hidden="true"
													xmlns="http://www.w3.org/2000/svg"
													fill="none"
													viewBox="0 0 24 24"
													stroke-width="2.3"
													stroke="currentColor"
													class="w-4 h-4"
												>
													<path
														stroke-linecap="round"
														stroke-linejoin="round"
														d="M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z"
													/>
													<path
														stroke-linecap="round"
														stroke-linejoin="round"
														d="M15.91 11.672a.375.375 0 0 1 0 .656l-5.603 3.113a.375.375 0 0 1-.557-.328V8.887c0-.286.307-.466.557-.327l5.603 3.112Z"
													/>
												</svg>
											</button>
										</Tooltip>
									{/if}
								{/if}
								{#if !readOnly && !isGeneratedMediaResponse}
									{#if $user?.role === 'admin' || ($user?.permissions?.chat?.delete_message ?? true)}
										{#if siblings.length > 1}
											<Tooltip content={$i18n.t('Delete')} placement="bottom">
												<button
													type="button"
													aria-label={$i18n.t('Delete')}
													id="delete-response-button"
													class="p-1 hover:bg-black/5 dark:hover:bg-white/5 rounded-full dark:hover:text-white hover:text-black transition"
													on:click={() => {
														showDeleteConfirm = true;
													}}
												>
													<svg
														xmlns="http://www.w3.org/2000/svg"
														fill="none"
														viewBox="0 0 24 24"
														stroke-width="2"
														stroke="currentColor"
														aria-hidden="true"
														class="w-4 h-4"
													>
														<path
															stroke-linecap="round"
															stroke-linejoin="round"
															d="m14.74 9-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 0 1-2.244 2.077H8.084a2.25 2.25 0 0 1-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 0 0-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 0 1 3.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 0 0-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 0 0-7.5 0"
														/>
													</svg>
												</button>
											</Tooltip>
										{/if}
									{/if}
									{#each model?.actions ?? [] as action}
										<Tooltip content={action.name} placement="bottom">
											<button
												type="button"
												aria-label={action.name}
												class="p-1 hover:bg-black/5 dark:hover:bg-white/5 rounded-full dark:hover:text-white hover:text-black transition"
												on:click={() => {
													actionMessage(action.id, message);
												}}
											>
												{#if action?.icon}
													<div class="size-4">
														<img
															src={action.icon}
															class="w-4 h-4 {action.icon.includes('data:image/svg')
																? 'dark:invert-[80%]'
																: ''}"
															style="fill: currentColor;"
															alt={action.name}
														/>
													</div>
												{:else}
													<Sparkles strokeWidth="2.1" className="size-4" />
												{/if}
											</button>
										</Tooltip>
									{/each}
								{/if}
							{/if}
						{/if}
					</div>
				{/if}
			</div>
		</div>
	</div>
{/key}

<style>
	/* Keep the entire document reply on one raster origin, including hovered controls. */
	.document-response {
		transform: translateZ(0);
	}
	.buttons::-webkit-scrollbar {
		display: none; /* for Chrome, Safari and Opera */
	}

	.buttons {
		-ms-overflow-style: none; /* IE and Edge */
		scrollbar-width: none; /* Firefox */
	}
</style>
