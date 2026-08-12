<script lang="ts">
	import { v4 as uuidv4 } from 'uuid';
	import { toast } from 'svelte-sonner';
	import { PaneGroup, Pane, PaneResizer } from 'paneforge';

	import { flushSync, getContext, onDestroy, onMount, tick } from 'svelte';
	import { fade } from 'svelte/transition';
	const i18n: Writable<i18nType> = getContext('i18n');

	import { goto } from '$app/navigation';
	import { page } from '$app/stores';

	import { get, type Unsubscriber, type Writable } from 'svelte/store';
	import type { i18n as i18nType } from 'i18next';
	import { NEVEAI_BASE_URL } from '$lib/constants';

	import {
		chatId,
		chats,
		config,
		type Model,
		models,
		tags as allTags,
		settings,
		showSidebar,
		NEVEAI_NAME,
		banners,
		user,
		socket,
		audioQueue,
		showControls,
		showCallOverlay,
		currentChatPage,
		temporaryChatEnabled,
		mobile,
		chatTitle,
		showArtifacts,
		artifactContents,
		tools,
		toolServers,
		terminalServers,
		functions,
		selectedFolder,
		pinnedChats,
		showEmbeds,
		selectedTerminalId,
		showFileNavPath,
		showFileNavDir,
		chatCodeExecutionEnabled,
		activeChatIds
	} from '$lib/stores';

	import { NEVEAI_API_BASE_URL } from '$lib/constants';

	import {
		convertMessagesToHistory,
		copyToClipboard,
		getMessageContentParts,
		createMessagesList,
		getPromptVariables,
		processDetails,
		removeAllDetails,
		getCodeBlockContents,
		isYoutubeUrl,
		displayFileHandler
	} from '$lib/utils';
	import { AudioQueue } from '$lib/utils/audio';

	import {
		createNewChat,
		getAllTags,
		getChatById,
		getChatList,
		getPinnedChatList,
		getTagsById,
		updateChatById,
		updateChatFolderIdById
	} from '$lib/apis/chats';
	import { generateOpenAIChatCompletion } from '$lib/apis/openai';
	import { processWeb, processWebSearch, processYoutubeVideo } from '$lib/apis/retrieval';
	import { getAndUpdateUserLocation, getUserSettings, updateUserSettings } from '$lib/apis/users';
	import {
		chatCompleted,
		generateQueries,
		chatAction,
		generateMoACompletion,
		stopTask,
		getTaskIdsByChatId,
		getModels
	} from '$lib/apis';
	import { getTools } from '$lib/apis/tools';
	import { getModelById } from '$lib/apis/models';
	import { uploadFile } from '$lib/apis/files';
	import { createOpenAITextStream } from '$lib/apis/streaming';
	import {
		getLoadedLocalModels,
		getMmProjFiles,
		loadLocalModel,
		normalizeLlamaCppErrorMessage,
		unloadLocalModel,
		type LocalModel
	} from '$lib/apis/llamacpp';
	import { findMatchingMmproj } from '$lib/utils/mmproj';
	import { getLocalModelLoadPreferences, LOCAL_MODEL_CONTEXT_OPTIONS } from '$lib/utils/llamacppLoadPreferences';
	import { getFunctions } from '$lib/apis/functions';
	import { updateFolderById } from '$lib/apis/folders';

	import Banner from '../common/Banner.svelte';
	import MessageInput from '$lib/components/chat/MessageInput.svelte';
	import Messages from '$lib/components/chat/Messages.svelte';
	import Navbar from '$lib/components/chat/Navbar.svelte';
	import ChatControls from './ChatControls.svelte';
	import ModelSettingsSheet from './ModelSettingsSheet.svelte';
	import EventConfirmDialog from '../common/ConfirmDialog.svelte';
	import Placeholder from './Placeholder.svelte';
	import FilesOverlay from './MessageInput/FilesOverlay.svelte';
	import NotificationToast from '../NotificationToast.svelte';
	import Spinner from '../common/Spinner.svelte';
	import Tooltip from '../common/Tooltip.svelte';
	import Sidebar from '../icons/Sidebar.svelte';
	import Image from '../common/Image.svelte';
	import { getBanners } from '$lib/apis/configs';

	export let chatIdProp = '';

	let loading = true;

	const eventTarget = new EventTarget();
	let controlPane: Pane | undefined;
	let controlPaneComponent: ChatControls | undefined;

	let messageInput: MessageInput | undefined;

	let autoScroll = true;
	let anchoredGeneratingMessageId: string | null = null;
	let showScrollToBottomButton = false;
	let scrollToBottomButtonSuppressUntil = 0;
	let scrollToBottomButtonSuppressTimer: ReturnType<typeof setTimeout> | null = null;
	let generationBottomSpacerHeight = 0;
	let scrollStateRAF: ReturnType<typeof requestAnimationFrame> | null = null;
	let generationAnchorRAF: ReturnType<typeof requestAnimationFrame>[] = [];
	let generationSpacerRAF: ReturnType<typeof requestAnimationFrame> | null = null;
	let generationSpacerScrollLimit: number | null = null;
	let generationSpacerScrollAllowance: number | null = null;
	let activeGenerationSpacerHeightLimit: number | null = null;
	let lastMessagesScrollTop = 0;
	let generationSpacerUpwardScrollIntentUntil = 0;
	let messagesBottomWheelLockUntil = 0;
	let messagesBottomWheelLockRAF: ReturnType<typeof requestAnimationFrame> | null = null;
	let processing = '';
	let messagesContainerElement: HTMLDivElement;

	let navbarElement;

	let showEventConfirmation = false;
	let eventConfirmationTitle = '';
	let eventConfirmationMessage = '';
	let eventConfirmationInput = false;
	let eventConfirmationInputPlaceholder = '';
	let eventConfirmationInputValue = '';
	let eventConfirmationInputType = '';
	let eventCallback = null;

	let selectedModels = [''];
	let atSelectedModel: Model | undefined;
	let selectedModelIds = [];
	$: if (atSelectedModel !== undefined) {
		selectedModelIds = [atSelectedModel.id];
	} else {
		selectedModelIds = selectedModels;
	}

	let selectedToolIds = [];
	let selectedFilterIds = [];

	let imageGenerationEnabled = false;
	let webSearchEnabled = false;
	let deepSearchEnabled = false;
	let codeExecutionEnabled = false;
	let stableDiffusionEnabled = false;
	let musicGenerationEnabled = false;
	let previousMediaGenerationEnabled = stableDiffusionEnabled || musicGenerationEnabled;
	let stableDiffusionStandbyModel: LocalModel | null = null;
	let restoringStableDiffusionStandbyModel = false;
	let thinkingEnabled = true;
	let thinkingExtendedEnabled = true;

	// Sincronizar toggle do chat com a store — controla auto-show de artifacts
	$: chatCodeExecutionEnabled.set(codeExecutionEnabled);

	let showCommands = false;

	let generating = false;
	let modelLoading = false;
	let dragged = false;
	let generationController = null;

	const USER_MESSAGE_ANCHOR_TOP_OFFSET_PX = 128;
	const getGenerationBottomReadingPadding = () =>
		Math.round(
			Math.min(220, Math.max(120, (messagesContainerElement?.clientHeight ?? 640) * 0.24))
		);

	// Content buffer system: accumulate streaming content in plain JS (outside Svelte 5 proxy)
	// to avoid triggering deep reactivity on every token.
	const _contentBuffers = new Map();
	let _flushRAF = null;
	const CODE_BLOCK_SCROLL_INTERVAL_MS = 64;
	let codeBlockScrollTimer = null;
	let lastCodeBlockScrollAt = 0;

	const hasOpenCodeFence = (value = '') => {
		const text = typeof value === 'string' ? value : '';
		const fences = text.match(/(^|\n)(`{3,}|~{3,})/g);
		return Boolean(fences && fences.length % 2 === 1);
	};

	const isStreamingOpenCodeBlock = (messageId = history?.currentId) => {
		const message = history?.messages?.[messageId];
		if (!message || message.role !== 'assistant' || message.done === true) {
			return false;
		}

		return hasOpenCodeFence(_contentBuffers.get(messageId) ?? message.content ?? '');
	};

	const scheduleStreamingAwareScrollToBottom = (messageId = history?.currentId) => {
		if (!isStreamingOpenCodeBlock(messageId)) {
			scheduleScrollToBottom();
			return;
		}

		const now = performance.now();
		const remaining = Math.max(0, CODE_BLOCK_SCROLL_INTERVAL_MS - (now - lastCodeBlockScrollAt));

		if (!codeBlockScrollTimer) {
			codeBlockScrollTimer = setTimeout(() => {
				codeBlockScrollTimer = null;
				lastCodeBlockScrollAt = performance.now();
				scheduleScrollToBottom();
			}, remaining);
		}
	};

	const flushContentBuffers = () => {
		let hasChanges = false;
		let changedMessageId = null;
		for (const [msgId, bufContent] of _contentBuffers) {
			if (history.messages[msgId] && history.messages[msgId].content !== bufContent) {
				history.messages[msgId].content = bufContent;
				history.messages[msgId] = history.messages[msgId];
				hasChanges = true;
				changedMessageId = msgId;
			}
		}
		if (hasChanges) {
			scheduleScrollStateUpdate({ updateAutoScroll: !anchoredGeneratingMessageId });
			scheduleGenerationSpacerFit();
			if (autoScroll && !anchoredGeneratingMessageId) {
				scheduleStreamingAwareScrollToBottom(changedMessageId);
			}
		}
		// Continue RAF loop while buffers exist
		if (_contentBuffers.size > 0) {
			_flushRAF = requestAnimationFrame(flushContentBuffers);
		} else {
			_flushRAF = null;
		}
	};

	const startContentFlush = () => {
		if (!_flushRAF) {
			_flushRAF = requestAnimationFrame(flushContentBuffers);
		}
	};

	const stopContentFlush = (msgId) => {
		_contentBuffers.delete(msgId);
		if (_contentBuffers.size === 0 && _flushRAF) {
			cancelAnimationFrame(_flushRAF);
			_flushRAF = null;
		}
	};

	const normalizeContextSizeErrorMessage = (message: unknown) => {
		const text = `${message ?? ''}`;
		const lower = text.toLowerCase();
		if (
			lower.includes('exceed_context_size_error') ||
			lower.includes('exceeds the available context size') ||
			(lower.includes('n_prompt_tokens') && lower.includes('n_ctx'))
		) {
			return 'A solicitação excede a quantidade de tokens disponíveis. Aumente e tente novamente.';
		}
		return text;
	};

	let chat = null;
	let tags = [];

	let history = {
		messages: {},
		currentId: null
	};

	let taskIds = null;

	// Chat Input
	let prompt = '';
	let chatFiles = [];
	let files = [];
	let params = {};

	// ── Context size modal state (for auto-loading on send) ──
	let showContextModal = false;
	let contextModalSize = 8192;
	let contextModalModelName = '';
	let contextModalResolve: ((size: number | null) => void) | null = null;
	let showVisionModal = false;
	let visionModalModelName = '';
	let visionModalResolve: ((useVision: boolean) => void) | null = null;

	function openContextModal(modelName: string): Promise<number | null> {
		contextModalModelName = modelName;
		contextModalSize = 8192;
		showContextModal = true;
		return new Promise((resolve) => {
			contextModalResolve = resolve;
		});
	}

	function confirmContextModal() {
		showContextModal = false;
		if (contextModalResolve) {
			contextModalResolve(contextModalSize);
			contextModalResolve = null;
		}
	}

	function cancelContextModal() {
		showContextModal = false;
		if (contextModalResolve) {
			contextModalResolve(null);
			contextModalResolve = null;
		}
	}

	const hasActiveChatResponse = () => {
		const currentMessage = history?.currentId ? history.messages[history.currentId] : null;
		return Boolean(
			taskIds ||
			generating ||
			(currentMessage?.role === 'assistant' && currentMessage?.done !== true)
		);
	};

	const showLocalModelLoadError = (err: any) => {
		const error = normalizeLlamaCppErrorMessage(err, 'Falha ao carregar modelo');
		if (error.includes('Predição de tokens')) {
			toast.error(error);
			return;
		}

		toast.error($i18n.t('Failed to verify/load model: {{error}}', { error }));
	};

	const restoreStableDiffusionStandbyModel = async () => {
		if (restoringStableDiffusionStandbyModel || !stableDiffusionStandbyModel) return;
		if (stableDiffusionEnabled || musicGenerationEnabled || hasActiveChatResponse()) return;

		const standbyModel = stableDiffusionStandbyModel;
		restoringStableDiffusionStandbyModel = true;
		modelLoading = true;

		try {
			const loadedModels = await getLoadedLocalModels(localStorage.token);
			if (loadedModels.some((loadedModel) => loadedModel.id === standbyModel.id)) {
				stableDiffusionStandbyModel = null;
				return;
			}

			const currentlyLoaded = loadedModels[0] ?? null;
			toast.info($i18n.t('Loading model... Please wait.'));

			if (currentlyLoaded) {
				try {
					await unloadLocalModel(localStorage.token, currentlyLoaded.id);
				} catch (unloadErr) {
					console.warn('Could not explicitly unload previous model (may already be inactive):', unloadErr);
				}
			}

			const standbyLoadPreferences = getLocalModelLoadPreferences();
			const standbyCacheType =
				standbyLoadPreferences.cache === 'default' ? 'f16' : standbyLoadPreferences.cache;
			const standbyContextShift = normalizeLocalContextShift(
				standbyModel.context_shift ?? standbyLoadPreferences.contextShift
			);
			const standbyTokenPrediction = normalizeLocalTokenPrediction(
				standbyModel.token_prediction ?? standbyLoadPreferences.tokenPrediction
			);
			const standbySpeculativePreference =
				standbyModel.speculative_decoding ?? standbyLoadPreferences.speculative;
			const standbySpeculativeDecoding = isLocalContextShiftEnabled(standbyContextShift) || isLocalTokenPredictionEnabled(standbyTokenPrediction)
				? 'off'
				: normalizeLocalSpeculativeDecoding(standbySpeculativePreference);

			await loadLocalModel(
				localStorage.token,
				standbyModel.filename,
				standbyModel.n_gpu_layers ?? -1,
				standbyModel.n_ctx ?? 8192,
				standbyModel.mmproj_filename ?? null,
				standbyCacheType,
				standbySpeculativeDecoding,
				isLocalContextShiftEnabled(standbyContextShift) ? 'off' : standbyTokenPrediction,
				standbyContextShift
			);

			stableDiffusionStandbyModel = null;
			models.set(await getModels(localStorage.token, null, false, true));
			toast.success($i18n.t('Model loaded successfully!'));
		} catch (err: any) {
			console.error('Failed to restore Stable Diffusion standby model:', err);
			showLocalModelLoadError(err);
		} finally {
			restoringStableDiffusionStandbyModel = false;
			modelLoading = false;
		}
	};

	$: {
		const mediaGenerationEnabled = stableDiffusionEnabled || musicGenerationEnabled;
		if (previousMediaGenerationEnabled && !mediaGenerationEnabled) {
			void restoreStableDiffusionStandbyModel();
		}
		previousMediaGenerationEnabled = mediaGenerationEnabled;
	}

	function openVisionModal(modelName: string): Promise<boolean> {
		visionModalModelName = modelName;
		showVisionModal = true;
		return new Promise((resolve) => {
			visionModalResolve = resolve;
		});
	}

	function confirmVisionModal() {
		showVisionModal = false;
		if (visionModalResolve) {
			visionModalResolve(true);
			visionModalResolve = null;
		}
	}

	function declineVisionModal() {
		showVisionModal = false;
		if (visionModalResolve) {
			visionModalResolve(false);
			visionModalResolve = null;
		}
	}

	// Message queue for storing messages while generating
	let messageQueue: { id: string; prompt: string; files: any[] }[] = [];

	$: if (chatIdProp) {
		navigateHandler();
	}

	const navigateHandler = async () => {
		loading = true;

		// Save current queue to sessionStorage before navigating away
		if (messageQueue.length > 0 && $chatId) {
			sessionStorage.setItem(`chat-queue-${$chatId}`, JSON.stringify(messageQueue));
		}

		prompt = '';
		messageInput?.setText('');

		files = [];
		messageQueue = [];
		selectedToolIds = [];
		selectedFilterIds = [];
		webSearchEnabled = false;
		deepSearchEnabled = false;
		imageGenerationEnabled = false;
		stableDiffusionEnabled = false;
		musicGenerationEnabled = false;

		const storageChatInput = sessionStorage.getItem(
			`chat-input${chatIdProp ? `-${chatIdProp}` : ''}`
		);

		if (chatIdProp && (await loadChat())) {
			await tick();
			loading = false;
			window.setTimeout(() => scrollToBottom(), 0);

			await tick();

			// Sync model params into Chat Controls after chat (and its saved params) are loaded
			await setDefaults();

			// Restore queue from sessionStorage
			const storedQueueData = sessionStorage.getItem(`chat-queue-${chatIdProp}`);
			if (storedQueueData) {
				try {
					const restoredQueue = JSON.parse(storedQueueData);

					if (restoredQueue.length > 0) {
						sessionStorage.removeItem(`chat-queue-${chatIdProp}`);
						// Check if there are pending tasks (still generating)
						const hasPendingTask = taskIds !== null && taskIds.length > 0;
						if (!hasPendingTask) {
							// No pending tasks - process the queue
							files = restoredQueue.flatMap((m) => m.files);
							await tick();
							const combinedPrompt = restoredQueue.map((m) => m.prompt).join('\n\n');
							await submitPrompt(combinedPrompt);
						} else {
							// Has pending tasks - show as queued (chatCompletedHandler will process)
							messageQueue = restoredQueue;
						}
					}
				} catch (e) {}
			}

			if (storageChatInput) {
				try {
					const input = JSON.parse(storageChatInput);

					if (!$temporaryChatEnabled) {
						messageInput?.setText(input.prompt);
						files = input.files;
						selectedToolIds = input.selectedToolIds;
						selectedFilterIds = input.selectedFilterIds;
						webSearchEnabled = input.webSearchEnabled;
						deepSearchEnabled = input.deepSearchEnabled ?? false;
						imageGenerationEnabled = input.imageGenerationEnabled;
						codeExecutionEnabled = input.codeExecutionEnabled ?? false;
						stableDiffusionEnabled = input.stableDiffusionEnabled ?? false;
						musicGenerationEnabled = input.musicGenerationEnabled ?? false;
						normalizeExclusiveFeatureToggles();
						thinkingExtendedEnabled = input.thinkingExtendedEnabled ?? thinkingExtendedEnabled;
					}
				} catch (e) {}
			}

			const chatInput = document.getElementById('chat-input');
			chatInput?.focus();
		} else {
			await goto('/');
		}
	};

	const onSelect = async (e) => {
		const { type, data } = e;

		if (type === 'prompt') {
			// Handle prompt selection
			messageInput?.setText(data, async () => {
				if (!($settings?.insertSuggestionPrompt ?? false)) {
					await tick();
					submitPrompt(prompt);
				}
			});
		}
	};

	$: if (selectedModels && chatIdProp !== '') {
		saveSessionSelectedModels();
	}

	const saveSessionSelectedModels = () => {
		const selectedModelsString = JSON.stringify(selectedModels);
		if (
			selectedModels.length === 0 ||
			(selectedModels.length === 1 && selectedModels[0] === '') ||
			sessionStorage.selectedModels === selectedModelsString
		) {
			return;
		}
		sessionStorage.selectedModels = selectedModelsString;
		// Auto-save last used model(s) to settings (replaces manual 'Set as default')
		const newSettings = { ...$settings, models: selectedModels };
		settings.set(newSettings);
		updateUserSettings(localStorage.token, { ui: newSettings }).catch(() => {});
		console.log('saveSessionSelectedModels', selectedModels, sessionStorage.selectedModels);
	};

	let oldSelectedModelIds = [''];
	$: if (JSON.stringify(selectedModelIds) !== JSON.stringify(oldSelectedModelIds)) {
		onSelectedModelIdsChange();
	}

	const onSelectedModelIdsChange = () => {
		resetInput();
		oldSelectedModelIds = structuredClone(selectedModelIds);
	};

	const resetInput = () => {
		selectedToolIds = [];
		selectedFilterIds = [];
		webSearchEnabled = false;
		deepSearchEnabled = false;
		imageGenerationEnabled = false;
		codeExecutionEnabled = false;
		stableDiffusionEnabled = false;
		musicGenerationEnabled = false;
		params = {};

		if (selectedModelIds.filter((id) => id).length > 0) {
			setDefaults();
		}
	};

	type ChatIntegrationId =
		| 'web_search'
		| 'deep_search'
		| 'image_generation'
		| 'code_execution'
		| 'stable_diffusion'
		| 'music_generation';

	const normalizeExclusiveFeatureToggles = (preferred?: ChatIntegrationId) => {
		const enabledIntegrations: ChatIntegrationId[] = [
			webSearchEnabled ? 'web_search' : null,
			deepSearchEnabled ? 'deep_search' : null,
			imageGenerationEnabled ? 'image_generation' : null,
			codeExecutionEnabled ? 'code_execution' : null,
			stableDiffusionEnabled ? 'stable_diffusion' : null,
			musicGenerationEnabled ? 'music_generation' : null
		].filter(Boolean) as ChatIntegrationId[];

		if (enabledIntegrations.length > 0) {
			const keep = preferred && enabledIntegrations.includes(preferred)
				? preferred
				: enabledIntegrations.at(-1);

			webSearchEnabled = keep === 'web_search';
			deepSearchEnabled = keep === 'deep_search';
			imageGenerationEnabled = keep === 'image_generation';
			codeExecutionEnabled = keep === 'code_execution';
			stableDiffusionEnabled = keep === 'stable_diffusion';
			musicGenerationEnabled = keep === 'music_generation';
			selectedToolIds = [];
			selectedFilterIds = [];
			return;
		}

		if (selectedFilterIds.length > 0) {
			selectedFilterIds = [selectedFilterIds.at(-1)];
			selectedToolIds = [];
			return;
		}

		if (selectedToolIds.length > 1) {
			selectedToolIds = [selectedToolIds.at(-1)];
		}
	};

	const setDefaults = async () => {
		if (!$tools) {
			tools.set(await getTools(localStorage.token));
		}
		if (!$functions) {
			functions.set(await getFunctions(localStorage.token));
		}
		if (selectedModels.length !== 1 && !atSelectedModel) {
			return;
		}

		const model = atSelectedModel ?? $models.find((m) => m.id === selectedModels[0]);
		if (model) {
			// Set Default Tools
			if (model?.info?.meta?.toolIds) {
				selectedToolIds = [
					...new Set(
						[...(model?.info?.meta?.toolIds ?? [])].filter((id) => $tools.find((t) => t.id === id))
					)
				];
			} else if ($settings?.tools) {
				selectedToolIds = $settings.tools;
			} else {
				selectedToolIds = selectedToolIds.filter((id) => !id.startsWith('direct_server:'));
			}

			// Set Default Filters (Toggleable only)
			if (model?.info?.meta?.defaultFilterIds) {
				selectedFilterIds = model.info.meta.defaultFilterIds.filter((id) =>
					model?.filters?.find((f) => f.id === id)
				);
			}

			// Set Default Features
			if (model?.info?.meta?.defaultFeatureIds) {
				deepSearchEnabled = Boolean(
					model.info.meta.defaultFeatureIds.includes('deep_search') &&
					$config?.features?.enable_web_search &&
					($user?.role === 'admin' || $user?.permissions?.features?.web_search)
				);

				if (
					model.info?.meta?.capabilities?.['image_generation'] &&
					$config?.features?.enable_image_generation &&
					($user?.role === 'admin' || $user?.permissions?.features?.image_generation)
				) {
					imageGenerationEnabled = model.info.meta.defaultFeatureIds.includes('image_generation');
				}

				if (
					model.info?.meta?.capabilities?.['web_search'] &&
					$config?.features?.enable_web_search &&
					($user?.role === 'admin' || $user?.permissions?.features?.web_search)
				) {
					webSearchEnabled = model.info.meta.defaultFeatureIds.includes('web_search');
				}

				if ($config?.features?.enable_code_execution) {
					codeExecutionEnabled = model.info.meta.defaultFeatureIds?.includes('code_execution') ?? false;
				}

				if (
					$config?.features?.enable_stable_diffusion &&
					($user?.role === 'admin' || $user?.permissions?.features?.stable_diffusion)
				) {
					stableDiffusionEnabled = model.info.meta.defaultFeatureIds?.includes('stable_diffusion') ?? false;
				}
			}

			normalizeExclusiveFeatureToggles();

	        // Auto-populate Chat Controls params from model settings
			// model.info.params is stripped by the backend for security; fetch full model via dedicated API
			if (Object.keys(params).length === 0) {
				try {
					const fullModel = await getModelById(localStorage.token, model.id);
					const modelParams = fullModel?.params ?? {};
					const samplingKeys = [
						'system', 'temperature', 'top_p', 'top_k', 'min_p', 'max_tokens',
						'repeat_penalty', 'frequency_penalty', 'presence_penalty',
						'mirostat', 'mirostat_eta', 'mirostat_tau', 'seed', 'stop',
						'xtc_threshold', 'xtc_probability', 'dry_multiplier',
						'dry_allowed_length', 'dry_base',
						'reasoning_tags', 'num_ctx'
					];
					const populated: Record<string, any> = {};
					for (const key of samplingKeys) {
						const v = (modelParams as any)[key];
						if (v !== undefined && v !== null && v !== '') {
							populated[key] = v;
						}
					}
					if (Object.keys(populated).length > 0) {
						params = { ...params, ...populated };
					}
				} catch (_) {
					// Base Ollama/OpenAI models have no custom model entry — skip silently
				}
			}
		}
	};

	const showMessage = async (message, scroll = true) => {
		const _chatId = JSON.parse(JSON.stringify($chatId));
		let _messageId = JSON.parse(JSON.stringify(message.id));

		let messageChildrenIds = [];
		if (_messageId === null) {
			messageChildrenIds = Object.keys(history.messages).filter(
				(id) => history.messages[id].parentId === null
			);
		} else {
			messageChildrenIds = history.messages[_messageId].childrenIds;
		}

		while (messageChildrenIds.length !== 0) {
			_messageId = messageChildrenIds.at(-1);
			messageChildrenIds = history.messages[_messageId].childrenIds;
		}

		history.currentId = _messageId;

		await tick();

		if (($settings?.scrollOnBranchChange ?? true) && scroll) {
			const messageElement = document.getElementById(`message-${message.id}`);
			if (messageElement) {
				messageElement.scrollIntoView({ behavior: 'smooth', block: 'start' });
			}
		}

		await tick();
		await tick();
		await tick();

		saveChatHandler(_chatId, history);
	};

	const terminalEventHandler = (type: string, data: any) => {
		if (type === 'terminal:display_file') {
			if (!data?.path) return;
			displayFileHandler(data.path, { showControls, showFileNavPath });
		} else if (type === 'terminal:write_file' || type === 'terminal:replace_file_content') {
			if (!data?.path) return;
			showFileNavDir.set(data.path);
		} else if (type === 'terminal:run_command') {
			showFileNavDir.set('/');
		}
	};

	const chatEventHandler = async (event, cb) => {
		if (event.chat_id === $chatId) {
			const type = event?.data?.type ?? null;
			const data = event?.data?.data ?? null;

			// Skip tick() for high-frequency streaming events to prevent backlog
			if (type !== 'chat:completion' && type !== 'chat:message:delta' && type !== 'message') {
				await tick();
			}

			let message = history.messages[event.message_id];

			if (message) {
				if (type === 'status') {
					if (message?.statusHistory) {
						message.statusHistory.push(data);
					} else {
						message.statusHistory = [data];
					}
					history.messages[event.message_id] = message;
				} else if (type === 'chat:completion') {
					chatCompletionEventHandler(data, message, event.chat_id);
					return; // handled by chatCompletionEventHandler
				} else if (type === 'chat:tasks:cancel') {
					taskIds = null;
					const responseMessage = history.messages[history.currentId];
					// Set all response messages to done
					for (const messageId of history.messages[responseMessage.parentId].childrenIds) {
						history.messages[messageId].done = true;
						releaseGeneratingMessageAnchor(messageId);
					}
				} else if (type === 'chat:message:delta' || type === 'message') {
					// Buffer content outside Svelte proxy to avoid reactive cascade per token
					if (!_contentBuffers.has(event.message_id)) {
						_contentBuffers.set(event.message_id, message.content ?? '');
					}
					_contentBuffers.set(event.message_id, _contentBuffers.get(event.message_id) + data.content);
					startContentFlush();
					return; // handled by content buffer flush
				} else if (type === 'chat:message' || type === 'replace') {
					message.content = data.content;
				} else if (type === 'chat:message:files' || type === 'files') {
					message.files = data.files;
				} else if (type === 'chat:message:embeds' || type === 'embeds') {
					message.embeds = data.embeds;

					// Auto-scroll to the embed once it's rendered in the DOM
					await tick();
					setTimeout(() => {
						const embedEl = document.getElementById(`${event.message_id}-embeds-container`);
						if (embedEl) {
							embedEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
						}
					}, 100);
				} else if (type === 'chat:message:error') {
					if (typeof data?.error?.content === 'string') {
						data.error.content = normalizeContextSizeErrorMessage(data.error.content);
					}
					message.error = data.error;
				} else if (type === 'chat:message:favorite') {
					// Update message favorite status
					message.favorite = data.favorite;
				} else if (type === 'chat:tags') {
					chat = await getChatById(localStorage.token, $chatId);
					allTags.set(await getAllTags(localStorage.token));
				} else if (type === 'source' || type === 'citation') {
					if (data?.type === 'code_execution') {
						// Code execution; update existing code execution by ID, or add new one.
						if (!message?.code_executions) {
							message.code_executions = [];
						}

						const existingCodeExecutionIndex = message.code_executions.findIndex(
							(execution) => execution.id === data.id
						);

						if (existingCodeExecutionIndex !== -1) {
							message.code_executions[existingCodeExecutionIndex] = data;
						} else {
							message.code_executions.push(data);
						}

						message.code_executions = message.code_executions;
					} else {
						// Regular source.
						if (message?.sources) {
							message.sources.push(data);
						} else {
							message.sources = [data];
						}
					}
				} else if (type === 'notification') {
					const toastType = data?.type ?? 'info';
					const toastContent = data?.content ?? '';

					if (toastType === 'success') {
						toast.success(toastContent);
					} else if (toastType === 'error') {
						toast.error(toastContent);
					} else if (toastType === 'warning') {
						toast.warning(toastContent);
					} else {
						toast.info(toastContent);
					}
				} else if (type === 'confirmation') {
					eventCallback = cb;

					eventConfirmationInput = false;
					showEventConfirmation = true;

					eventConfirmationTitle = data.title;
					eventConfirmationMessage = data.message;
				} else if (type === 'execute') {
					eventCallback = cb;

					try {
						// Use Function constructor to evaluate code in a safer way
						const asyncFunction = new Function(`return (async () => { ${data.code} })()`);
						const result = await asyncFunction(); // Await the result of the async function

						if (cb) {
							cb(result);
						}
					} catch (error) {
						console.error('Error executing code:', error);
					}
				} else if (type === 'input') {
					eventCallback = cb;

					eventConfirmationInput = true;
					showEventConfirmation = true;

					eventConfirmationTitle = data.title;
					eventConfirmationMessage = data.message;
					eventConfirmationInputPlaceholder = data.placeholder;
					eventConfirmationInputValue = data?.value ?? '';
					eventConfirmationInputType = data?.type ?? '';
				} else if (type.startsWith('terminal:')) {
					terminalEventHandler(type, data);
				} else {
					console.log('Unknown message type', data);
				}

				// Skip reactive trigger for chat:completion — handled by chatCompletionEventHandler with RAF throttling
				if (type !== 'chat:completion') {
					history.messages[event.message_id] = message;
				}
			}
		}
	};

	const onMessageHandler = async (event: {
		origin: string;
		data: { type: string; text: string };
	}) => {
		if (event.origin !== window.origin) {
			return;
		}

		if (event.data.type === 'action:submit') {
			console.debug(event.data.text);

			if (prompt !== '') {
				await tick();
				submitPrompt(prompt);
			}
		}

		// Replace with your iframe's origin
		if (event.data.type === 'input:prompt') {
			console.debug(event.data.text);

			const inputElement = document.getElementById('chat-input');

			if (inputElement) {
				messageInput?.setText(event.data.text);
				inputElement.focus();
			}
		}

		if (event.data.type === 'input:prompt:submit') {
			console.debug(event.data.text);

			if (event.data.text !== '') {
				await tick();
				submitPrompt(event.data.text);
			}
		}
	};

	const savedModelIds = async () => {
		if (
			$selectedFolder &&
			selectedModels.filter((modelId) => modelId !== '').length > 0 &&
			JSON.stringify($selectedFolder?.data?.model_ids) !== JSON.stringify(selectedModels)
		) {
			const res = await updateFolderById(localStorage.token, $selectedFolder.id, {
				data: {
					model_ids: selectedModels
				}
			});
		}
	};

	$: if (selectedModels !== null) {
		savedModelIds();
	}

	const stopAudio = () => {
		try {
			speechSynthesis.cancel();
			$audioQueue?.stop();
		} catch {}
	};

	let stopChatRenderDebug: (() => void) | null = null;

	const startChatRenderDebug = () => {
		if (localStorage.getItem('NEVE_CHAT_RENDER_DEBUG') !== '1') {
			return null;
		}

		const debugPrefix = '[NEVE_CHAT_RENDER_DEBUG]';
		const root = document.documentElement;
		const style = document.createElement('style');
		const panel = document.createElement('div');
		const observedElements = new Map<Element, { label: string; width: number; height: number }>();
		const displayLines: string[] = [];
		const reportLines: string[] = [];
		let refreshFrame: ReturnType<typeof requestAnimationFrame> | null = null;
		let scrollElement: HTMLElement | null = null;
		let lastScrollTop = 0;
		let scrollFrame: ReturnType<typeof requestAnimationFrame> | null = null;
		let scrollAttachTimer: ReturnType<typeof setInterval> | null = null;
		let performanceObserver: any = null;
		let captureFrame: ReturnType<typeof requestAnimationFrame> | null = null;
		let captureUntil = 0;
		let captureLastKey = '';
		let originalScrollIntoView: any = null;
		let originalScrollTo: any = null;
		let wheelSequence = 0;

		const formatNumber = (value: number) => Math.round(value * 10) / 10;
		const formatRect = (rect?: DOMRect | DOMRectReadOnly | null) => {
			if (!rect) return null;
			return {
				x: formatNumber(rect.x),
				y: formatNumber(rect.y),
				width: formatNumber(rect.width),
				height: formatNumber(rect.height),
				top: formatNumber(rect.top),
				right: formatNumber(rect.right),
				bottom: formatNumber(rect.bottom),
				left: formatNumber(rect.left)
			};
		};
		const getElementPath = (element: Element | null) => {
			if (!element) return null;
			const parts: string[] = [];
			let current: Element | null = element;

			for (let index = 0; current && index < 7; index += 1) {
				let part = current.tagName.toLowerCase();
				if (current.id) {
					part += `#${current.id}`;
				} else {
					const classes = [...current.classList].slice(0, 4);
					if (classes.length > 0) {
						part += `.${classes.join('.')}`;
					}
				}
				parts.unshift(part);
				current = current.parentElement;
			}

			return parts.join(' > ');
		};
		const getTextSnippet = (element: Element | null) => {
			const text = element?.textContent?.replace(/\s+/g, ' ').trim() ?? '';
			return text.length > 100 ? `${text.slice(0, 100)}...` : text;
		};
		const getElementDebugInfo = (element: Element | null) => {
			if (!element) return null;
			const rect = element.getBoundingClientRect();
			const style = element instanceof HTMLElement ? getComputedStyle(element) : null;

			return {
				label: getElementLabel(element),
				path: getElementPath(element),
				rect: formatRect(rect),
				className: element.className?.toString?.() ?? '',
				text: getTextSnippet(element),
				scrollTop: element instanceof HTMLElement ? formatNumber(element.scrollTop) : undefined,
				scrollHeight:
					element instanceof HTMLElement ? formatNumber(element.scrollHeight) : undefined,
				clientHeight:
					element instanceof HTMLElement ? formatNumber(element.clientHeight) : undefined,
				style: style
					? {
							display: style.display,
							position: style.position,
							overflow: `${style.overflowX}/${style.overflowY}`,
							overflowAnchor: style.overflowAnchor,
							transform: style.transform,
							contain: style.contain,
							contentVisibility: style.contentVisibility,
							willChange: style.willChange
						}
					: undefined
			};
		};
		const elementFromRect = (rect?: DOMRect | DOMRectReadOnly | null) => {
			if (!rect || rect.width <= 0 || rect.height <= 0) return null;
			const x = Math.min(window.innerWidth - 1, Math.max(0, rect.left + rect.width / 2));
			const y = Math.min(window.innerHeight - 1, Math.max(0, rect.top + rect.height / 2));
			return document.elementFromPoint(x, y);
		};
		const getScrollDebugMetrics = (element: HTMLElement | null) => {
			if (!element) return null;
			const maxScrollTop = Math.max(0, element.scrollHeight - element.clientHeight);
			const scrollBottom = element.scrollTop + element.clientHeight;
			const bottomGap = maxScrollTop - element.scrollTop;

			return {
				scrollTop: formatNumber(element.scrollTop),
				clientHeight: formatNumber(element.clientHeight),
				scrollHeight: formatNumber(element.scrollHeight),
				scrollBottom: formatNumber(scrollBottom),
				maxScrollTop: formatNumber(maxScrollTop),
				bottomGap: formatNumber(bottomGap),
				atBottom: Math.abs(bottomGap) <= 1,
				overscroll: formatNumber(element.scrollTop - maxScrollTop)
			};
		};
		const getBottomContentDebugInfo = (container: HTMLElement | null) => {
			if (!container) return null;

			const containerRect = container.getBoundingClientRect();
			const directChildren = [...container.children].slice(-6).map((child) => ({
				label: getElementLabel(child),
				rect: formatRect(child.getBoundingClientRect()),
				text: getTextSnippet(child)
			}));
			const messages = [...container.querySelectorAll('[id^="message-"]')].slice(-6).map((message) => {
				const rect = message.getBoundingClientRect();
				return {
					label: getElementLabel(message),
					rect: formatRect(rect),
					distanceToContainerBottom: formatNumber(containerRect.bottom - rect.bottom),
					text: getTextSnippet(message)
				};
			});
			const bottomElement = document.elementFromPoint(
				Math.min(window.innerWidth - 1, Math.max(0, containerRect.left + containerRect.width / 2)),
				Math.min(window.innerHeight - 1, Math.max(0, containerRect.bottom - 4))
			);

			return {
				containerRect: formatRect(containerRect),
				bottomElement: getElementDebugInfo(bottomElement),
				directChildren,
				messages
			};
		};
		const getDebugSnapshot = () => {
			const messagesElement = document.getElementById('messages-container');
			const inputElement = document.getElementById('message-input-container');
			const messagesHTMLElement =
				messagesElement instanceof HTMLElement ? messagesElement : null;
			const currentMessageElement = history?.currentId
				? document.getElementById(`message-${history.currentId}`)
				: null;

			return {
				time: formatNumber(performance.now()),
				url: location.pathname,
				userAgent: navigator.userAgent,
				devicePixelRatio: window.devicePixelRatio,
				viewport: {
					inner: `${window.innerWidth}x${window.innerHeight}`,
					documentElement: `${document.documentElement.clientWidth}x${document.documentElement.clientHeight}`,
					visual: window.visualViewport
						? {
								width: formatNumber(window.visualViewport.width),
								height: formatNumber(window.visualViewport.height),
								offsetTop: formatNumber(window.visualViewport.offsetTop),
								offsetLeft: formatNumber(window.visualViewport.offsetLeft),
								scale: formatNumber(window.visualViewport.scale)
							}
						: null
				},
				state: {
					autoScroll,
					anchoredGeneratingMessageId,
					showScrollToBottomButton,
					generationBottomSpacerHeight,
					generating,
					currentId: history?.currentId
				},
				messagesContainer: getElementDebugInfo(messagesElement),
				messagesScroll: getScrollDebugMetrics(messagesHTMLElement),
				bottomContent: getBottomContentDebugInfo(messagesHTMLElement),
				input: getElementDebugInfo(inputElement),
				currentMessage: getElementDebugInfo(currentMessageElement),
				activeElement: getElementDebugInfo(document.activeElement)
			};
		};
		const getDebugReport = () => reportLines.join('\n');
		const updatePanel = () => {
			panel.textContent = [
				'Neve render debug ON',
				'Copiar: copyNeveChatRenderDebug()',
				'Limpar: clearNeveChatRenderDebug()',
				'Capturar frames: captureNeveChatRenderDebug(5000)',
				'Snapshot: snapshotNeveChatRenderDebug()',
				'Probe fundo: probeNeveChatBottomDebug()',
				'',
				...displayLines
			].join('\n');
		};
		const serializeDebugData = (data: unknown) => {
			if (data === undefined || data === null) return '';
			try {
				return JSON.stringify(data, (_key, value) => {
					if (value instanceof Element) {
						return getElementDebugInfo(value);
					}
					if (value instanceof Window || value instanceof Document) {
						return '[document]';
					}
					return value;
				});
			} catch {
				return String(data);
			}
		};
		const snapshotDebugReport = () => {
			const snapshot = getDebugSnapshot();
			pushLine('snapshot', snapshot);
			return snapshot;
		};
		const probeBottomDebugReport = () => {
			const frames = new Set([1, 2, 4, 8, 16, 32]);
			let frame = 0;
			pushLine('bottom-probe start', getDebugSnapshot());

			const run = () => {
				frame += 1;
				if (frames.has(frame)) {
					pushLine(`bottom-probe frame:${frame}`, getDebugSnapshot());
				}

				if (frame < 32) {
					requestAnimationFrame(run);
				} else {
					pushLine('bottom-probe finished', getDebugSnapshot());
				}
			};

			requestAnimationFrame(run);
			return getDebugSnapshot();
		};
		const stopFrameCapture = () => {
			captureUntil = 0;
			captureLastKey = '';
			if (captureFrame) {
				cancelAnimationFrame(captureFrame);
				captureFrame = null;
			}
			pushLine('frame capture stopped');
		};
		const startFrameCapture = (durationMs = 5000) => {
			captureUntil = performance.now() + Number(durationMs || 5000);
			captureLastKey = '';
			if (captureFrame) {
				cancelAnimationFrame(captureFrame);
			}

			const run = () => {
				const snapshot = getDebugSnapshot();
				const key = JSON.stringify({
					viewport: snapshot.viewport,
					state: snapshot.state,
					messagesContainer: snapshot.messagesContainer?.rect,
					messagesScroll: snapshot.messagesScroll,
					messagesScrollTop: snapshot.messagesContainer?.scrollTop,
					messagesScrollHeight: snapshot.messagesContainer?.scrollHeight,
					input: snapshot.input?.rect,
					currentMessage: snapshot.currentMessage?.rect
				});

				if (key !== captureLastKey) {
					captureLastKey = key;
					pushLine('frame', snapshot);
				}

				if (performance.now() < captureUntil) {
					captureFrame = requestAnimationFrame(run);
				} else {
					captureFrame = null;
					pushLine('frame capture finished');
				}
			};

			pushLine(`frame capture started ${durationMs}ms`);
			captureFrame = requestAnimationFrame(run);
			return 'capturing';
		};
		const copyDebugReport = async () => {
			const report = getDebugReport();
			try {
				await navigator.clipboard.writeText(report);
				console.log(debugPrefix, 'debug report copied');
				return report;
			} catch {
				console.log(debugPrefix, 'debug report copy failed; returning report text');
				return report;
			}
		};
		const clearDebugReport = () => {
			displayLines.length = 0;
			reportLines.length = 0;
			updatePanel();
			console.log(debugPrefix, 'debug report cleared');
		};

		const pushLine = (message: string, data?: unknown) => {
			const timestamp = new Date().toLocaleTimeString('pt-BR', { hour12: false });
			const line = `${timestamp} ${message}`;
			const serializedData = serializeDebugData(data);
			const reportLine = serializedData ? `${line} ${serializedData}` : line;
			displayLines.push(line);
			reportLines.push(reportLine);
			while (displayLines.length > 16) {
				displayLines.shift();
			}
			while (reportLines.length > 5000) {
				reportLines.shift();
			}
			updatePanel();
			console.log(debugPrefix, message, data ?? '');
		};

		const flashElement = (element: Element) => {
			if (!(element instanceof HTMLElement)) return;
			element.classList.add('neve-chat-render-debug-flash');
			window.setTimeout(() => {
				element.classList.remove('neve-chat-render-debug-flash');
			}, 180);
		};

		const getElementLabel = (element: Element) => {
			if (element.id === 'message-input-container') return '#message-input-container';
			if (element.id === 'messages-container') return '#messages-container';
			if (element.id?.startsWith('message-')) return `message:${element.id.replace('message-', '')}`;
			if (element.matches('pre')) return 'codeblock:<pre>';
			if (element.matches('pre code')) return 'codeblock:<code>';
			if (element.classList.contains('markdown-prose')) return 'markdown-prose';
			if (element.classList.contains('chat-assistant')) return 'chat-assistant';
			if (element.classList.contains('chat-user')) return 'chat-user';
			if (element.className?.toString().includes('language-')) return 'codeblock:language';
			if (element.classList.contains('hljs')) return 'codeblock:hljs';
			return element.tagName.toLowerCase();
		};

		const observeElement = (element: Element) => {
			const rect = element.getBoundingClientRect();
			if (rect.width === 0 && rect.height === 0) return;
			if (observedElements.has(element)) return;

			observedElements.set(element, {
				label: getElementLabel(element),
				width: formatNumber(rect.width),
				height: formatNumber(rect.height)
			});
			resizeObserver.observe(element);
		};

		const refreshObservedElements = () => {
			refreshFrame = null;
			const targets = document.querySelectorAll(
				[
					'#messages-container',
					'[id^="message-"]',
					'.markdown-prose',
					'.chat-assistant',
					'.chat-user',
					'pre',
					'pre code',
					'.hljs',
					'[class*="language-"]'
				].join(',')
			);
			targets.forEach(observeElement);
		};

		const scheduleRefreshObservedElements = () => {
			if (refreshFrame) return;
			refreshFrame = requestAnimationFrame(refreshObservedElements);
		};

		const onScroll = () => {
			if (!scrollElement || scrollFrame) return;
			scrollFrame = requestAnimationFrame(() => {
				scrollFrame = null;
				if (!scrollElement) return;
				const nextScrollTop = formatNumber(scrollElement.scrollTop);
				const delta = formatNumber(nextScrollTop - lastScrollTop);
				if (Math.abs(delta) >= 1) {
					pushLine(
						`scrollTop ${lastScrollTop} -> ${nextScrollTop} (delta ${delta})`,
						{
							scroll: getScrollDebugMetrics(scrollElement),
							bottomContent: getBottomContentDebugInfo(scrollElement)
						}
					);
					lastScrollTop = nextScrollTop;
				}
			});
		};
		const logNearBottomWheelFrames = (sequence: number) => {
			const frames = new Set([1, 2, 4, 8, 16]);
			let frame = 0;

			const run = () => {
				frame += 1;
				if (sequence !== wheelSequence) return;

				if (frames.has(frame)) {
					pushLine(`wheel-bottom frame:${frame}`, getDebugSnapshot());
				}

				if (frame < 16) {
					requestAnimationFrame(run);
				}
			};

			requestAnimationFrame(run);
		};
		const onWheel = (event: WheelEvent) => {
			if (!scrollElement) return;

			const metrics = getScrollDebugMetrics(scrollElement);
			if (!metrics || Math.abs(event.deltaY) < 0.5) return;

			const nearBottom = metrics.bottomGap <= 48;
			if (!nearBottom) return;

			wheelSequence += 1;
			const sequence = wheelSequence;
			pushLine(event.deltaY > 0 ? 'wheel-down near-bottom' : 'wheel-up near-bottom', {
				deltaX: formatNumber(event.deltaX),
				deltaY: formatNumber(event.deltaY),
				deltaMode: event.deltaMode,
				cancelable: event.cancelable,
				defaultPrevented: event.defaultPrevented,
				scroll: metrics,
				bottomContent: getBottomContentDebugInfo(scrollElement)
			});
			logNearBottomWheelFrames(sequence);
		};

		const attachScrollDebug = () => {
			const nextScrollElement = document.getElementById('messages-container') as HTMLElement | null;
			if (!nextScrollElement || nextScrollElement === scrollElement) return;

			if (scrollElement) {
				scrollElement.removeEventListener('scroll', onScroll);
				scrollElement.removeEventListener('wheel', onWheel);
			}
			scrollElement = nextScrollElement;
			lastScrollTop = formatNumber(scrollElement.scrollTop);
			scrollElement.addEventListener('scroll', onScroll, { passive: true });
			scrollElement.addEventListener('wheel', onWheel, { passive: true });
			pushLine(`attached scroll observer at ${lastScrollTop}`);
		};

		const resizeObserver = new ResizeObserver((entries) => {
			for (const entry of entries) {
				const previous = observedElements.get(entry.target);
				if (!previous) continue;

				const width = formatNumber(entry.contentRect.width);
				const height = formatNumber(entry.contentRect.height);
				const widthDelta = formatNumber(width - previous.width);
				const heightDelta = formatNumber(height - previous.height);
				if (Math.abs(widthDelta) < 1 && Math.abs(heightDelta) < 1) continue;

				observedElements.set(entry.target, { ...previous, width, height });
				flashElement(entry.target);
				pushLine(
					`resize ${previous.label}: ${previous.width}x${previous.height} -> ${width}x${height}`,
					{
					widthDelta,
					heightDelta,
					element: getElementDebugInfo(entry.target)
				}
			);
		}
	});

		const mutationObserver = new MutationObserver((mutations) => {
			const added: unknown[] = [];
			const removed: unknown[] = [];
			for (const mutation of mutations) {
				mutation.addedNodes.forEach((node) => {
					if (node instanceof Element && added.length < 8) {
						if (
							node.id?.startsWith('message-') ||
							node.id === 'messages-container' ||
							node.matches?.('pre, pre code, .markdown-prose, .chat-assistant, .chat-user')
						) {
							added.push(getElementDebugInfo(node));
						}
					}
				});
				mutation.removedNodes.forEach((node) => {
					if (node instanceof Element && removed.length < 8) {
						if (
							node.id?.startsWith('message-') ||
							node.id === 'messages-container' ||
							node.matches?.('pre, pre code, .markdown-prose, .chat-assistant, .chat-user')
						) {
							removed.push({
								label: getElementLabel(node),
								path: getElementPath(node),
								className: node.className?.toString?.() ?? '',
								text: getTextSnippet(node)
							});
						}
					}
				});
			}

			if (added.length > 0 || removed.length > 0) {
				pushLine(`mutation added:${added.length} removed:${removed.length}`, { added, removed });
			}
			scheduleRefreshObservedElements();
			attachScrollDebug();
		});

		root.classList.add('neve-chat-render-debug');
		style.id = 'neve-chat-render-debug-style';
		style.textContent = `
			html.neve-chat-render-debug #messages-container {
				outline: 2px solid rgba(56, 189, 248, 0.95) !important;
				outline-offset: -2px !important;
			}
			html.neve-chat-render-debug [id^="message-"] {
				outline: 1px dashed rgba(245, 158, 11, 0.95) !important;
				outline-offset: 2px !important;
			}
			html.neve-chat-render-debug .markdown-prose {
				outline: 1px solid rgba(34, 197, 94, 0.75) !important;
				outline-offset: 4px !important;
			}
			html.neve-chat-render-debug pre,
			html.neve-chat-render-debug pre code,
			html.neve-chat-render-debug [class*="language-"] {
				outline: 2px solid rgba(236, 72, 153, 0.75) !important;
				outline-offset: -2px !important;
			}
			html.neve-chat-render-debug .neve-chat-render-debug-flash {
				box-shadow: 0 0 0 3px rgba(239, 68, 68, 0.9) !important;
			}
			#neve-chat-render-debug-panel {
				position: fixed;
				right: 12px;
				bottom: 12px;
				z-index: 2147483647;
				width: min(520px, calc(100vw - 24px));
				height: min(42vh, 420px);
				overflow: hidden;
				padding: 10px 12px;
				border-radius: 8px;
				border: 1px solid rgba(255, 255, 255, 0.18);
				background: rgba(10, 10, 10, 0.88);
				color: #f8fafc;
				font: 11px/1.35 ui-monospace, SFMono-Regular, Consolas, monospace;
				white-space: pre-wrap;
				pointer-events: none;
				box-shadow: 0 12px 40px rgba(0, 0, 0, 0.35);
			}
		`;
		panel.id = 'neve-chat-render-debug-panel';
		document.head.appendChild(style);
		document.body.appendChild(panel);
		(window as any).__NEVE_CHAT_RENDER_DEBUG_LOGS = reportLines;
		(window as any).copyNeveChatRenderDebug = copyDebugReport;
		(window as any).clearNeveChatRenderDebug = clearDebugReport;
		(window as any).snapshotNeveChatRenderDebug = snapshotDebugReport;
		(window as any).probeNeveChatBottomDebug = probeBottomDebugReport;
		(window as any).captureNeveChatRenderDebug = startFrameCapture;
		(window as any).stopNeveChatRenderDebugCapture = stopFrameCapture;

		try {
			originalScrollIntoView = (Element.prototype as any).scrollIntoView;
			(Element.prototype as any).scrollIntoView = function (arg?: unknown) {
				const element = this as Element;
				if (
					element.id === 'messages-container' ||
					element.id?.startsWith('message-') ||
					element.closest?.('#messages-container')
				) {
					pushLine('scrollIntoView called', {
						arg,
						target: getElementDebugInfo(element),
						stack: new Error().stack?.split('\n').slice(1, 7)
					});
				}
				return originalScrollIntoView.call(this, arg as any);
			};
		} catch (error) {
			pushLine('scrollIntoView patch failed', error);
		}

		try {
			originalScrollTo = (HTMLElement.prototype as any).scrollTo;
			(HTMLElement.prototype as any).scrollTo = function (...args: unknown[]) {
				const element = this as HTMLElement;
				if (element.id === 'messages-container') {
					pushLine('scrollTo called', {
						args,
						target: getElementDebugInfo(element),
						stack: new Error().stack?.split('\n').slice(1, 7)
					});
				}
				return originalScrollTo.apply(this, args as any);
			};
		} catch (error) {
			pushLine('scrollTo patch failed', error);
		}

		mutationObserver.observe(document.body, { childList: true, subtree: true });
		scheduleRefreshObservedElements();
		attachScrollDebug();
		scrollAttachTimer = setInterval(attachScrollDebug, 500);

		try {
			const PerformanceObserverConstructor = (window as any).PerformanceObserver;
			if (PerformanceObserverConstructor?.supportedEntryTypes?.includes('layout-shift')) {
				performanceObserver = new PerformanceObserverConstructor((list) => {
					for (const entry of list.getEntries()) {
						if (entry.hadRecentInput || entry.value < 0.001) continue;
						const sources = (entry.sources ?? []).map((source) => {
							const node =
								source.node ??
								elementFromRect(source.currentRect) ??
								elementFromRect(source.previousRect);
							return {
								previousRect: formatRect(source.previousRect),
								currentRect: formatRect(source.currentRect),
								node: getElementDebugInfo(node),
								probePrevious: getElementDebugInfo(elementFromRect(source.previousRect)),
								probeCurrent: getElementDebugInfo(elementFromRect(source.currentRect))
							};
						});
						pushLine(`layout-shift ${entry.value.toFixed(4)}`, {
							value: entry.value,
							sources,
							snapshot: getDebugSnapshot()
						});
					}
				});
				performanceObserver.observe({ type: 'layout-shift', buffered: true });
			}
		} catch (error) {
			console.warn(debugPrefix, 'layout-shift observer unavailable', error);
		}

		pushLine('debug started');
		snapshotDebugReport();

		return () => {
			root.classList.remove('neve-chat-render-debug');
			stopFrameCapture();
			resizeObserver.disconnect();
			mutationObserver.disconnect();
			performanceObserver?.disconnect?.();
			if (originalScrollIntoView) {
				(Element.prototype as any).scrollIntoView = originalScrollIntoView;
			}
			if (originalScrollTo) {
				(HTMLElement.prototype as any).scrollTo = originalScrollTo;
			}
			if (scrollElement) {
				scrollElement.removeEventListener('scroll', onScroll);
				scrollElement.removeEventListener('wheel', onWheel);
			}
			if (scrollAttachTimer) {
				clearInterval(scrollAttachTimer);
			}
			if (refreshFrame) {
				cancelAnimationFrame(refreshFrame);
			}
			if (scrollFrame) {
				cancelAnimationFrame(scrollFrame);
			}
			style.remove();
			panel.remove();
			delete (window as any).__NEVE_CHAT_RENDER_DEBUG_LOGS;
			delete (window as any).copyNeveChatRenderDebug;
			delete (window as any).clearNeveChatRenderDebug;
			delete (window as any).snapshotNeveChatRenderDebug;
			delete (window as any).probeNeveChatBottomDebug;
			delete (window as any).captureNeveChatRenderDebug;
			delete (window as any).stopNeveChatRenderDebugCapture;
			console.log(debugPrefix, 'debug stopped');
		};
	};

	onMount(() => {
		loading = true;
		console.log('mounted');
		stopChatRenderDebug = startChatRenderDebug();
		window.addEventListener('message', onMessageHandler);
		$socket?.on('events', chatEventHandler);

		$audioQueue?.destroy();

		const audioQueueInstance = new AudioQueue(document.getElementById('audioElement'));
		audioQueue.set(audioQueueInstance);

		// Reset direct terminal enabled states — selectedTerminalId starts null on every page load
		if ($settings?.terminalServers?.some((s) => s.enabled)) {
			settings.set({
				...$settings,
				terminalServers: ($settings.terminalServers ?? []).map((s) => ({ ...s, enabled: false }))
			});
		}

		const pageSubscribe = page.subscribe(async (p) => {
			if (p.url.pathname === '/') {
				await tick();
				initNewChat();

				// Re-fetch banners on navigation to homepage so newly configured banners appear
				try {
					banners.set(await getBanners(localStorage.token).catch(() => []));
				} catch (e) {
					console.error('Failed to refresh banners:', e);
				}
			}

			stopAudio();
		});

		const showControlsSubscribe = showControls.subscribe(async (value) => {
			await tick();
			if (controlPane && !$mobile) {
				try {
					if (value) {
						controlPaneComponent?.openPane();
					} else {
						controlPane.collapse();
					}
				} catch (e) {
					// ignore
				}
			}

			if (!value) {
				showCallOverlay.set(false);
				showArtifacts.set(false);
				showEmbeds.set(false);
			}
		});

		const selectedFolderSubscribe = selectedFolder.subscribe(async (folder) => {
			await tick();
			if (
				folder?.data?.model_ids &&
				JSON.stringify(selectedModels) !== JSON.stringify(folder.data.model_ids)
			) {
				selectedModels = folder.data.model_ids;

				console.log('Set selectedModels from folder data:', selectedModels);
			}
		});

		const storageChatInput = sessionStorage.getItem(
			`chat-input${chatIdProp ? `-${chatIdProp}` : ''}`
		);

		const init = async () => {
			if (!chatIdProp) {
				loading = false;
				await tick();
			}

			if (storageChatInput) {
				prompt = '';
				messageInput?.setText('');

				files = [];
				selectedToolIds = [];
				selectedFilterIds = [];
				webSearchEnabled = false;
				deepSearchEnabled = false;
				imageGenerationEnabled = false;
				codeExecutionEnabled = false;
				stableDiffusionEnabled = false;
				musicGenerationEnabled = false;

				try {
					const input = JSON.parse(storageChatInput);

					if (!$temporaryChatEnabled) {
						messageInput?.setText(input.prompt);
						files = input.files;
						selectedToolIds = input.selectedToolIds;
						selectedFilterIds = input.selectedFilterIds;
						webSearchEnabled = input.webSearchEnabled;
						deepSearchEnabled = input.deepSearchEnabled ?? false;
						imageGenerationEnabled = input.imageGenerationEnabled;
						codeExecutionEnabled = input.codeExecutionEnabled ?? false;
						stableDiffusionEnabled = input.stableDiffusionEnabled ?? false;
						musicGenerationEnabled = input.musicGenerationEnabled ?? false;
						normalizeExclusiveFeatureToggles();
						thinkingExtendedEnabled = input.thinkingExtendedEnabled ?? thinkingExtendedEnabled;
					}
				} catch (e) {}
			}

			const chatInput = document.getElementById('chat-input');
			chatInput?.focus();
		};
		init();

		return () => {
			try {
				pageSubscribe();
				showControlsSubscribe();
				selectedFolderSubscribe();
				window.removeEventListener('message', onMessageHandler);
				$socket?.off('events', chatEventHandler);
				audioQueueInstance?.destroy();
				audioQueue.set(null);
				// Reset code execution store so CodeBlock in other views doesn't see stale value
				chatCodeExecutionEnabled.set(false);
				if (scrollRAF) {
					cancelAnimationFrame(scrollRAF);
					scrollRAF = null;
				}
				if (scrollStateRAF) {
					cancelAnimationFrame(scrollStateRAF);
					scrollStateRAF = null;
				}
				if (generationSpacerRAF) {
					cancelAnimationFrame(generationSpacerRAF);
					generationSpacerRAF = null;
				}
				cancelMessagesBottomWheelLock();
				cancelGenerationAnchorRAF();
				if (codeBlockScrollTimer) {
					clearTimeout(codeBlockScrollTimer);
					codeBlockScrollTimer = null;
				}
				if (scrollToBottomButtonSuppressTimer) {
					clearTimeout(scrollToBottomButtonSuppressTimer);
					scrollToBottomButtonSuppressTimer = null;
				}
				stopChatRenderDebug?.();
				stopChatRenderDebug = null;
			} catch (e) {
				console.error(e);
			}
		};
	});

	// File upload functions

	const uploadGoogleDriveFile = async (fileData) => {
		console.log('Starting uploadGoogleDriveFile with:', {
			id: fileData.id,
			name: fileData.name,
			url: fileData.url,
			headers: {
				Authorization: `Bearer ${token}`
			}
		});

		// Validate input
		if (!fileData?.id || !fileData?.name || !fileData?.url || !fileData?.headers?.Authorization) {
			throw new Error('Invalid file data provided');
		}

		const tempItemId = uuidv4();
		const fileItem = {
			type: 'file',
			file: '',
			id: null,
			url: fileData.url,
			name: fileData.name,
			collection_name: '',
			status: 'uploading',
			error: '',
			itemId: tempItemId,
			size: 0
		};

		try {
			files = [...files, fileItem];
			console.log('Processing web file with URL:', fileData.url);

			// Configure fetch options with proper headers
			const fetchOptions = {
				headers: {
					Authorization: fileData.headers.Authorization,
					Accept: '*/*'
				},
				method: 'GET'
			};

			// Attempt to fetch the file
			console.log('Fetching file content from Google Drive...');
			const fileResponse = await fetch(fileData.url, fetchOptions);

			if (!fileResponse.ok) {
				const errorText = await fileResponse.text();
				throw new Error(`Failed to fetch file (${fileResponse.status}): ${errorText}`);
			}

			// Get content type from response
			const contentType = fileResponse.headers.get('content-type') || 'application/octet-stream';
			console.log('Response received with content-type:', contentType);

			// Convert response to blob
			console.log('Converting response to blob...');
			const fileBlob = await fileResponse.blob();

			if (fileBlob.size === 0) {
				throw new Error('Retrieved file is empty');
			}

			console.log('Blob created:', {
				size: fileBlob.size,
				type: fileBlob.type || contentType
			});

			// Create File object with proper MIME type
			const file = new File([fileBlob], fileData.name, {
				type: fileBlob.type || contentType
			});

			console.log('File object created:', {
				name: file.name,
				size: file.size,
				type: file.type
			});

			if (file.size === 0) {
				throw new Error('Created file is empty');
			}

			// If the file is an audio file, provide the language for STT.
			let metadata = null;
			if (
				(file.type.startsWith('audio/') || file.type.startsWith('video/')) &&
				$settings?.audio?.stt?.language
			) {
				metadata = {
					language: $settings?.audio?.stt?.language
				};
			}

			// Upload file to server
			console.log('Uploading file to server...');
			const uploadedFile = await uploadFile(localStorage.token, file, metadata);

			if (!uploadedFile) {
				throw new Error('Server returned null response for file upload');
			}

			console.log('File uploaded successfully:', uploadedFile);

			// Update file item with upload results
			fileItem.status = 'uploaded';
			fileItem.file = uploadedFile;
			fileItem.id = uploadedFile.id;
			fileItem.size = file.size;
			fileItem.collection_name = uploadedFile?.meta?.collection_name;
			fileItem.url = `${uploadedFile.id}`;

			files = files;
			toast.success($i18n.t('File uploaded successfully'));
		} catch (e) {
			console.error('Error uploading file:', e);
			files = files.filter((f) => f.itemId !== tempItemId);
			toast.error(
				$i18n.t('Error uploading file: {{error}}', {
					error: e.message || 'Unknown error'
				})
			);
		}
	};

	const uploadWeb = async (urls) => {
		if ($user?.role !== 'admin' && !($user?.permissions?.chat?.web_upload ?? true)) {
			toast.error($i18n.t('You do not have permission to upload web content.'));
			return;
		}

		if (!Array.isArray(urls)) {
			urls = [urls];
		}

		// Create file items first
		const fileItems = urls.map((url) => ({
			type: 'text',
			name: url,
			collection_name: '',
			status: 'uploading',
			context: 'full',
			url,
			error: ''
		}));

		// Display all items at once
		files = [...files, ...fileItems];

		for (const fileItem of fileItems) {
			try {
				const res = isYoutubeUrl(fileItem.url)
					? await processYoutubeVideo(localStorage.token, fileItem.url)
					: await processWeb(localStorage.token, '', fileItem.url);

				if (res) {
					fileItem.status = 'uploaded';
					fileItem.collection_name = res.collection_name;
					fileItem.file = {
						...res.file,
						...fileItem.file
					};
				}

				files = [...files];
			} catch (e) {
				files = files.filter((f) => f.name !== url);
				toast.error(`${e}`);
			}
		}
	};

	const onUpload = async (event) => {
		const { type, data } = event;

		if (type === 'google-drive') {
			await uploadGoogleDriveFile(data);
		} else if (type === 'web') {
			await uploadWeb(data);
		}
	};

	let contentsDebounceTimer = null;
	let lastContentsFingerprint = '';

	const onHistoryChange = (history) => {
		if (history) {
			// Skip entirely while streaming — artifacts will be updated
			// directly by chatCompletionEventHandler when generation completes
			if (_flushRAF) return;

			clearTimeout(contentsDebounceTimer);
			contentsDebounceTimer = setTimeout(() => {
				contentsDebounceTimer = null;
				const messages = history ? createMessagesList(history, history.currentId) : [];
				const lastAssistant = messages.filter(m => m?.role !== 'user').pop();
				const fingerprint = lastAssistant ? `${lastAssistant.id}:${lastAssistant.content?.length ?? 0}` : '';
				if (fingerprint !== lastContentsFingerprint) {
					lastContentsFingerprint = fingerprint;
					getContents();
				}
			}, 300);
		} else {
			clearTimeout(contentsDebounceTimer);
			lastContentsFingerprint = '';
			artifactContents.set([]);
		}
	};

	$: onHistoryChange(history);

	const getContents = () => {
		const messages = history ? createMessagesList(history, history.currentId) : [];
		let contents = [];
		messages.forEach((message) => {
			if (message?.role !== 'user' && message?.content) {
				const {
					codeBlocks: codeBlocks,
					html: htmlContent,
					css: cssContent,
					js: jsContent
				} = getCodeBlockContents(message.content);

				if (htmlContent || cssContent || jsContent) {
					const renderedContent = `
                        <!DOCTYPE html>
                        <html lang="en">
                        <head>
                            <meta charset="UTF-8">
                            <meta name="viewport" content="width=device-width, initial-scale=1.0">
							<${''}style>
								body {
									background-color: white; /* Ensure the iframe has a white background */
								}

								${cssContent}
							</${''}style>
                        </head>
                        <body>
                            ${htmlContent}

							<${''}script>
                            	${jsContent}
							</${''}script>
                        </body>
                        </html>
                    `;
					contents = [...contents, { type: 'iframe', content: renderedContent, rawHtml: htmlContent, rawCss: cssContent, rawJs: jsContent }];
				} else {
					// Check for SVG content
					for (const block of codeBlocks) {
						if (block.lang === 'svg' || (block.lang === 'xml' && block.code.includes('<svg'))) {
							contents = [...contents, { type: 'svg', content: block.code }];
						}
					}
				}
			}
		});

		artifactContents.set(contents);
	};

	//////////////////////////
	// Web functions
	//////////////////////////

	const initNewChat = async () => {
		console.log('initNewChat');
		if ($user?.role !== 'admin' && $user?.permissions?.chat?.temporary_enforced) {
			await temporaryChatEnabled.set(true);
		}

		if ($settings?.temporaryChatByDefault ?? false) {
			if ($temporaryChatEnabled === false) {
				await temporaryChatEnabled.set(true);
			} else if ($temporaryChatEnabled === null) {
				// if set to null set to false; refer to temp chat toggle click handler
				await temporaryChatEnabled.set(false);
			}
		}

		if ($user?.role !== 'admin' && !$user?.permissions?.chat?.temporary) {
			await temporaryChatEnabled.set(false);
		}

		const availableModels = $models
			.filter((m) => !(m?.info?.meta?.hidden ?? false))
			.map((m) => m.id);

		const defaultModels = $config?.default_models ? $config?.default_models.split(',') : [];

		if ($page.url.searchParams.get('models') || $page.url.searchParams.get('model')) {
			const urlModels = (
				$page.url.searchParams.get('models') ||
				$page.url.searchParams.get('model') ||
				''
			)?.split(',');

			if (urlModels.length === 1) {
				if (!$models.find((m) => m.id === urlModels[0])) {
					// Model not found; open model selector and prefill
					const modelSelectorButton = document.getElementById('model-selector-0-button');
					if (modelSelectorButton) {
						modelSelectorButton.click();
						await tick();

						const modelSelectorInput = document.getElementById('model-search-input');
						if (modelSelectorInput) {
							modelSelectorInput.focus();
							modelSelectorInput.value = urlModels[0];
							modelSelectorInput.dispatchEvent(new Event('input'));
						}
					}
				} else {
					// Model found; set it as selected
					selectedModels = urlModels;
				}
			} else {
				// Multiple models; set as selected
				selectedModels = urlModels;
			}

			// Unavailable models filtering
			selectedModels = selectedModels.filter((modelId) =>
				$models.map((m) => m.id).includes(modelId)
			);
		} else {
			if ($selectedFolder?.data?.model_ids) {
				// Set from folder model IDs
				selectedModels = $selectedFolder?.data?.model_ids;
			} else {
				if (sessionStorage.selectedModels) {
					// Set from session storage (temporary selection)
					selectedModels = JSON.parse(sessionStorage.selectedModels);
					sessionStorage.removeItem('selectedModels');
				} else {
					if ($settings?.models) {
						// Set from user settings
						selectedModels = $settings?.models;
					} else if (defaultModels && defaultModels.length > 0) {
						// Set from default models
						selectedModels = defaultModels;
					}
				}
			}

			// Unavailable & hidden models filtering
			selectedModels = selectedModels.filter((modelId) => availableModels.includes(modelId));
		}

		// Ensure at least one model is selected
		if (selectedModels.length === 0 || (selectedModels.length === 1 && selectedModels[0] === '')) {
			if (availableModels.length > 0) {
				if (defaultModels && defaultModels.length > 0) {
					selectedModels = defaultModels.filter((modelId) => availableModels.includes(modelId));
				}

				if (
					selectedModels.length === 0 ||
					(selectedModels.length === 1 && selectedModels[0] === '')
				) {
					// Only fall back to first available model if default models didn't resolve
					selectedModels = [availableModels?.at(0) ?? ''];
				}
			} else {
				selectedModels = [''];
			}
		}

		if ($mobile) {
			await showControls.set(false);
		}
		await showCallOverlay.set(false);
		await showArtifacts.set(false);

		if ($page.url.pathname.includes('/c/')) {
			window.history.replaceState(history.state, '', `/`);
		}

		autoScroll = true;
		anchoredGeneratingMessageId = null;
		showScrollToBottomButton = false;
		generationBottomSpacerHeight = 0;
		generationSpacerScrollLimit = null;
		generationSpacerScrollAllowance = null;
		activeGenerationSpacerHeightLimit = null;
		lastMessagesScrollTop = 0;
		generationSpacerUpwardScrollIntentUntil = 0;

		resetInput();
		await chatId.set('');
		await chatTitle.set('');

		history = {
			messages: {},
			currentId: null
		};

		chatFiles = [];
		// params already cleared by resetInput() — do NOT overwrite here
		// (setDefaults() is async and would be clobbered)
		taskIds = null;
		messageQueue = [];

		if ($page.url.searchParams.get('youtube')) {
			await uploadWeb(`https://www.youtube.com/watch?v=${$page.url.searchParams.get('youtube')}`);
		}

		if ($page.url.searchParams.get('load-url')) {
			await uploadWeb($page.url.searchParams.get('load-url'));
		}

		if ($page.url.searchParams.get('web-search') === 'true') {
			webSearchEnabled = true;
		}

		if ($page.url.searchParams.get('image-generation') === 'true') {
			imageGenerationEnabled = true;
		}

		if ($page.url.searchParams.get('tools')) {
			selectedToolIds = $page.url.searchParams
				.get('tools')
				?.split(',')
				.map((id) => id.trim())
				.filter((id) => id);
		} else if ($page.url.searchParams.get('tool-ids')) {
			selectedToolIds = $page.url.searchParams
				.get('tool-ids')
				?.split(',')
				.map((id) => id.trim())
				.filter((id) => id);
		}

		if ($page.url.searchParams.get('call') === 'true') {
			showCallOverlay.set(true);
			showControls.set(true);
		}

		if ($page.url.searchParams.get('q')) {
			const q = $page.url.searchParams.get('q') ?? '';
			messageInput?.setText(q);

			if (q) {
				if (($page.url.searchParams.get('submit') ?? 'true') === 'true') {
					await tick();
					submitPrompt(q);
				}
			}
		}

		selectedModels = selectedModels.map((modelId) =>
			$models.map((m) => m.id).includes(modelId) ? modelId : ''
		);

		const chatInput = document.getElementById('chat-input');
		setTimeout(() => chatInput?.focus(), 0);
	};

	const loadChat = async () => {
		chatId.set(chatIdProp);

		if ($temporaryChatEnabled) {
			temporaryChatEnabled.set(false);
		}

		chat = await getChatById(localStorage.token, $chatId).catch(async (error) => {
			await goto('/');
			return null;
		});

		if (chat) {
			tags = await getTagsById(localStorage.token, $chatId).catch(async (error) => {
				return [];
			});

			const chatContent = chat.chat;

			if (chatContent) {
				console.log(chatContent);

				selectedModels =
					(chatContent?.models ?? undefined) !== undefined
						? chatContent.models
						: [chatContent.models ?? ''];

				if (!($user?.role === 'admin' || ($user?.permissions?.chat?.multiple_models ?? true))) {
					selectedModels = selectedModels.length > 0 ? [selectedModels[0]] : [''];
				}

				oldSelectedModelIds = structuredClone(selectedModels);

				history =
					(chatContent?.history ?? undefined) !== undefined
						? chatContent.history
						: convertMessagesToHistory(chatContent.messages);

				chatTitle.set(chatContent.title);

				params = chatContent?.params ?? {};
				chatFiles = chatContent?.files ?? [];

				autoScroll = true;
				anchoredGeneratingMessageId = null;
				showScrollToBottomButton = false;
				generationBottomSpacerHeight = 0;
				generationSpacerScrollLimit = null;
				generationSpacerScrollAllowance = null;
				activeGenerationSpacerHeightLimit = null;
				lastMessagesScrollTop = 0;
				generationSpacerUpwardScrollIntentUntil = 0;

				// Update artifact contents synchronously before tick() so that Artifacts.svelte
				// mounts with the correct content (prevents stale preview from previous chat)
				getContents();

				await tick();

				if (history.currentId) {
					for (const message of Object.values(history.messages)) {
						if (message && message.role === 'assistant') {
							message.done = true;
						}
					}
				}

				const taskRes = await getTaskIdsByChatId(localStorage.token, $chatId).catch((error) => {
					return null;
				});

				if (taskRes) {
					taskIds = taskRes.task_ids;
				}

				await tick();

				return true;
			} else {
				return null;
			}
		}
	};

	const scrollToBottom = async (behavior = 'auto') => {
		await tick();
		if (messagesContainerElement) {
			messagesContainerElement.scrollTo({
				top: messagesContainerElement.scrollHeight,
				behavior
			});
		}
	};

	const scrollToContentBottom = async (behavior = 'auto') => {
		await tick();
		if (!messagesContainerElement) return;

		const activeMessageElement = anchoredGeneratingMessageId
			? document.getElementById(`message-${anchoredGeneratingMessageId}`)
			: null;

		if (activeMessageElement) {
			const bottomPadding = getGenerationBottomReadingPadding();
			let containerRect = messagesContainerElement.getBoundingClientRect();
			let messageRect = activeMessageElement.getBoundingClientRect();
			let targetTop =
				messagesContainerElement.scrollTop +
				messageRect.bottom -
				containerRect.bottom +
				bottomPadding;
			const maxScrollTop =
				messagesContainerElement.scrollHeight - messagesContainerElement.clientHeight;

			if (targetTop > maxScrollTop) {
				const requestedSpacerHeight =
					generationBottomSpacerHeight + Math.ceil(targetTop - maxScrollTop) + 4;
				generationBottomSpacerHeight =
					activeGenerationSpacerHeightLimit === null
						? requestedSpacerHeight
						: Math.min(requestedSpacerHeight, activeGenerationSpacerHeightLimit);
				await tick();
				containerRect = messagesContainerElement.getBoundingClientRect();
				messageRect = activeMessageElement.getBoundingClientRect();
				targetTop =
					messagesContainerElement.scrollTop +
					messageRect.bottom -
					containerRect.bottom +
					bottomPadding;
			}

			messagesContainerElement.scrollTo({
				top: Math.max(0, targetTop),
				behavior
			});
			scheduleScrollStateUpdate({ updateAutoScroll: false });
			return;
		}

		const effectiveScrollHeight = Math.max(
			messagesContainerElement.clientHeight,
			messagesContainerElement.scrollHeight - generationBottomSpacerHeight
		);
		messagesContainerElement.scrollTo({
			top: effectiveScrollHeight,
			behavior
		});
	};

	const isMessagesContainerAtBottom = () => {
		if (!messagesContainerElement) return true;
		const effectiveScrollHeight = Math.max(
			messagesContainerElement.clientHeight,
			messagesContainerElement.scrollHeight - generationBottomSpacerHeight
		);
		return (
			effectiveScrollHeight - messagesContainerElement.scrollTop <=
			messagesContainerElement.clientHeight + 5
		);
	};

	const updateScrollStateFromContainer = ({
		updateAutoScroll = !anchoredGeneratingMessageId
	}: { updateAutoScroll?: boolean } = {}) => {
		if (!messagesContainerElement) {
			showScrollToBottomButton = false;
			return;
		}

		const activeMessageElement = anchoredGeneratingMessageId
			? document.getElementById(`message-${anchoredGeneratingMessageId}`)
			: null;

		if (activeMessageElement) {
			const containerRect = messagesContainerElement.getBoundingClientRect();
			const messageRect = activeMessageElement.getBoundingClientRect();
			const hasHiddenContentBelow = messageRect.bottom > containerRect.bottom + 4;
			showScrollToBottomButton =
				hasHiddenContentBelow && Date.now() >= scrollToBottomButtonSuppressUntil;

			if (updateAutoScroll) {
				autoScroll = !hasHiddenContentBelow;
			}
			return;
		}

		const atBottom = isMessagesContainerAtBottom();
		showScrollToBottomButton = !atBottom && Date.now() >= scrollToBottomButtonSuppressUntil;

		if (updateAutoScroll) {
			autoScroll = atBottom;
		}
	};

	const scheduleScrollStateUpdate = ({
		updateAutoScroll = !anchoredGeneratingMessageId
	}: { updateAutoScroll?: boolean } = {}) => {
		if (scrollStateRAF) {
			cancelAnimationFrame(scrollStateRAF);
		}

		scrollStateRAF = requestAnimationFrame(() => {
			scrollStateRAF = null;
			updateScrollStateFromContainer({ updateAutoScroll });
		});
	};

	const fitGenerationSpacerToViewport = async (
		desiredScrollTop = messagesContainerElement?.scrollTop ?? 0
	) => {
		if (!messagesContainerElement || generationBottomSpacerHeight <= 0) return;

		const realScrollHeight = Math.max(
			messagesContainerElement.clientHeight,
			messagesContainerElement.scrollHeight - generationBottomSpacerHeight
		);
		const requestedSpacerHeight = Math.max(
			0,
			Math.ceil(desiredScrollTop + messagesContainerElement.clientHeight - realScrollHeight)
		);
		const nextSpacerHeight =
			activeGenerationSpacerHeightLimit === null
				? requestedSpacerHeight
				: Math.min(requestedSpacerHeight, activeGenerationSpacerHeightLimit);

		const spacerHeightChanged = nextSpacerHeight > generationBottomSpacerHeight + 1;
		if (spacerHeightChanged) {
			generationBottomSpacerHeight = nextSpacerHeight;
			await tick();
		}
		scheduleScrollStateUpdate({ updateAutoScroll: !anchoredGeneratingMessageId });
	};

	const scheduleGenerationSpacerFit = () => {
		if (!anchoredGeneratingMessageId || !messagesContainerElement || generationBottomSpacerHeight <= 0) {
			return;
		}

		if (generationSpacerRAF) {
			cancelAnimationFrame(generationSpacerRAF);
		}

		generationSpacerRAF = requestAnimationFrame(() => {
			generationSpacerRAF = null;
			fitGenerationSpacerToViewport();
		});
	};

	const waitForLayout = async (frames = 2) => {
		await tick();
		for (let i = 0; i < frames; i += 1) {
			await new Promise((resolve) => requestAnimationFrame(resolve));
		}
	};

	const positionMessageAtTop = (
		messageId: string,
		behavior = 'auto',
		topOffset?: number
	) => {
		const messageElement = document.getElementById(`message-${messageId}`);
		if (!messageElement) return;

		if (!messagesContainerElement) {
			return;
		}

		const containerRect = messagesContainerElement.getBoundingClientRect();
		const messageRect = messageElement.getBoundingClientRect();
		const scrollMarginTop =
			topOffset ?? (parseFloat(getComputedStyle(messageElement).scrollMarginTop || '0') || 0);
		const targetTop = messagesContainerElement.scrollTop + messageRect.top - containerRect.top - scrollMarginTop;
		const nextTop = Math.max(0, targetTop);

		if (Math.abs(messagesContainerElement.scrollTop - nextTop) > 1) {
			messagesContainerElement.scrollTo({
				top: nextTop,
				behavior
			});
		}
	};

	const scrollToMessageTop = async (
		messageId: string,
		behavior = 'auto',
		{ topOffset, layoutFrames = 2 }: { topOffset?: number; layoutFrames?: number } = {}
	) => {
		if (!messageId) return;
		if (layoutFrames > 0) {
			await waitForLayout(layoutFrames);
		} else {
			await tick();
		}

		positionMessageAtTop(messageId, behavior, topOffset);
	};

	const prepareGenerationSpacerForMessageTop = (
		messageId: string,
		topOffset = 0
	) => {
		if (!messagesContainerElement || !messageId) return;

		const messageElement = document.getElementById(`message-${messageId}`);
		if (!messageElement) return;

		const containerRect = messagesContainerElement.getBoundingClientRect();
		const messageRect = messageElement.getBoundingClientRect();
		const targetTop = messagesContainerElement.scrollTop + messageRect.top - containerRect.top - topOffset;
		const maxScrollTop = Math.max(
			0,
			messagesContainerElement.scrollHeight -
				generationBottomSpacerHeight -
				messagesContainerElement.clientHeight
		);
		const requiredSpacerHeight = Math.max(
			0,
			Math.ceil(targetTop - maxScrollTop + getGenerationBottomReadingPadding())
		);

		if (Math.abs(requiredSpacerHeight - generationBottomSpacerHeight) > 1) {
			generationBottomSpacerHeight = requiredSpacerHeight;
			flushSync();
		}
	};

	const cancelGenerationAnchorRAF = () => {
		for (const frame of generationAnchorRAF) {
			cancelAnimationFrame(frame);
		}
		generationAnchorRAF = [];
	};

	const primeGeneratingMessageAnchor = (trackedMessageId?: string | null) => {
		if (!trackedMessageId) return;

		anchoredGeneratingMessageId = trackedMessageId;
		generationSpacerScrollLimit = null;
		generationSpacerScrollAllowance = null;
		activeGenerationSpacerHeightLimit = null;
		generationSpacerUpwardScrollIntentUntil = 0;
		autoScroll = false;
		cancelGenerationAnchorRAF();

		if (generationSpacerRAF) {
			cancelAnimationFrame(generationSpacerRAF);
			generationSpacerRAF = null;
		}
	};

	const stabilizeGeneratingAnchor = (
		scrollTargetMessageId: string,
		trackedMessageId: string,
		topOffset = 0
	) => {
		cancelGenerationAnchorRAF();

		let attempts = 0;
		const run = () => {
			if (anchoredGeneratingMessageId !== trackedMessageId || attempts >= 5) {
				generationAnchorRAF = [];
				return;
			}

			attempts += 1;
			scrollToMessageTop(scrollTargetMessageId, 'auto', { topOffset, layoutFrames: 0 }).then(() => {
				const frame = requestAnimationFrame(run);
				generationAnchorRAF = [frame];
			});
		};

		const frame = requestAnimationFrame(run);
		generationAnchorRAF = [frame];
	};

	const anchorGeneratingMessageTop = async (
		scrollTargetMessageId: string,
		trackedMessageId = scrollTargetMessageId,
		{
			topOffset = 0,
			stabilizeAcrossFrames = true
		}: { topOffset?: number; stabilizeAcrossFrames?: boolean } = {}
	) => {
		anchoredGeneratingMessageId = trackedMessageId;
		generationSpacerScrollLimit = null;
		generationSpacerScrollAllowance = null;
		autoScroll = false;
		flushSync();
		prepareGenerationSpacerForMessageTop(scrollTargetMessageId, topOffset);
		positionMessageAtTop(scrollTargetMessageId, 'auto', topOffset);
		await fitGenerationSpacerToViewport(messagesContainerElement?.scrollTop ?? 0);
		activeGenerationSpacerHeightLimit = generationBottomSpacerHeight;
		lastMessagesScrollTop = messagesContainerElement?.scrollTop ?? 0;
		generationSpacerUpwardScrollIntentUntil = 0;
		autoScroll = false;
		if (stabilizeAcrossFrames) {
			stabilizeGeneratingAnchor(scrollTargetMessageId, trackedMessageId, topOffset);
		}
		scheduleScrollStateUpdate({ updateAutoScroll: false });
	};

	const anchorGeneratingMessageBottom = async (messageId: string) => {
		anchoredGeneratingMessageId = messageId;
		generationBottomSpacerHeight = messagesContainerElement?.clientHeight ?? 0;
		generationSpacerScrollLimit = null;
		generationSpacerScrollAllowance = null;
		autoScroll = false;
		await tick();
		await scrollToContentBottom('auto');
		activeGenerationSpacerHeightLimit = generationBottomSpacerHeight;
		lastMessagesScrollTop = messagesContainerElement?.scrollTop ?? 0;
		generationSpacerUpwardScrollIntentUntil = 0;
		autoScroll = false;
		scheduleScrollStateUpdate({ updateAutoScroll: false });
	};

	const getMaxScrollWithoutGenerationSpacer = () => {
		if (!messagesContainerElement) return 0;
		return Math.max(
			0,
			messagesContainerElement.scrollHeight -
				generationBottomSpacerHeight -
				messagesContainerElement.clientHeight
		);
	};

	const setGenerationSpacerScrollLimit = (scrollTop: number) => {
		generationSpacerScrollLimit = scrollTop;
		generationSpacerScrollAllowance = Math.max(
			0,
			scrollTop - getMaxScrollWithoutGenerationSpacer()
		);
	};

	const getIdleGenerationSpacerScrollLimit = () => {
		if (
			!messagesContainerElement ||
			generationBottomSpacerHeight <= 0 ||
			generationSpacerScrollLimit === null
		) {
			return null;
		}

		const spacerAllowance =
			generationSpacerScrollAllowance ??
			Math.max(
				0,
				generationSpacerScrollLimit - getMaxScrollWithoutGenerationSpacer()
			);

		return Math.min(
			getMessagesMaxScrollTop(),
			getMaxScrollWithoutGenerationSpacer() + spacerAllowance
		);
	};

	const releaseGeneratingMessageAnchor = (messageId?: string) => {
		if (!messageId || anchoredGeneratingMessageId === messageId) {
			if (
				messagesContainerElement &&
				generationBottomSpacerHeight > 0 &&
				generationSpacerScrollLimit === null
			) {
				setGenerationSpacerScrollLimit(messagesContainerElement.scrollTop);
			}
			anchoredGeneratingMessageId = null;
			activeGenerationSpacerHeightLimit = null;
			generationSpacerUpwardScrollIntentUntil = 0;
			cancelGenerationAnchorRAF();
			if (generationSpacerRAF) {
				cancelAnimationFrame(generationSpacerRAF);
				generationSpacerRAF = null;
			}
		}
	};

	const clearGenerationSpacerIfSafe = async () => {
		if (!messagesContainerElement || generationBottomSpacerHeight <= 0) return;

		await tick();
		const maxScrollWithoutSpacer = Math.max(
			0,
			messagesContainerElement.scrollHeight -
				generationBottomSpacerHeight -
				messagesContainerElement.clientHeight
		);

		if (messagesContainerElement.scrollTop <= maxScrollWithoutSpacer + 0.5) {
			generationBottomSpacerHeight = 0;
			generationSpacerScrollLimit = null;
			generationSpacerScrollAllowance = null;
			await tick();
			updateScrollStateFromContainer({ updateAutoScroll: true });
		} else {
			setGenerationSpacerScrollLimit(messagesContainerElement.scrollTop);
		}
	};

	const clampIdleGenerationSpacerScroll = () => {
		if (
			!messagesContainerElement ||
			anchoredGeneratingMessageId ||
			generating ||
			generationBottomSpacerHeight <= 0 ||
			generationSpacerScrollLimit === null
		) {
			return false;
		}

		const currentScrollLimit = getIdleGenerationSpacerScrollLimit();
		if (
			currentScrollLimit !== null &&
			messagesContainerElement.scrollTop > currentScrollLimit + 1
		) {
			messagesContainerElement.scrollTop = currentScrollLimit;
			return true;
		}

		return false;
	};

	const getMessagesMaxScrollTop = () => {
		if (!messagesContainerElement) return 0;
		return Math.max(0, messagesContainerElement.scrollHeight - messagesContainerElement.clientHeight);
	};

	const consumeGenerationSpacerFromUpwardScroll = () => {
		if (!messagesContainerElement) return;

		const currentScrollTop = messagesContainerElement.scrollTop;
		const upwardDistance = lastMessagesScrollTop - currentScrollTop;
		lastMessagesScrollTop = currentScrollTop;

		if (
			generationBottomSpacerHeight <= 0 ||
			upwardDistance <= 0 ||
			performance.now() > generationSpacerUpwardScrollIntentUntil
		) {
			return;
		}

		const maxScrollWithoutSpacer = getMaxScrollWithoutGenerationSpacer();
		const nextSpacerHeight = Math.max(0, generationBottomSpacerHeight - upwardDistance);
		if (generationBottomSpacerHeight - nextSpacerHeight < 0.5) return;

		if (currentScrollTop <= maxScrollWithoutSpacer + 0.5) {
			generationBottomSpacerHeight = 0;
			generationSpacerScrollLimit = null;
			generationSpacerScrollAllowance = null;
			if (anchoredGeneratingMessageId) {
				activeGenerationSpacerHeightLimit = 0;
			}
			return;
		}

		generationBottomSpacerHeight = nextSpacerHeight;
		if (anchoredGeneratingMessageId) {
			activeGenerationSpacerHeightLimit = nextSpacerHeight;
		} else if (generationSpacerScrollLimit !== null) {
			const remainingAllowance = Math.min(
				nextSpacerHeight,
				Math.max(0, currentScrollTop - maxScrollWithoutSpacer)
			);
			generationSpacerScrollAllowance = remainingAllowance;
			generationSpacerScrollLimit = maxScrollWithoutSpacer + remainingAllowance;
		}
	};

	const beginGenerationSpacerPointerScroll = () => {
		if (!messagesContainerElement) return;
		cancelGenerationAnchorRAF();
		lastMessagesScrollTop = messagesContainerElement.scrollTop;
		if (generationBottomSpacerHeight > 0) {
			generationSpacerUpwardScrollIntentUntil = Number.POSITIVE_INFINITY;
		}
	};

	const endGenerationSpacerPointerScroll = () => {
		if (generationSpacerUpwardScrollIntentUntil === Number.POSITIVE_INFINITY) {
			generationSpacerUpwardScrollIntentUntil = 0;
		}
	};

	const cancelMessagesBottomWheelLock = () => {
		messagesBottomWheelLockUntil = 0;
		if (messagesBottomWheelLockRAF) {
			cancelAnimationFrame(messagesBottomWheelLockRAF);
			messagesBottomWheelLockRAF = null;
		}
	};

	const clampMessagesBottomWheelJitter = () => {
		if (!messagesContainerElement || Date.now() > messagesBottomWheelLockUntil) {
			return false;
		}

		const maxScrollTop = getMessagesMaxScrollTop();
		const bottomGap = maxScrollTop - messagesContainerElement.scrollTop;

		if (bottomGap >= -2 && bottomGap <= 8) {
			if (Math.abs(messagesContainerElement.scrollTop - maxScrollTop) > 0.1) {
				messagesContainerElement.scrollTop = maxScrollTop;
			}
			showScrollToBottomButton = false;
			autoScroll = true;
			return true;
		}

		return false;
	};

	const scheduleMessagesBottomWheelLockClamp = () => {
		if (messagesBottomWheelLockRAF) return;

		const run = () => {
			messagesBottomWheelLockRAF = null;
			if (Date.now() > messagesBottomWheelLockUntil) {
				return;
			}

			clampMessagesBottomWheelJitter();
			messagesBottomWheelLockRAF = requestAnimationFrame(run);
		};

		messagesBottomWheelLockRAF = requestAnimationFrame(run);
	};

	const preventMessagesBottomWheelJitter = (event: WheelEvent) => {
		if (!messagesContainerElement) return;
		if (anchoredGeneratingMessageId) {
			cancelGenerationAnchorRAF();
		}

		if (event.deltaY < 0) {
			if (generationBottomSpacerHeight > 0) {
				generationSpacerUpwardScrollIntentUntil = performance.now() + 180;
			}
			cancelMessagesBottomWheelLock();
			return;
		}

		if (event.deltaY <= 0) return;
		generationSpacerUpwardScrollIntentUntil = 0;

		const idleGenerationScrollLimit =
			!anchoredGeneratingMessageId &&
			!generating &&
			generationBottomSpacerHeight > 0 &&
			generationSpacerScrollLimit !== null
				? getIdleGenerationSpacerScrollLimit()
				: null;

		if (idleGenerationScrollLimit !== null) {
			cancelMessagesBottomWheelLock();
			const wheelDeltaPixels =
				event.deltaMode === 1
					? event.deltaY * 16
					: event.deltaMode === 2
						? event.deltaY * messagesContainerElement.clientHeight
						: event.deltaY;

			if (messagesContainerElement.scrollTop + wheelDeltaPixels > idleGenerationScrollLimit) {
				event.preventDefault();
				if (messagesContainerElement.scrollTop < idleGenerationScrollLimit) {
					messagesContainerElement.scrollTop = idleGenerationScrollLimit;
				}
				scheduleScrollStateUpdate({ updateAutoScroll: false });
			}
			return;
		}

		if (anchoredGeneratingMessageId) {
			cancelMessagesBottomWheelLock();
			return;
		}

		const maxScrollTop = getMessagesMaxScrollTop();
		const bottomGap = maxScrollTop - messagesContainerElement.scrollTop;

		if (bottomGap <= 8) {
			event.preventDefault();
			messagesBottomWheelLockUntil = Date.now() + 320;
			clampMessagesBottomWheelJitter();
			scheduleMessagesBottomWheelLockClamp();
		}
	};

	const observeMessagesContentSize = (node: HTMLElement) => {
		if (typeof ResizeObserver === 'undefined') {
			return {};
		}

		let resizeFrame: ReturnType<typeof requestAnimationFrame> | null = null;
		const observer = new ResizeObserver(() => {
			if (resizeFrame) {
				cancelAnimationFrame(resizeFrame);
			}

			resizeFrame = requestAnimationFrame(() => {
				resizeFrame = null;
				clampIdleGenerationSpacerScroll();
				updateScrollStateFromContainer({ updateAutoScroll: false });
			});
		});

		observer.observe(node);

		return {
			destroy() {
				observer.disconnect();
				if (resizeFrame) {
					cancelAnimationFrame(resizeFrame);
				}
			}
		};
	};

	let scrollRAF = null;
	const scheduleScrollToBottom = () => {
		if (!scrollRAF) {
			scrollRAF = requestAnimationFrame(async () => {
				scrollRAF = null;
				await scrollToBottom();
			});
		}
	};

	const scrollToBottomFromInput = async () => {
		const isAnchoredGeneration = Boolean(anchoredGeneratingMessageId);

		scrollToBottomButtonSuppressUntil = Date.now() + (isAnchoredGeneration ? 120 : 350);
		showScrollToBottomButton = false;
		if (scrollToBottomButtonSuppressTimer) {
			clearTimeout(scrollToBottomButtonSuppressTimer);
		}
		if (generationSpacerRAF) {
			cancelAnimationFrame(generationSpacerRAF);
			generationSpacerRAF = null;
		}

		await scrollToContentBottom(isAnchoredGeneration ? 'auto' : 'smooth');
		if (!anchoredGeneratingMessageId) {
			autoScroll = true;
		}

		scrollToBottomButtonSuppressTimer = setTimeout(() => {
			scrollToBottomButtonSuppressTimer = null;
			scrollToBottomButtonSuppressUntil = 0;
			updateScrollStateFromContainer({ updateAutoScroll: !anchoredGeneratingMessageId });
		}, isAnchoredGeneration ? 120 : 350);
	};
	const chatCompletedHandler = async (_chatId, modelId, responseMessageId, messages) => {
		const res = await chatCompleted(localStorage.token, {
			model: modelId,
			messages: messages.map((m) => ({
				id: m.id,
				role: m.role,
				content: m.content,
				info: m.info ? m.info : undefined,
				timestamp: m.timestamp,
				...(m.usage ? { usage: m.usage } : {}),
				...(m.sources ? { sources: m.sources } : {})
			})),
			filter_ids: selectedFilterIds.length > 0 ? selectedFilterIds : undefined,
			model_item: $models.find((m) => m.id === modelId),
			chat_id: _chatId,
			session_id: $socket?.id,
			id: responseMessageId
		}).catch((error) => {
			toast.error(`${error}`);
			messages.at(-1).error = { content: error };

			return null;
		});

		if (res !== null && res.messages) {
			// Update chat history with the new messages
			for (const message of res.messages) {
				if (message?.id) {
					// Add null check for message and message.id
					history.messages[message.id] = {
						...history.messages[message.id],
						...(history.messages[message.id].content !== message.content
							? { originalContent: history.messages[message.id].content }
							: {}),
						...message
					};
				}
			}
		}

		await tick();

		if ($chatId == _chatId) {
			if (!$temporaryChatEnabled) {
				chat = await updateChatById(localStorage.token, _chatId, {
					models: selectedModels,
					messages: messages,
					history: history,
					params: params,
					files: chatFiles
				});

				currentChatPage.set(1);
				await chats.set(await getChatList(localStorage.token, $currentChatPage));
			}
		}

		taskIds = null;

		if (!stableDiffusionEnabled && !musicGenerationEnabled) {
			await restoreStableDiffusionStandbyModel();
		}

		// Process message queue - combine all queued messages and submit at once
		if (messageQueue.length > 0) {
			const combinedPrompt = messageQueue.map((m) => m.prompt).join('\n\n');
			const combinedFiles = messageQueue.flatMap((m) => m.files);
			messageQueue = [];

			// Set the files and submit
			files = combinedFiles;
			await tick();
			await submitPrompt(combinedPrompt);
		}
	};

	const chatActionHandler = async (_chatId, actionId, modelId, responseMessageId, event = null) => {
		const messages = createMessagesList(history, responseMessageId);

		const res = await chatAction(localStorage.token, actionId, {
			model: modelId,
			messages: messages.map((m) => ({
				id: m.id,
				role: m.role,
				content: m.content,
				info: m.info ? m.info : undefined,
				timestamp: m.timestamp,
				...(m.sources ? { sources: m.sources } : {})
			})),
			...(event ? { event: event } : {}),
			model_item: $models.find((m) => m.id === modelId),
			chat_id: _chatId,
			session_id: $socket?.id,
			id: responseMessageId
		}).catch((error) => {
			toast.error(`${error}`);
			messages.at(-1).error = { content: error };
			return null;
		});

		if (res !== null && res.messages) {
			// Update chat history with the new messages
			for (const message of res.messages) {
				history.messages[message.id] = {
					...history.messages[message.id],
					...(history.messages[message.id].content !== message.content
						? { originalContent: history.messages[message.id].content }
						: {}),
					...message
				};
			}
		}

		if ($chatId == _chatId) {
			if (!$temporaryChatEnabled) {
				chat = await updateChatById(localStorage.token, _chatId, {
					models: selectedModels,
					messages: messages,
					history: history,
					params: params,
					files: chatFiles
				});

				currentChatPage.set(1);
				await chats.set(await getChatList(localStorage.token, $currentChatPage));
			}
		}
	};

	const getChatEventEmitter = async (modelId: string, chatId: string = '') => {
		return setInterval(() => {
			$socket?.emit('usage', {
				action: 'chat',
				model: modelId,
				chat_id: chatId
			});
		}, 1000);
	};

	const createMessagePair = async (userPrompt) => {
		messageInput?.setText('');
		if (selectedModels.length === 0) {
			toast.error($i18n.t('Model not selected'));
		} else {
			const modelId = selectedModels[0];
			const model = $models.filter((m) => m.id === modelId).at(0);

			if (!model) {
				toast.error($i18n.t('Model not found'));
				return;
			}

			const messages = createMessagesList(history, history.currentId);
			const parentMessage = messages.length !== 0 ? messages.at(-1) : null;

			const userMessageId = uuidv4();
			const responseMessageId = uuidv4();

			const userMessage = {
				id: userMessageId,
				parentId: parentMessage ? parentMessage.id : null,
				childrenIds: [responseMessageId],
				role: 'user',
				content: userPrompt ? userPrompt : `[PROMPT] ${userMessageId}`,
				timestamp: Math.floor(Date.now() / 1000)
			};

			const responseMessage = {
				id: responseMessageId,
				parentId: userMessageId,
				childrenIds: [],
				role: 'assistant',
				content: `[RESPONSE] ${responseMessageId}`,
				done: true,

				model: modelId,
				modelName: model.name ?? model.id,
				modelIdx: 0,
				timestamp: Math.floor(Date.now() / 1000)
			};

			if (parentMessage) {
				parentMessage.childrenIds.push(userMessageId);
				history.messages[parentMessage.id] = parentMessage;
			}
			history.messages[userMessageId] = userMessage;
			history.messages[responseMessageId] = responseMessage;

			history.currentId = responseMessageId;

			await tick();

			if (autoScroll) {
				scrollToBottom();
			}

			if (messages.length === 0) {
				await initChatHandler(history);
			} else {
				await saveChatHandler($chatId, history);
			}
		}
	};

	const addMessages = async ({ modelId, parentId, messages }) => {
		const model = $models.filter((m) => m.id === modelId).at(0);

		let parentMessage = history.messages[parentId];
		let currentParentId = parentMessage ? parentMessage.id : null;
		for (const message of messages) {
			let messageId = uuidv4();

			if (message.role === 'user') {
				const userMessage = {
					id: messageId,
					parentId: currentParentId,
					childrenIds: [],
					timestamp: Math.floor(Date.now() / 1000),
					...message
				};

				if (parentMessage) {
					parentMessage.childrenIds.push(messageId);
					history.messages[parentMessage.id] = parentMessage;
				}

				history.messages[messageId] = userMessage;
				parentMessage = userMessage;
				currentParentId = messageId;
			} else {
				const responseMessage = {
					id: messageId,
					parentId: currentParentId,
					childrenIds: [],
					done: true,
					model: model.id,
					modelName: model.name ?? model.id,
					modelIdx: 0,
					timestamp: Math.floor(Date.now() / 1000),
					...message
				};

				if (parentMessage) {
					parentMessage.childrenIds.push(messageId);
					history.messages[parentMessage.id] = parentMessage;
				}

				history.messages[messageId] = responseMessage;
				parentMessage = responseMessage;
				currentParentId = messageId;
			}
		}

		history.currentId = currentParentId;
		await tick();

		if (autoScroll) {
			scrollToBottom();
		}

		if (messages.length === 0) {
			await initChatHandler(history);
		} else {
			await saveChatHandler($chatId, history);
		}
	};

	const chatCompletionEventHandler = async (data, message, chatId) => {
		const { id, done, choices, content, output, sources, selected_model_id, error, usage } = data;

		// Store raw OR-aligned output items from backend
		if (output) {
			message.output = output;
		}

		if (error) {
			await handleOpenAIError(error, message);
		}

		if (sources && !message?.sources) {
			message.sources = sources;
		}

		// Initialize buffer for this message if not already present
		if (!_contentBuffers.has(message.id)) {
			_contentBuffers.set(message.id, message.content ?? '');
		}

		if (choices) {
			if (choices[0]?.message?.content) {
				// Non-stream response — still buffer it
				_contentBuffers.set(message.id, (_contentBuffers.get(message.id) ?? '') + choices[0].message.content);
			} else {
				// Stream response — accumulate in plain JS buffer (no proxy mutation)
				let value = choices[0]?.delta?.content ?? '';
				let current = _contentBuffers.get(message.id) ?? '';
				if (!(current === '' && value === '\n')) {
					_contentBuffers.set(message.id, current + value);

					if (navigator.vibrate && ($settings?.hapticFeedback ?? false)) {
						navigator.vibrate(5);
					}

					// Emit chat event for TTS (only when call overlay is active)
					if ($showCallOverlay) {
						const buffered = _contentBuffers.get(message.id);
						const messageContentParts = getMessageContentParts(
							removeAllDetails(buffered),
							$config?.audio?.tts?.split_on ?? 'punctuation'
						);
						messageContentParts.pop();

						if (
							messageContentParts.length > 0 &&
							messageContentParts[messageContentParts.length - 1] !== message.lastSentence
						) {
							message.lastSentence = messageContentParts[messageContentParts.length - 1];
							eventTarget.dispatchEvent(
								new CustomEvent('chat', {
									detail: {
										id: message.id,
										content: messageContentParts[messageContentParts.length - 1]
									}
								})
							);
						}
					}
				}
			}
		}

		if (content) {
			_contentBuffers.set(message.id, content);

			if (navigator.vibrate && ($settings?.hapticFeedback ?? false)) {
				navigator.vibrate(5);
			}

			// Emit chat event for TTS (only when call overlay is active)
			if ($showCallOverlay) {
				const buffered = _contentBuffers.get(message.id);
				const messageContentParts = getMessageContentParts(
					removeAllDetails(buffered),
					$config?.audio?.tts?.split_on ?? 'punctuation'
				);
				messageContentParts.pop();

				if (
					messageContentParts.length > 0 &&
					messageContentParts[messageContentParts.length - 1] !== message.lastSentence
				) {
					message.lastSentence = messageContentParts[messageContentParts.length - 1];
					eventTarget.dispatchEvent(
						new CustomEvent('chat', {
							detail: {
								id: message.id,
								content: messageContentParts[messageContentParts.length - 1]
							}
						})
					);
				}
			}
		}

		if (selected_model_id) {
			message.selectedModelId = selected_model_id;
			message.arena = true;
		}

		if (usage) {
			message.usage = usage;
		}

		if (done) {
			// Flush final buffered content to the proxy
			const finalContent = _contentBuffers.get(message.id) ?? message.content;
			message.content = finalContent;
			stopContentFlush(message.id);

			// Clear artifact debounce — we'll call getContents() directly below
			clearTimeout(contentsDebounceTimer);
			contentsDebounceTimer = null;
			lastContentsFingerprint = '';

			const wasAnchored = anchoredGeneratingMessageId === message.id;
			message.done = true;

			// Immediately remove this chat from activeChatIds so spinner stops
			activeChatIds.update((ids) => { ids.delete(chatId); return new Set(ids); });

			if ($settings.responseAutoCopy) {
				copyToClipboard(message.content);
			}

			if ($settings.responseAutoPlayback && !$showCallOverlay) {
				await tick();
				document.getElementById(`speak-button-${message.id}`)?.click();
			}

			// Emit chat event for TTS (only when call overlay is active)
			if ($showCallOverlay) {
				let lastMessageContentPart =
					getMessageContentParts(
						removeAllDetails(message.content),
						$config?.audio?.tts?.split_on ?? 'punctuation'
					)?.at(-1) ?? '';
				if (lastMessageContentPart) {
					eventTarget.dispatchEvent(
						new CustomEvent('chat', {
							detail: { id: message.id, content: lastMessageContentPart }
						})
					);
				}
			}
			eventTarget.dispatchEvent(
				new CustomEvent('chat:finish', {
					detail: {
						id: message.id,
						content: message.content
					}
				})
			);

			history.messages[message.id] = message;

			await tick();
			if (wasAnchored) {
				updateScrollStateFromContainer({ updateAutoScroll: false });
			} else if (autoScroll) {
				scrollToBottom();
			}

			// Update artifacts now that generation is complete
			getContents();

			// Auto-open artifacts panel if HTML/SVG content was detected
			const artContents = get(artifactContents);
			if (
				$chatCodeExecutionEnabled &&
				artContents && artContents.length > 0 &&
				($settings?.detectArtifacts ?? true) &&
				!$mobile
			) {
				showArtifacts.set(true);
				showControls.set(true);
			}

			await chatCompletedHandler(
				chatId,
				message.model,
				message.id,
				createMessagesList(history, message.id)
			);

			if (wasAnchored) {
				await clearGenerationSpacerIfSafe();
				releaseGeneratingMessageAnchor(message.id);
				updateScrollStateFromContainer({ updateAutoScroll: false });
			}
		} else {
			// Start periodic flush (200ms) — this is the ONLY place reactive updates
			// happen during streaming, replacing per-token proxy mutations
			startContentFlush();
		}
	};

	//////////////////////////
	// Chat functions
	//////////////////////////

	type LocalModelLoadPlan = {
		modelFilename: string;
		gpuLayers: number;
		contextSize: number;
		mmprojFilename: string;
		cacheType: string;
		speculativeDecoding: string;
		tokenPrediction: string;
		contextShift: string;
	};

	const normalizeLocalCacheType = (cacheType?: string | null) => {
		return cacheType && cacheType !== 'default' ? cacheType : 'f16';
	};

	const normalizeLocalSpeculativeDecoding = (speculativeDecoding?: string | null) => {
		return speculativeDecoding && speculativeDecoding !== 'default' ? speculativeDecoding : 'off';
	};

	const normalizeLocalTokenPrediction = (tokenPrediction?: string | null) => {
		return tokenPrediction === 'on' || tokenPrediction === 'stable' || tokenPrediction === 'aggressive'
			? 'on'
			: 'off';
	};

	const normalizeLocalContextShift = (contextShift?: string | null) => {
		return contextShift === 'on' ? 'on' : 'off';
	};

	const isLocalTokenPredictionEnabled = (tokenPrediction?: string | null) => {
		return normalizeLocalTokenPrediction(tokenPrediction) !== 'off';
	};

	const isLocalContextShiftEnabled = (contextShift?: string | null) => {
		return normalizeLocalContextShift(contextShift) !== 'off';
	};

	const resolveLocalModelLoadPlan = async (
		model: any,
		modelId: string,
		loadedModel: LocalModel | null
	): Promise<LocalModelLoadPlan | null> => {
		const llamacppInfo = model.llamacpp ?? {};
		const modelFilename = llamacppInfo.filename ?? modelId;
		const loadPreferences = getLocalModelLoadPreferences();

		let contextSize: number;
		if (loadPreferences.context === 'ask') {
			if (loadedModel?.n_ctx) {
				contextSize = loadedModel.n_ctx;
			} else {
				const modalSize = await openContextModal(model.name ?? modelId);
				if (modalSize === null) {
					return null;
				}
				contextSize = modalSize;
			}
		} else {
			contextSize = loadPreferences.context;
		}

		const mmProjFiles = await getMmProjFiles(localStorage.token);
		const matchingMmproj = findMatchingMmproj(modelFilename, mmProjFiles);
		let mmprojFilename = '';

		if (matchingMmproj) {
			if (loadPreferences.vision === 'ask') {
				if (loadedModel) {
					mmprojFilename = loadedModel.mmproj_filename ?? '';
				} else {
					const useVision = await openVisionModal(model.name ?? modelId);
					mmprojFilename = useVision ? matchingMmproj : '';
				}
			} else {
				mmprojFilename = loadPreferences.vision === 'yes' ? matchingMmproj : '';
			}
		}

		const contextShift = normalizeLocalContextShift(loadPreferences.contextShift);
		const tokenPrediction = isLocalContextShiftEnabled(contextShift)
			? 'off'
			: normalizeLocalTokenPrediction(loadPreferences.tokenPrediction);
		const speculativeDecoding = isLocalContextShiftEnabled(contextShift) || isLocalTokenPredictionEnabled(tokenPrediction)
			? 'off'
			: normalizeLocalSpeculativeDecoding(loadPreferences.speculative);

		return {
			modelFilename,
			gpuLayers: llamacppInfo.n_gpu_layers ?? -1,
			contextSize,
			mmprojFilename,
			cacheType: normalizeLocalCacheType(loadPreferences.cache),
			speculativeDecoding,
			tokenPrediction,
			contextShift
		};
	};

	const loadedLocalModelMatchesPlan = (loadedModel: LocalModel, loadPlan: LocalModelLoadPlan) => {
		return (
			(loadedModel.n_ctx ?? loadPlan.contextSize) === loadPlan.contextSize &&
			(loadedModel.mmproj_filename ?? '') === loadPlan.mmprojFilename &&
			normalizeLocalCacheType(loadedModel.cache_type) === loadPlan.cacheType &&
			normalizeLocalSpeculativeDecoding(loadedModel.speculative_decoding) ===
				loadPlan.speculativeDecoding &&
			normalizeLocalTokenPrediction(loadedModel.token_prediction) === loadPlan.tokenPrediction &&
			normalizeLocalContextShift(loadedModel.context_shift) === loadPlan.contextShift
		);
	};

	const ensureLocalModelsReady = async (modelIds: string[]) => {
		for (const modelId of modelIds) {
			const model = $models.find((m) => m.id === modelId);
			if (!model || (model as any).owned_by !== 'llamacpp') {
				continue;
			}

			try {
				const loadedModels = await getLoadedLocalModels(localStorage.token);
				const loadedModel = loadedModels.find((lm) => lm.id === modelId) ?? null;

				if (stableDiffusionEnabled || musicGenerationEnabled) {
					stableDiffusionStandbyModel = loadedModel ?? loadedModels[0] ?? stableDiffusionStandbyModel;
					continue;
				}

				const loadPlan = await resolveLocalModelLoadPlan(model, modelId, loadedModel);
				if (loadPlan === null) {
					return false;
				}

				const needsLoad =
					loadedModel === null || !loadedLocalModelMatchesPlan(loadedModel, loadPlan);
				if (!needsLoad) {
					continue;
				}

				const currentlyLoaded = loadedModels.length > 0 ? loadedModels[0] : null;

				modelLoading = true;
				try {
					toast.info($i18n.t('Loading model... Please wait.'));
					if (currentlyLoaded) {
						try {
							await unloadLocalModel(localStorage.token, currentlyLoaded.id);
						} catch (unloadErr) {
							console.warn('Could not explicitly unload previous model (may already be inactive):', unloadErr);
						}
					}

					const doLoad = () =>
						loadLocalModel(
							localStorage.token,
							loadPlan.modelFilename,
							loadPlan.gpuLayers,
							loadPlan.contextSize,
							loadPlan.mmprojFilename,
							loadPlan.cacheType,
							loadPlan.speculativeDecoding,
							loadPlan.tokenPrediction,
							loadPlan.contextShift
						);
					try {
						await doLoad();
					} catch (firstErr) {
						const firstErrorMessage = normalizeLlamaCppErrorMessage(
							firstErr,
							'Falha ao carregar modelo'
						);
						if (firstErrorMessage.toLowerCase().includes('tokens')) {
							throw firstErr;
						}
						console.warn('First load attempt failed, retrying in 3s...', firstErr);
						await new Promise((resolve) => setTimeout(resolve, 3000));
						await doLoad();
					}
					toast.success($i18n.t('Model loaded successfully!'));
					models.set(await getModels(localStorage.token, null, false, true));
				} finally {
					modelLoading = false;
				}
			} catch (err: any) {
				console.error('LlamaCpp model check failed:', err);
				showLocalModelLoadError(err);
				return false;
			}
		}

		return true;
	};

	const submitPrompt = async (userPrompt, { _raw = false } = {}) => {
		console.log('submitPrompt', userPrompt, $chatId);

		const _selectedModels = selectedModels.map((modelId) =>
			$models.map((m) => m.id).includes(modelId) ? modelId : ''
		);

		if (JSON.stringify(selectedModels) !== JSON.stringify(_selectedModels)) {
			selectedModels = _selectedModels;
		}

		if (userPrompt === '' && files.length === 0) {
			toast.error($i18n.t('Please enter a prompt'));
			return;
		}
		if (selectedModels.includes('')) {
			toast.error($i18n.t('Model not selected'));
			return;
		}

		// ── LlamaCpp model-loaded check ──────────────────────────────
		for (const modelId of selectedModels) {
			const model = $models.find((m) => m.id === modelId);
			if (model && (model as any).owned_by === 'llamacpp') {
				try {
					const loadedModels = await getLoadedLocalModels(localStorage.token);
					const loadedModel = loadedModels.find((lm) => lm.id === modelId) ?? null;

					if (stableDiffusionEnabled || musicGenerationEnabled) {
						stableDiffusionStandbyModel = loadedModel ?? loadedModels[0] ?? stableDiffusionStandbyModel;
						continue;
					}

					const loadPlan = await resolveLocalModelLoadPlan(model, modelId, loadedModel);
					if (loadPlan === null) {
						return;
					}

					const needsLoad =
						loadedModel === null || !loadedLocalModelMatchesPlan(loadedModel, loadPlan);
					if (needsLoad) {
						const currentlyLoaded = loadedModels.length > 0 ? loadedModels[0] : null;

						modelLoading = true;
						try {
							toast.info($i18n.t('Loading model... Please wait.'));
							if (currentlyLoaded) {
								try {
									await unloadLocalModel(localStorage.token, currentlyLoaded.id);
								} catch (unloadErr) {
									console.warn('Could not explicitly unload previous model (may already be inactive):', unloadErr);
								}
							}

							const doLoad = () =>
								loadLocalModel(
									localStorage.token,
									loadPlan.modelFilename,
									loadPlan.gpuLayers,
									loadPlan.contextSize,
									loadPlan.mmprojFilename,
									loadPlan.cacheType,
									loadPlan.speculativeDecoding,
									loadPlan.tokenPrediction,
									loadPlan.contextShift
								);
							try {
								await doLoad();
							} catch (firstErr) {
								const firstErrorMessage = normalizeLlamaCppErrorMessage(
									firstErr,
									'Falha ao carregar modelo'
								);
								if (firstErrorMessage.includes('Predição de tokens')) {
									throw firstErr;
								}
								console.warn('First load attempt failed, retrying in 3s...', firstErr);
								await new Promise((resolve) => setTimeout(resolve, 3000));
								await doLoad();
							}
							toast.success($i18n.t('Model loaded successfully!'));
							models.set(await getModels(localStorage.token, null, false, true));
						} finally {
							modelLoading = false;
						}
					}
				} catch (err: any) {
					console.error('LlamaCpp model check failed:', err);
					showLocalModelLoadError(err);
					return;
				}
			}
		}
		// ─────────────────────────────────────────────────────────────

		if (
			files.length > 0 &&
			files.filter((file) => file.type !== 'image' && file.status === 'uploading').length > 0
		) {
			toast.error(
				$i18n.t(`Oops! There are files still uploading. Please wait for the upload to complete.`)
			);
			return;
		}

		if (
			($config?.file?.max_count ?? null) !== null &&
			files.length + chatFiles.length > $config?.file?.max_count
		) {
			toast.error(
				$i18n.t(`You can only chat with a maximum of {{maxCount}} file(s) at a time.`, {
					maxCount: $config?.file?.max_count
				})
			);
			return;
		}

		// Check if there are pending tasks (more reliable than lastMessage.done)
		if (taskIds !== null && taskIds.length > 0) {
			if ($settings?.enableMessageQueue ?? true) {
				// Queue the message
				const _files = structuredClone(files);
				messageQueue = [
					...messageQueue,
					{
						id: uuidv4(),
						prompt: userPrompt,
						files: _files
					}
				];
				// Clear input
				messageInput?.setText('');
				prompt = '';
				files = [];
				return;
			} else {
				// Interrupt: stop current generation and proceed
				await stopResponse();
				await tick();
			}
		}

		if (history?.currentId) {
			const lastMessage = history.messages[history.currentId];

			if (lastMessage.error && !lastMessage.content) {
				// Error in response
				toast.error($i18n.t(`Oops! There was an error in the previous response.`));
				return;
			}
		}

		messageInput?.setText('');
		prompt = '';

		const messages = createMessagesList(history, history.currentId);
		const _files = structuredClone(files);

		chatFiles.push(
			..._files.filter(
				(item) =>
					['doc', 'text', 'note', 'chat', 'folder', 'collection'].includes(item.type) ||
					(item.type === 'file' && !(item?.content_type ?? '').startsWith('image/'))
			)
		);
		chatFiles = chatFiles.filter(
			// Remove duplicates
			(item, index, array) =>
				array.findIndex((i) => JSON.stringify(i) === JSON.stringify(item)) === index
		);

		files = [];
		messageInput?.setText('');

		// Create user message
		let userMessageId = uuidv4();
		let userMessage = {
			id: userMessageId,
			parentId: messages.length !== 0 ? messages.at(-1).id : null,
			childrenIds: [],
			role: 'user',
			content: userPrompt,
			files: _files.length > 0 ? _files : undefined,
			timestamp: Math.floor(Date.now() / 1000), // Unix epoch
			models: selectedModels
		};

		// Add message to history and Set currentId to messageId
		history.messages[userMessageId] = userMessage;
		history.currentId = userMessageId;

		// Append messageId to childrenIds of parent message
		if (messages.length !== 0) {
			history.messages[messages.at(-1).id].childrenIds.push(userMessageId);
		}

		// focus on chat input
		const chatInput = document.getElementById('chat-input');
		chatInput?.focus();

		saveSessionSelectedModels();

		await sendMessage(history, userMessageId, { newChat: true });
	};

	const sendMessage = async (
		_history,
		parentId: string,
		{
			messages = null,
			modelId = null,
			modelIdx = null,
			newChat = false
		}: {
			messages?: any[] | null;
			modelId?: string | null;
			modelIdx?: number | null;
			newChat?: boolean;
		} = {}
	) => {
		let _chatId = JSON.parse(JSON.stringify($chatId));
		_history = structuredClone(_history);

		const responseMessageIds: Record<PropertyKey, string> = {};
		const responseMessageOrder: string[] = [];
		// If modelId is provided, use it, else use selected model
		let selectedModelIds = modelId
			? [modelId]
			: atSelectedModel !== undefined
				? [atSelectedModel.id]
				: selectedModels;

		// Create response messages for each selected model
		for (const [_modelIdx, modelId] of selectedModelIds.entries()) {
			const model = $models.filter((m) => m.id === modelId).at(0);

			if (model) {
				let responseMessageId = uuidv4();
				let responseMessage = {
					parentId: parentId,
					id: responseMessageId,
					childrenIds: [],
					role: 'assistant',
					content: '',
					done: false,
					model: model.id,
					modelName: model.name ?? model.id,
					modelIdx: modelIdx ? modelIdx : _modelIdx,
					timestamp: Math.floor(Date.now() / 1000) // Unix epoch
				};

				// Add message to history and Set currentId to messageId
				history.messages[responseMessageId] = responseMessage;
				history.currentId = responseMessageId;

				// Append messageId to childrenIds of parent message
				if (parentId !== null && history.messages[parentId]) {
					// Add null check before accessing childrenIds
					history.messages[parentId].childrenIds = [
						...history.messages[parentId].childrenIds,
						responseMessageId
					];
				}

				responseMessageIds[`${modelId}-${modelIdx ? modelIdx : _modelIdx}`] = responseMessageId;
				responseMessageOrder.push(responseMessageId);
			}
		}

		const initialResponseMessageId = responseMessageOrder[0] ?? null;
		if (initialResponseMessageId) {
			primeGeneratingMessageAnchor(initialResponseMessageId);
		}
		history = history;

		if (initialResponseMessageId) {
			await anchorGeneratingMessageTop(parentId, initialResponseMessageId, {
				topOffset: USER_MESSAGE_ANCHOR_TOP_OFFSET_PX,
				stabilizeAcrossFrames: false
			});
		}

		// Create new chat if newChat is true and first user message
		if (newChat && _history.messages[_history.currentId].parentId === null) {
			_chatId = await initChatHandler(_history);
		}

		_history = structuredClone(history);
		// Save chat after all messages have been created
		await saveChatHandler(_chatId, _history);

		await Promise.all(
			selectedModelIds.map(async (modelId, _modelIdx) => {
				console.log('modelId', modelId);
				const model = $models.filter((m) => m.id === modelId).at(0);

				if (model) {
					// If there are image files, check if model is vision capable unless an image tool owns the request.
					const hasImages = createMessagesList(_history, parentId).some((message) =>
						message.files?.some(
							(file) => file.type === 'image' || (file?.content_type ?? '').startsWith('image/')
						)
					);

					if (
						hasImages &&
						!(model.info?.meta?.capabilities?.vision ?? true) &&
						!imageGenerationEnabled &&
						!stableDiffusionEnabled
					) {
						toast.error(
							$i18n.t('Model {{modelName}} is not vision capable', {
								modelName: model.name ?? model.id
							})
						);
					}

					let responseMessageId =
						responseMessageIds[`${modelId}-${modelIdx ? modelIdx : _modelIdx}`];
					const chatEventEmitter = await getChatEventEmitter(model.id, _chatId);

					await sendMessageSocket(
						model,
						messages && messages.length > 0
							? messages
							: createMessagesList(_history, responseMessageId),
						_history,
						responseMessageId,
						_chatId
					);

					if (chatEventEmitter) clearInterval(chatEventEmitter);
				} else {
					toast.error($i18n.t(`Model {{modelId}} not found`, { modelId }));
				}
			})
		);

		currentChatPage.set(1);
		chats.set(await getChatList(localStorage.token, $currentChatPage));
	};

	const getFeatures = () => {
		const effectiveDeepSearchEnabled =
			deepSearchEnabled &&
			!webSearchEnabled &&
			!imageGenerationEnabled &&
			!codeExecutionEnabled &&
			!stableDiffusionEnabled &&
			!musicGenerationEnabled &&
			selectedToolIds.length === 0 &&
			selectedFilterIds.length === 0;

		let features = {};

		if ($config?.features)
			features = {
				voice: $showCallOverlay,
				image_generation:
					$config?.features?.enable_image_generation &&
					($user?.role === 'admin' || $user?.permissions?.features?.image_generation)
						? imageGenerationEnabled
						: false,
				web_search:
					$config?.features?.enable_web_search &&
					($user?.role === 'admin' || $user?.permissions?.features?.web_search)
						? webSearchEnabled || effectiveDeepSearchEnabled
						: false,
				deep_search:
					$config?.features?.enable_web_search &&
					($user?.role === 'admin' || $user?.permissions?.features?.web_search)
						? effectiveDeepSearchEnabled
						: false,
				code_execution:
					$config?.features?.enable_code_execution
						? codeExecutionEnabled
						: false,
				stable_diffusion:
					$config?.features?.enable_stable_diffusion &&
					($user?.role === 'admin' || $user?.permissions?.features?.stable_diffusion)
						? stableDiffusionEnabled
						: false,
				music_generation:
					$config?.features?.enable_music_generation &&
					($user?.role === 'admin' || $user?.permissions?.features?.music_generation)
						? musicGenerationEnabled
						: false
			};

		const currentModels = atSelectedModel?.id ? [atSelectedModel.id] : selectedModels;

		if (
			currentModels.filter(
				(model) => $models.find((m) => m.id === model)?.info?.meta?.capabilities?.web_search ?? true
			).length === currentModels.length
		) {
			if ($config?.features?.enable_web_search && ($settings?.webSearch ?? false) === 'always') {
				features = { ...features, web_search: true };
			}
		}

		if ($settings?.memory ?? false) {
			features = { ...features, memory: true };
		}

		return features;
	};

	const canCurrentModelsToggleReasoning = () => {
		const currentModels = atSelectedModel?.id ? [atSelectedModel.id] : selectedModels;
		return (
			currentModels.length > 0 &&
			currentModels.every(
				(modelId) =>
					$models.find((model) => model.id === modelId)?.info?.meta?.capabilities
						?.toggle_reasoning ?? false
			)
		);
	};

	const getStopTokens = () => {
		const stop = params?.stop ?? $settings?.params?.stop;
		if (!stop) return undefined;

		const tokens = Array.isArray(stop) ? stop : stop.split(',').map((s) => s.trim());

		return tokens
			.filter(Boolean)
			.map((token) => decodeURIComponent(JSON.parse(`"${token.replace(/"/g, '\\"')}"`)));
	};

	const CHAT_SOCKET_READY_TIMEOUT_MS = 20000;

	const isChatSocketReady = (chatSocket: any) => {
		return Boolean(chatSocket?.connected && chatSocket?.id);
	};

	const waitForChatSocketReady = async (): Promise<string> => {
		const currentSocket = get(socket);
		if (isChatSocketReady(currentSocket)) {
			return currentSocket.id;
		}

		return await new Promise<string>((resolve, reject) => {
			let settled = false;
			let attachedSocket: any = null;
			let unsubscribe: Unsubscriber | null = null;
			let timeoutId: ReturnType<typeof setTimeout> | null = null;

			const detachSocket = () => {
				if (attachedSocket) {
					attachedSocket.off('connect', handleConnect);
				}
			};

			const cleanup = () => {
				detachSocket();
				unsubscribe?.();
				if (timeoutId) {
					clearTimeout(timeoutId);
				}
			};

			const finish = (socketId?: string, error?: Error) => {
				if (settled) return;
				settled = true;
				cleanup();
				if (error) {
					reject(error);
				} else {
					resolve(socketId ?? '');
				}
			};

			const resolveIfReady = (nextSocket = attachedSocket) => {
				if (isChatSocketReady(nextSocket)) {
					finish(nextSocket.id);
					return true;
				}
				return false;
			};

			function handleConnect() {
				resolveIfReady(attachedSocket);
			}

			const attachSocket = (nextSocket: any) => {
				if (settled || attachedSocket === nextSocket) {
					resolveIfReady(nextSocket);
					return;
				}

				detachSocket();
				attachedSocket = nextSocket;

				if (!nextSocket || resolveIfReady(nextSocket)) {
					return;
				}

				nextSocket.on('connect', handleConnect);
			};

			timeoutId = setTimeout(() => {
				finish(
					undefined,
					new Error('Não foi possível conectar ao backend. Verifique se ele está em execução e tente novamente.')
				);
			}, CHAT_SOCKET_READY_TIMEOUT_MS);

			unsubscribe = socket.subscribe(attachSocket);
		});
	};

	const sendMessageSocket = async (model, _messages, _history, responseMessageId, _chatId) => {
		const responseMessage = _history.messages[responseMessageId];
		const userMessage = _history.messages[responseMessage.parentId];

		let socketId = '';
		try {
			socketId = await waitForChatSocketReady();
		} catch (error) {
			const errorMessage =
				error instanceof Error
					? error.message
					: 'Não foi possível conectar ao backend. Tente novamente.';

			toast.error(errorMessage);
			responseMessage.error = { content: errorMessage };
			responseMessage.done = true;
			releaseGeneratingMessageAnchor(responseMessageId);
			history.messages[responseMessageId] = responseMessage;
			history.currentId = responseMessageId;
			taskIds = null;

			await tick();
			await scrollToMessageTop(responseMessageId);
			return;
		}

		if ($temporaryChatEnabled && (!_chatId || _chatId === 'local:undefined')) {
			_chatId = `local:${socketId}`;
			await chatId.set(_chatId);
		}

		const chatMessageFiles = _messages
			.filter((message) => message.files)
			.flatMap((message) => message.files);

		// Filter chatFiles to only include files that are in the chatMessageFiles
		chatFiles = chatFiles.filter((item) => {
			const fileExists = chatMessageFiles.some((messageFile) => messageFile.id === item.id);
			return fileExists;
		});

		let files = structuredClone(chatFiles);
		files.push(
			...(userMessage?.files ?? []).filter(
				(item) =>
					['doc', 'text', 'note', 'chat', 'collection'].includes(item.type) ||
					(item.type === 'file' && !(item?.content_type ?? '').startsWith('image/'))
			)
		);
		// Remove duplicates
		files = files.filter(
			(item, index, array) =>
				array.findIndex((i) => JSON.stringify(i) === JSON.stringify(item)) === index
		);

		if (anchoredGeneratingMessageId !== responseMessageId) {
			await anchorGeneratingMessageTop(responseMessageId);
		}
		const wasAnchoredByThisSend = anchoredGeneratingMessageId === responseMessageId;
		eventTarget.dispatchEvent(
			new CustomEvent('chat:start', {
				detail: {
					id: responseMessageId
				}
			})
		);
		await tick();

		let userLocation;
		if ($settings?.userLocation) {
			userLocation = await getAndUpdateUserLocation(localStorage.token).catch((err) => {
				console.error(err);
				return undefined;
			});
		}

		const stream = $settings?.streamResponse ?? true;

		let messages = [
			params?.system || $settings.system
				? {
						role: 'system',
						content: `${params?.system ?? $settings?.system ?? ''}`
					}
				: undefined,
			..._messages.map((message) => ({
				...message,
				content: processDetails(message.content),
				// Include output for temp chats (backend will use it and strip before LLM)
				...(message.output ? { output: message.output } : {})
			}))
		].filter((message) => message);

		messages = messages
			.map((message, idx, arr) => {
				const imageFiles = (message?.files ?? []).filter(
					(file) => file.type === 'image' || (file?.content_type ?? '').startsWith('image/')
				);

				return {
					role: message.role,
					...(message.role === 'user' && imageFiles.length > 0
						? {
								content: [
									{
										type: 'text',
										text: message?.merged?.content ?? message.content
									},
									...imageFiles.map((file) => ({
										type: 'image_url',
										image_url: {
											url: file.url
										}
									}))
								]
							}
						: {
								content: message?.merged?.content ?? message.content
							})
				};
			})
			.filter((message) => message?.role === 'user' || message?.content?.trim());

		const toolIds = [];
		const toolServerIds = [];

		for (const toolId of selectedToolIds) {
			if (toolId.startsWith('direct_server:')) {
				let serverId = toolId.replace('direct_server:', '');
				// Check if serverId is a number
				if (!isNaN(parseInt(serverId))) {
					toolServerIds.push(parseInt(serverId));
				} else {
					toolServerIds.push(serverId);
				}
			} else {
				toolIds.push(toolId);
			}
		}

		// Parse skill mentions (<$skillId|label>) from user messages
		const skillMentionRegex = /<\$([^|>]+)\|?[^>]*>/g;
		const skillIds = [];
		for (const message of messages) {
			const content =
				typeof message.content === 'string' ? message.content : (message.content?.[0]?.text ?? '');
			for (const match of content.matchAll(skillMentionRegex)) {
				if (!skillIds.includes(match[1])) {
					skillIds.push(match[1]);
				}
			}
		}

		// Strip skill mentions from message content
		if (skillIds.length > 0) {
			messages = messages.map((message) => {
				if (typeof message.content === 'string') {
					return {
						...message,
						content: message.content.replace(/<\$[^>]+>/g, '').trim()
					};
				} else if (Array.isArray(message.content)) {
					return {
						...message,
						content: message.content.map((part) =>
							part.type === 'text'
								? { ...part, text: part.text.replace(/<\$[^>]+>/g, '').trim() }
								: part
						)
					};
				}
				return message;
			});
		}

		// Use the user-selected terminal from the dropdown
		const activeTerminalId = $selectedTerminalId ?? null;

		const res = await generateOpenAIChatCompletion(
			localStorage.token,
			{
				stream: stream,
				model: model.id,
				messages: messages,
				params: {
					...$settings?.params,
					...params,
					...(!thinkingExtendedEnabled && canCurrentModelsToggleReasoning()
						? {
								temperature: 0.5,
								min_p: 0.1,
								dry_multiplier: 0.1,
								reasoning_extended: false
							}
						: {}),
					stop: getStopTokens(),
					...(!thinkingEnabled && canCurrentModelsToggleReasoning() ? { no_think: true } : {})
				},

				files: (files?.length ?? 0) > 0 ? files : undefined,

				filter_ids: selectedFilterIds.length > 0 ? selectedFilterIds : undefined,
				tool_ids: toolIds.length > 0 ? toolIds : undefined,
				skill_ids: skillIds.length > 0 ? skillIds : undefined,
				terminal_id: activeTerminalId ?? undefined,
				tool_servers: [
					...($toolServers ?? []).filter(
						(server, idx) => toolServerIds.includes(idx) || toolServerIds.includes(server?.id)
					),
					// Direct terminal servers — always included when enabled (not routed through selectedToolIds)
					...($terminalServers ?? []).filter((t) => !t.id)
				],
				features: getFeatures(),
				variables: {
					...getPromptVariables(
						$user?.name,
						$settings?.userLocation ? userLocation : undefined,
						$user?.email
					)
				},
				model_item: $models.find((m) => m.id === model.id),

				session_id: socketId,
				chat_id: _chatId,

				id: responseMessageId,
				parent_id: userMessage?.id ?? null,
				parent_message: userMessage,

				background_tasks: {
					...(!$temporaryChatEnabled &&
					(messages.length == 1 ||
						(messages.length == 2 &&
							messages.at(0)?.role === 'system' &&
							messages.at(1)?.role === 'user')) &&
					(selectedModels[0] === model.id || atSelectedModel !== undefined)
						? {
								title_generation: false
							}
						: {}),
					follow_up_generation: false
				},

				...(stream && (model.info?.meta?.capabilities?.usage ?? false)
					? {
							stream_options: {
								include_usage: true
							}
						}
					: {})
			},
			`${NEVEAI_BASE_URL}/api`
		).catch(async (error) => {
			console.log(error);

			let errorMessage = error;
			if (error?.error?.message) {
				errorMessage = error.error.message;
			} else if (error?.message) {
				errorMessage = error.message;
			}

			if (typeof errorMessage === 'object') {
				errorMessage = $i18n.t(`Uh-oh! There was an issue with the response.`);
			}
			errorMessage = normalizeContextSizeErrorMessage(errorMessage);

			toast.error(`${errorMessage}`);
			responseMessage.error = {
				content: error
			};

			responseMessage.done = true;
			releaseGeneratingMessageAnchor(responseMessageId);

			history.messages[responseMessageId] = responseMessage;
			history.currentId = responseMessageId;

			return null;
		});

		if (res) {
			if (res.error) {
				await handleOpenAIError(res.error, responseMessage);
			} else {
				if (taskIds) {
					taskIds.push(res.task_id);
				} else {
					taskIds = [res.task_id];
				}
			}
		}

		await tick();
		const latestResponseMessage = history.messages[responseMessageId] ?? responseMessage;
		if (
			!wasAnchoredByThisSend &&
			latestResponseMessage?.done !== true &&
			anchoredGeneratingMessageId !== responseMessageId
		) {
			await scrollToMessageTop(responseMessageId);
		} else {
			scheduleScrollStateUpdate({ updateAutoScroll: !anchoredGeneratingMessageId });
		}
	};

	const handleOpenAIError = async (error, responseMessage) => {
		let errorMessage = '';
		let innerError;

		if (error) {
			innerError = error;
		}

		console.error(innerError);
		if ('detail' in innerError) {
			// FastAPI error
			errorMessage = innerError.detail;
		} else if ('error' in innerError) {
			// OpenAI error
			if ('message' in innerError.error) {
				errorMessage = innerError.error.message;
			} else {
				errorMessage = innerError.error;
			}
		} else if ('message' in innerError) {
			// OpenAI error
			errorMessage = innerError.message;
		}
		errorMessage = normalizeContextSizeErrorMessage(errorMessage);
		toast.error(errorMessage);

		responseMessage.error = {
			content: $i18n.t(`Uh-oh! There was an issue with the response.`) + '\n' + errorMessage
		};
		responseMessage.done = true;
		releaseGeneratingMessageAnchor(responseMessage.id);

		if (responseMessage.statusHistory) {
			responseMessage.statusHistory = responseMessage.statusHistory.filter(
				(status) => status.action !== 'knowledge_search'
			);
		}

		history.messages[responseMessage.id] = responseMessage;
	};

	const stopResponse = async () => {
		// Cancel pending content flush
		if (_flushRAF) {
			cancelAnimationFrame(_flushRAF);
			_flushRAF = null;
		}
		_contentBuffers.clear();

		if (musicGenerationEnabled) {
			void fetch(`${NEVEAI_API_BASE_URL}/music-generation/cancel`, {
				method: 'POST',
				headers: {
					Accept: 'application/json',
					...(localStorage.token && { Authorization: `Bearer ${localStorage.token}` })
				}
			}).catch(() => null);
		}

		if (taskIds) {
			for (const taskId of taskIds) {
				const res = await stopTask(localStorage.token, taskId).catch((error) => {
					toast.error(`${error}`);
					return null;
				});
			}

			taskIds = null;

			const responseMessage = history.messages[history.currentId];
			// Set all response messages to done
			if (responseMessage.parentId && history.messages[responseMessage.parentId]) {
				for (const messageId of history.messages[responseMessage.parentId].childrenIds) {
					history.messages[messageId].done = true;
					releaseGeneratingMessageAnchor(messageId);
				}
			}

			history.messages[history.currentId] = responseMessage;

			if (autoScroll) {
				scrollToBottom();
			}
		}

		if (generating) {
			generating = false;
			generationController?.abort();
			generationController = null;
		}
	};

	const submitMessage = async (parentId, prompt) => {
		let userPrompt = prompt;
		let userMessageId = uuidv4();

		let userMessage = {
			id: userMessageId,
			parentId: parentId,
			childrenIds: [],
			role: 'user',
			content: userPrompt,
			models: selectedModels,
			timestamp: Math.floor(Date.now() / 1000) // Unix epoch
		};

		if (parentId !== null) {
			history.messages[parentId].childrenIds = [
				...history.messages[parentId].childrenIds,
				userMessageId
			];
		}

		history.messages[userMessageId] = userMessage;
		history.currentId = userMessageId;

		await tick();

		await sendMessage(history, userMessageId);
	};

	const regenerateResponse = async (message, suggestionPrompt = null) => {
		console.log('regenerateResponse');

		if (history.currentId) {
			let userMessage = history.messages[message.parentId];

			if (!userMessage) {
				toast.error($i18n.t('Parent message not found'));
				return;
			}

			if (!suggestionPrompt) {
				const modelId = message?.selectedModelId ?? message.model;
				const model = $models.find((model) => model.id === modelId);

				if (!model) {
					toast.error($i18n.t(`Model {{modelId}} not found`, { modelId }));
					return;
				}

				if (!(await ensureLocalModelsReady([model.id]))) {
					return;
				}

				stopContentFlush(message.id);

				const responseMessage = {
					...history.messages[message.id],
					content: '',
					done: false,
					error: undefined,
					files: undefined,
					sources: undefined,
					citations: undefined,
					usage: undefined,
					output: undefined,
					originalContent: undefined,
					lastSentence: undefined,
					statusHistory: undefined,
					timestamp: Math.floor(Date.now() / 1000)
				};

				history.messages[message.id] = responseMessage;
				history.currentId = message.id;
				history = history;

				await tick();
				await anchorGeneratingMessageTop(userMessage.id, message.id, {
					topOffset: USER_MESSAGE_ANCHOR_TOP_OFFSET_PX,
					stabilizeAcrossFrames: false
				});
				await saveChatHandler($chatId, history);

				const chatEventEmitter = await getChatEventEmitter(model.id, $chatId);
				const _history = structuredClone(history);

				await sendMessageSocket(
					model,
					createMessagesList(_history, message.id),
					_history,
					message.id,
					$chatId
				);

				if (chatEventEmitter) clearInterval(chatEventEmitter);

				currentChatPage.set(1);
				chats.set(await getChatList(localStorage.token, $currentChatPage));
				return;
			}

			const retryModelIds =
				(userMessage?.models ?? [...selectedModels]).length > 1
					? [message?.selectedModelId ?? message.model]
					: selectedModels;

			if (!(await ensureLocalModelsReady(retryModelIds))) {
				return;
			}

			await sendMessage(history, userMessage.id, {
				...(suggestionPrompt
					? {
							messages: [
								...createMessagesList(history, message.id),
								{
									role: 'user',
									content: suggestionPrompt
								}
							]
						}
					: {}),
				...((userMessage?.models ?? [...selectedModels]).length > 1
					? {
							// If multiple models are selected, use the model from the message
							modelId: message.model,
							modelIdx: message.modelIdx
						}
					: {})
			});
		}
	};

	const continueResponse = async () => {
		console.log('continueResponse');
		const _chatId = JSON.parse(JSON.stringify($chatId));

		if (history.currentId && history.messages[history.currentId].done == true) {
			const responseMessage = history.messages[history.currentId];
			const model = $models
				.filter((m) => m.id === (responseMessage?.selectedModelId ?? responseMessage.model))
				.at(0);

			if (model) {
				if (!(await ensureLocalModelsReady([model.id]))) {
					return;
				}

				responseMessage.done = false;
				await tick();
				await anchorGeneratingMessageBottom(responseMessage.id);

				await sendMessageSocket(
					model,
					createMessagesList(history, responseMessage.id),
					history,
					responseMessage.id,
					_chatId
				);
			} else {
				toast.error(
					$i18n.t(`Model {{modelId}} not found`, {
						modelId: responseMessage?.selectedModelId ?? responseMessage.model
					})
				);
			}
		}
	};

	const mergeResponses = async (messageId, responses, _chatId) => {
		console.log('mergeResponses', messageId, responses);
		const message = history.messages[messageId];
		const mergedResponse = {
			status: true,
			content: ''
		};
		message.merged = mergedResponse;
		history.messages[messageId] = message;
		await anchorGeneratingMessageTop(messageId);

		try {
			generating = true;
			const [res, controller] = await generateMoACompletion(
				localStorage.token,
				message.model ?? '',
				message.parentId ? history.messages[message.parentId].content : '',
				responses
			);

			if (res && res.ok && res.body && generating) {
				generationController = controller as AbortController;
				const textStream = await createOpenAITextStream(
					res.body,
					Boolean($settings?.splitLargeChunks ?? false)
				);
				for await (const update of textStream) {
					const { value, done, sources, error, usage } = update;
					if (error || done) {
						generating = false;
						generationController = null;
						break;
					}

					if (mergedResponse.content == '' && value == '\n') {
						continue;
					} else {
						mergedResponse.content += value;
						history.messages[messageId] = message;
					}

					if (autoScroll) {
						scheduleStreamingAwareScrollToBottom(messageId);
					}
				}

				await saveChatHandler(_chatId, history);
			} else {
				console.error(res);
			}
		} catch (e) {
			console.error(e);
		} finally {
			releaseGeneratingMessageAnchor(messageId);
		}
	};

	const getMessageTextForTitle = (content) => {
		if (typeof content === 'string') return content;
		if (Array.isArray(content)) {
			return content
				.filter((part) => part?.type === 'text' && typeof part?.text === 'string')
				.map((part) => part.text)
				.join(' ');
		}
		return '';
	};

	const getInitialImageChatTitle = (history) => {
		const firstUserMessage = createMessagesList(history, history.currentId).find(
			(message) => message?.role === 'user'
		);
		const title = getMessageTextForTitle(firstUserMessage?.content)
			.replace(/<\$[^>]+>/g, '')
			.replace(/\s+/g, ' ')
			.trim();
		return title.length > 100 ? `${title.slice(0, 100)}...` : title;
	};

	const initChatHandler = async (history) => {
		let _chatId = $chatId;

		if (!$temporaryChatEnabled) {
			const initialTitle = stableDiffusionEnabled || musicGenerationEnabled
				? getInitialImageChatTitle(history) || $i18n.t('New Chat')
				: $i18n.t('New Chat');

			chat = await createNewChat(
				localStorage.token,
				{
					id: _chatId,
					title: initialTitle,
					models: selectedModels,
					system: $settings.system ?? undefined,
					params: params,
					history: history,
					messages: createMessagesList(history, history.currentId),
					tags: [],
					timestamp: Date.now()
				},
				$selectedFolder?.id
			);

			_chatId = chat.id;
			await chatId.set(_chatId);

			window.history.replaceState(history.state, '', `/c/${_chatId}`);

			await tick();

			await chats.set(await getChatList(localStorage.token, $currentChatPage));
			currentChatPage.set(1);

			selectedFolder.set(null);
		} else {
			_chatId = `local:${$socket?.id}`; // Use socket id for temporary chat
			await chatId.set(_chatId);
		}
		await tick();

		return _chatId;
	};

	const saveChatHandler = async (_chatId, history) => {
		if ($chatId == _chatId) {
			if (!$temporaryChatEnabled) {
				chat = await updateChatById(localStorage.token, _chatId, {
					models: selectedModels,
					history: history,
					messages: createMessagesList(history, history.currentId),
					params: params,
					files: chatFiles
				});
				currentChatPage.set(1);
				await chats.set(await getChatList(localStorage.token, $currentChatPage));
			}
		}
	};

	const MAX_DRAFT_LENGTH = 5000;
	let saveDraftTimeout: ReturnType<typeof setTimeout> | null = null;

	const saveDraft = async (draft, chatId = null) => {
		if (saveDraftTimeout) {
			clearTimeout(saveDraftTimeout);
		}

		if (draft.prompt !== null && draft.prompt.length < MAX_DRAFT_LENGTH) {
			saveDraftTimeout = setTimeout(async () => {
				await sessionStorage.setItem(
					`chat-input${chatId ? `-${chatId}` : ''}`,
					JSON.stringify(draft)
				);
			}, 500);
		} else {
			sessionStorage.removeItem(`chat-input${chatId ? `-${chatId}` : ''}`);
		}
	};

	const clearDraft = async (chatId = null) => {
		if (saveDraftTimeout) {
			clearTimeout(saveDraftTimeout);
		}
		await sessionStorage.removeItem(`chat-input${chatId ? `-${chatId}` : ''}`);
	};

	const moveChatHandler = async (chatId, folderId) => {
		if (chatId && folderId) {
			const res = await updateChatFolderIdById(localStorage.token, chatId, folderId).catch(
				(error) => {
					toast.error(`${error}`);
					return null;
				}
			);

			if (res) {
				currentChatPage.set(1);
				await chats.set(await getChatList(localStorage.token, $currentChatPage));
				await pinnedChats.set(await getPinnedChatList(localStorage.token));

				toast.success($i18n.t('Chat moved successfully'));
			}
		} else {
			toast.error($i18n.t('Failed to move chat'));
		}
	};
</script>

<svelte:head>
	<title>
		{$settings.showChatTitleInTab !== false && $chatTitle
			? `${$chatTitle.length > 30 ? `${$chatTitle.slice(0, 30)}...` : $chatTitle} • ${$NEVEAI_NAME}`
			: `${$NEVEAI_NAME}`}
	</title>
</svelte:head>

<audio id="audioElement" src="" style="display: none;"></audio>

<EventConfirmDialog
	bind:show={showEventConfirmation}
	title={eventConfirmationTitle}
	message={eventConfirmationMessage}
	input={eventConfirmationInput}
	inputPlaceholder={eventConfirmationInputPlaceholder}
	inputValue={eventConfirmationInputValue}
	inputType={eventConfirmationInputType}
	on:confirm={(e) => {
		if (e.detail) {
			eventCallback(e.detail);
		} else {
			eventCallback(true);
		}
	}}
	on:cancel={() => {
		eventCallback(false);
	}}
/>

{#if showContextModal}
	<div class="fixed inset-0 z-[10001] flex items-center justify-center bg-black/40" transition:fade={{ duration: 80 }}>
		<div class="bg-white dark:bg-gray-900 rounded-2xl p-5 shadow-xl mx-4 w-80 flex flex-col gap-3">
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
					on:click={cancelContextModal}
				>Cancelar</button>
				<button
					class="px-4 py-1.5 text-xs rounded-lg bg-black text-white dark:bg-white dark:text-black hover:opacity-90 transition font-medium"
					on:click={confirmContextModal}
				>Confirmar</button>
			</div>
		</div>
	</div>
{/if}

{#if showVisionModal}
	<div class="fixed inset-0 z-[10001] flex items-center justify-center bg-black/40" transition:fade={{ duration: 80 }}>
		<div class="bg-white dark:bg-gray-900 rounded-2xl p-5 shadow-xl mx-4 w-80 flex flex-col gap-3">
			<p class="text-sm font-semibold text-gray-900 dark:text-white">Deseja carregar a visão?</p>
			<p class="text-xs text-gray-500 dark:text-gray-400">
				{visionModalModelName} será carregado com suporte a análise de imagens.
			</p>
			<div class="flex justify-end gap-2 mt-1">
				<button
					class="px-4 py-1.5 text-xs rounded-lg bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 transition font-medium"
					on:click={declineVisionModal}
				>Não</button>
				<button
					class="px-4 py-1.5 text-xs rounded-lg bg-black text-white dark:bg-white dark:text-black hover:opacity-90 transition font-medium"
					on:click={confirmVisionModal}
				>Sim</button>
			</div>
		</div>
	</div>
{/if}

<div
	class="h-screen max-h-[100dvh] w-full max-w-full flex flex-col"
	id="chat-container"
>
	{#if !loading}
		<div in:fade={{ duration: 50 }} class="w-full h-full flex flex-col">
			{#if $selectedFolder && $selectedFolder?.meta?.background_image_url}
				<div
					class="absolute top-0 left-0 w-full h-full bg-cover bg-center bg-no-repeat"
					style="background-image: url({$selectedFolder?.meta?.background_image_url})  "
				/>

				<div
					class="absolute top-0 left-0 w-full h-full bg-linear-to-t from-white to-white/85 dark:from-black dark:to-black/90 z-0"
				/>
			{:else if $settings?.backgroundImageUrl ?? $config?.license_metadata?.background_image_url ?? null}
				<div
					class="absolute top-0 left-0 w-full h-full bg-cover bg-center bg-no-repeat"
					style="background-image: url({$settings?.backgroundImageUrl ??
						$config?.license_metadata?.background_image_url})  "
				/>

				<div
					class="absolute top-0 left-0 w-full h-full bg-linear-to-t from-white to-white/85 dark:from-black dark:to-black/90 z-0"
				/>
			{/if}

			<PaneGroup direction="horizontal" class="w-full h-full">
				<Pane defaultSize={50} minSize={$showArtifacts ? 38 : 30} class="h-full flex relative max-w-full flex-col">
					<FilesOverlay show={dragged} />
					<Navbar
						bind:this={navbarElement}
						chat={{
							id: $chatId,
							chat: {
								title: $chatTitle,
								models: selectedModels,
								system: $settings.system ?? undefined,
								params: params,
								history: history,
								timestamp: Date.now()
							}
						}}
						{history}
						title={$chatTitle}
						bind:selectedModels
						shareEnabled={!!history.currentId}
						{initNewChat}
						{moveChatHandler}
						onSaveTempChat={async () => {
							try {
								if (!history?.currentId || !Object.keys(history.messages).length) {
									toast.error($i18n.t('No conversation to save'));
									return;
								}
								const messages = createMessagesList(history, history.currentId);
								const title =
									messages.find((m) => m.role === 'user')?.content ?? $i18n.t('New Chat');

								const savedChat = await createNewChat(
									localStorage.token,
									{
										id: uuidv4(),
										title: title.length > 50 ? `${title.slice(0, 50)}...` : title,
										models: selectedModels,
										params: params,
										history: history,
										messages: messages,
										timestamp: Date.now()
									},
									null
								);

								if (savedChat) {
									temporaryChatEnabled.set(false);
									chatId.set(savedChat.id);
									chats.set(await getChatList(localStorage.token, $currentChatPage));

									await goto(`/c/${savedChat.id}`);
									toast.success($i18n.t('Conversation saved successfully'));
								}
							} catch (error) {
								console.error('Error saving conversation:', error);
								toast.error($i18n.t('Failed to save conversation'));
							}
						}}
					/>

					<div id="chat-pane" class="flex flex-col flex-auto z-10 w-full @container overflow-auto">
						{#if ($settings?.landingPageMode === 'chat' && !$selectedFolder) || createMessagesList(history, history.currentId).length > 0}
							<div
								class=" pb-2.5 flex flex-col justify-between w-full flex-auto overflow-auto h-0 max-w-full z-10 scrollbar-hidden"
								id="messages-container"
								bind:this={messagesContainerElement}
								style="overflow-anchor: none; scrollbar-gutter: stable both-edges;"
								on:wheel|nonpassive={preventMessagesBottomWheelJitter}
								on:pointerdown={beginGenerationSpacerPointerScroll}
								on:pointerup={endGenerationSpacerPointerScroll}
								on:pointercancel={endGenerationSpacerPointerScroll}
								on:pointerleave={endGenerationSpacerPointerScroll}
								on:scroll={(e) => {
									consumeGenerationSpacerFromUpwardScroll();
									if (clampMessagesBottomWheelJitter()) {
										return;
									}
									if (clampIdleGenerationSpacerScroll()) {
										return;
									}
									updateScrollStateFromContainer();
								}}
							>
								<div class=" min-h-full w-full flex flex-col" use:observeMessagesContentSize>
									<Messages
										chatId={$chatId}
										bind:history
										bind:autoScroll
										bind:prompt
										setInputText={(text) => {
											messageInput?.setText(text);
										}}
										{selectedModels}
										{atSelectedModel}
										{sendMessage}
										{showMessage}
										{submitMessage}
										{continueResponse}
										{regenerateResponse}
										{mergeResponses}
										{chatActionHandler}
										{addMessages}
										topPadding={true}
										bottomPadding={files.length > 0}
										bottomSpacerHeight={generationBottomSpacerHeight}
										{onSelect}
									/>
								</div>
							</div>

							<div class=" pb-2 z-10 w-full flex flex-col items-center">
								<MessageInput
									bind:this={messageInput}
									{history}
									{taskIds}
									{selectedModels}
									{showScrollToBottomButton}
									onScrollToBottom={scrollToBottomFromInput}
									bind:files
									bind:prompt
									bind:autoScroll
									bind:selectedToolIds
									bind:selectedFilterIds
									bind:imageGenerationEnabled
									bind:codeExecutionEnabled
									bind:webSearchEnabled
									bind:deepSearchEnabled
									bind:stableDiffusionEnabled
									bind:musicGenerationEnabled
									bind:thinkingEnabled
									bind:thinkingExtendedEnabled
									bind:atSelectedModel
									bind:showCommands
									bind:dragged
									toolServers={$toolServers}
									{generating}
									sendDisabled={modelLoading}
									{stopResponse}
									{createMessagePair}
									{onUpload}
									{messageQueue}
									onQueueSendNow={async (id) => {
										const item = messageQueue.find((m) => m.id === id);
										if (item) {
											// Remove from queue
											messageQueue = messageQueue.filter((m) => m.id !== id);
											// Stop current generation first
											await stopResponse();
											await tick();
											// Set files and submit
											files = item.files;
											await tick();
											await submitPrompt(item.prompt);
										}
									}}
									onQueueEdit={(id) => {
										const item = messageQueue.find((m) => m.id === id);
										if (item) {
											// Remove from queue
											messageQueue = messageQueue.filter((m) => m.id !== id);
											// Set files and restore prompt to input
											files = item.files;
											messageInput?.setText(item.prompt);
										}
									}}
									onQueueDelete={(id) => {
										messageQueue = messageQueue.filter((m) => m.id !== id);
									}}
									onChange={(data) => {
										if (!$temporaryChatEnabled) {
											saveDraft(data, $chatId);
										}
									}}
									on:submit={async (e) => {
										clearDraft();
										if (e.detail || files.length > 0) {
											await tick();

											submitPrompt(e.detail.replaceAll('\n\n', '\n'));
										}
									}}
								/>

								<div
									class="absolute bottom-1 text-xs text-gray-500 text-center line-clamp-1 right-0 left-0"
								>
									<!-- {$i18n.t('LLMs can make mistakes. Verify important information.')} -->
								</div>
							</div>
						{:else}
							<div class="flex items-center h-full">
								<Placeholder
									{history}
									{selectedModels}
									bind:messageInput
									bind:files
									bind:prompt
									bind:autoScroll
									bind:selectedToolIds
									bind:selectedFilterIds
									bind:imageGenerationEnabled
									bind:codeExecutionEnabled
									bind:webSearchEnabled
									bind:deepSearchEnabled
									bind:stableDiffusionEnabled
									bind:musicGenerationEnabled
									bind:thinkingEnabled
									bind:thinkingExtendedEnabled
									bind:atSelectedModel
									bind:showCommands
									bind:dragged
									toolServers={$toolServers}
									sendDisabled={modelLoading}
									{stopResponse}
									{createMessagePair}
									{onSelect}
									{onUpload}
									onChange={(data) => {
										if (!$temporaryChatEnabled) {
											saveDraft(data);
										}
									}}
									on:submit={async (e) => {
										clearDraft();
										if (e.detail || files.length > 0) {
											await tick();
											submitPrompt(e.detail.replaceAll('\n\n', '\n'));
										}
									}}
								/>
							</div>
						{/if}
					</div>
				</Pane>

				<ModelSettingsSheet
					bind:params
					bind:chatFiles
					thinkingExtendedEnabled={thinkingExtendedEnabled || !canCurrentModelsToggleReasoning()}
					selectedModelName={$models.find((m) => m.id === selectedModelIds?.at(0))?.name ?? selectedModelIds?.at(0) ?? ''}
				/>

				<ChatControls
					bind:this={controlPaneComponent}
					bind:history
					bind:chatFiles
					bind:params
					bind:files
					bind:pane={controlPane}
					chatId={$chatId}
					modelId={selectedModelIds?.at(0) ?? null}
					models={selectedModelIds.reduce((a, e, i, arr) => {
						const model = $models.find((m) => m.id === e);
						if (model) {
							return [...a, model];
						}
						return a;
					}, [])}
					{submitPrompt}
					{stopResponse}
					{showMessage}
					{eventTarget}
				/>
			</PaneGroup>
		</div>
	{:else if loading}
		<div class=" flex items-center justify-center h-full w-full">
			<div class="m-auto">
				<Spinner className="size-5" />
			</div>
		</div>
	{/if}
</div>

<style>
	::-webkit-scrollbar {
		height: 0.5rem;
		width: 0.5rem;
	}
</style>
