<script lang="ts">
	import DOMPurify from 'dompurify';
	import { toast } from 'svelte-sonner';

	import { marked } from 'marked';
	import { v4 as uuidv4 } from 'uuid';
	import dayjs from '$lib/dayjs';
	import duration from 'dayjs/plugin/duration';
	import relativeTime from 'dayjs/plugin/relativeTime';

	dayjs.extend(duration);
	dayjs.extend(relativeTime);

	import { onMount, tick, getContext, createEventDispatcher } from 'svelte';

	import { createPicker, getAuthToken } from '$lib/utils/google-drive-picker';
	import { pickAndDownloadFile } from '$lib/utils/onedrive-file-picker';
	import { KokoroWorker } from '$lib/workers/KokoroWorker';

	const dispatch = createEventDispatcher();

	import {
		type Model,
		mobile,
		settings,
		models,
		config,
		showCallOverlay,
		tools,
		toolServers,
		terminalServers,
		user as _user,
		showControls,
		showArtifacts,
		showSettings,
		selectedTerminalId,
		TTSWorker,
		temporaryChatEnabled,
		chatId
	} from '$lib/stores';
	import { getChatById } from '$lib/apis/chats';

	import {
		convertHeicToJpeg,
		compressImage,
		createMessagesList,
		extractContentFromFile,
		extractCurlyBraceWords,
		extractInputVariables,
		getAge,
		getCurrentDateTime,
		getFormattedDate,
		getFormattedTime,
		getUserPosition,
		getUserTimezone,
		getWeekday
	} from '$lib/utils';
	import { uploadFile } from '$lib/apis/files';
	import { generateAutoCompletion } from '$lib/apis';
	import { deleteFileById } from '$lib/apis/files';
	import { getSessionUser } from '$lib/apis/auths';
	import { getTools } from '$lib/apis/tools';

	import { fly } from 'svelte/transition';
	import { WEBUI_BASE_URL, WEBUI_API_BASE_URL, PASTED_TEXT_CHARACTER_LIMIT } from '$lib/constants';

	import { createNoteHandler } from '../notes/utils';
	import { getSuggestionRenderer } from '../common/RichTextInput/suggestions';

	import InputMenu from './MessageInput/InputMenu.svelte';

	import ToolServersModal from './ToolServersModal.svelte';

	import RichTextInput from '../common/RichTextInput.svelte';
	import Tooltip from '../common/Tooltip.svelte';
	import FileItem from '../common/FileItem.svelte';
	import Image from '../common/Image.svelte';
	import Spinner from '../common/Spinner.svelte';

	import XMark from '../icons/XMark.svelte';
	import GlobeAlt from '../icons/GlobeAlt.svelte';
	import Photo from '../icons/Photo.svelte';
	import Wrench from '../icons/Wrench.svelte';
	import Sparkles from '../icons/Sparkles.svelte';

	import InputVariablesModal from './MessageInput/InputVariablesModal.svelte';
	import Voice from '../icons/Voice.svelte';
	import Cloud from '../icons/Cloud.svelte';
	import Terminal from '../icons/Terminal.svelte';
	import Code from '../icons/Code.svelte';
	import TerminalMenu from './MessageInput/TerminalMenu.svelte';
	import Knobs from '../icons/Knobs.svelte';
	import PlusAlt from '../icons/PlusAlt.svelte';
	import Dropdown from '../common/Dropdown.svelte';

	import { DropdownMenu } from 'bits-ui';
	import { flyAndScale } from '$lib/utils/transitions';

	import CommandSuggestionList from './MessageInput/CommandSuggestionList.svelte';
	import ValvesModal from '../workspace/common/ValvesModal.svelte';
	import PageEdit from '../icons/PageEdit.svelte';
	import { goto } from '$app/navigation';
	import InputModal from '../common/InputModal.svelte';
	import QueuedMessageItem from './MessageInput/QueuedMessageItem.svelte';

	const i18n = getContext('i18n');

	export let onUpload: Function = (e) => {};
	export let onChange: Function = () => {};

	export let createMessagePair: Function;
	export let stopResponse: Function;

	export let autoScroll = false;
	export let generating = false;
	export let uploadPending = false;

	export let atSelectedModel: Model | undefined = undefined;
	export let selectedModels: [''];

	let selectedModelIds = [];
	$: selectedModelIds = atSelectedModel !== undefined ? [atSelectedModel.id] : selectedModels;

	export let history;
	export let taskIds = null;

	export let prompt = '';
	export let files = [];
	export let sendDisabled = false;

	export let selectedToolIds = [];
	export let selectedFilterIds = [];

	export let imageGenerationEnabled = false;
	export let webSearchEnabled = false;
	export let codeInterpreterEnabled = false;
	export let codeExecutionEnabled = false;
	export let stableDiffusionEnabled = false;
	export let thinkingEnabled = true;

	let showTerminalMenu = false;

	export let messageQueue: { id: string; prompt: string; files: any[] }[] = [];
	export let onQueueSendNow: (id: string) => void = () => {};
	export let onQueueEdit: (id: string) => void = () => {};
	export let onQueueDelete: (id: string) => void = () => {};

	let inputContent = null;

	let showInputVariablesModal = false;
	let inputVariablesModalCallback = (variableValues) => {};
	let inputVariables = {};
	let inputVariableValues = {};

	let showValvesModal = false;
	let selectedValvesType = 'tool'; // 'tool' or 'function'
	let selectedValvesItemId = null;

	$: onChange({
		prompt,
		files: files
			.filter((file) => file.type !== 'image')
			.map((file) => {
				return {
					...file,
					user: undefined,
					access_grants: undefined
				};
			}),
		selectedToolIds,
		selectedFilterIds,
		imageGenerationEnabled,
		webSearchEnabled,
		codeInterpreterEnabled,
		codeExecutionEnabled,
		stableDiffusionEnabled,
		thinkingEnabled
	});

	$: isCompact =
		atSelectedModel === undefined &&
		!history?.currentId &&
		files.length === 0 &&
		!webSearchEnabled &&
		!imageGenerationEnabled &&
		!codeInterpreterEnabled &&
		!codeExecutionEnabled &&
		!stableDiffusionEnabled &&
		(selectedToolIds ?? []).length === 0 &&
		(selectedFilterIds ?? []).length === 0 &&
		!isInputMultiline;

	let showTokenPopup = false;

	// Token usage from the last assistant message
	$: lastUsage = (() => {
		if (!history?.messages || !history?.currentId) return null;
		let id = history.currentId;
		while (id) {
			const msg = history.messages[id];
			if (msg?.role === 'assistant' && msg?.done && msg?.usage) return msg.usage;
			id = msg?.parentId;
		}
		return null;
	})();

	function formatTokens(n: number): string {
		if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M';
		if (n >= 1_000) return (n / 1_000).toFixed(1) + 'K';
		return String(n);
	}

	const inputVariableHandler = async (text: string): Promise<string> => {
		inputVariables = extractInputVariables(text);

		// No variables? return the original text immediately.
		if (Object.keys(inputVariables).length === 0) {
			return text;
		}
		showInputVariablesModal = true;
		return await new Promise<string>((resolve) => {
			inputVariablesModalCallback = (variableValues) => {
				inputVariableValues = { ...inputVariableValues, ...variableValues };
				replaceVariables(inputVariableValues);
				showInputVariablesModal = false;
				resolve(text);
			};
		});
	};

	const textVariableHandler = async (text: string) => {
		if (text.includes('{{CLIPBOARD}}')) {
			const clipboardText = await navigator.clipboard.readText().catch((err) => {
				toast.error($i18n.t('Failed to read clipboard contents'));
				return '{{CLIPBOARD}}';
			});

			const clipboardItems = await navigator.clipboard.read().catch((err) => {
				console.error('Failed to read clipboard items:', err);
				return [];
			});

			for (const item of clipboardItems) {
				for (const type of item.types) {
					if (type.startsWith('image/')) {
						const blob = await item.getType(type);
						const file = new File([blob], `clipboard-image.${type.split('/')[1]}`, {
							type: type
						});

						inputFilesHandler([file]);
					}
				}
			}

			text = text.replaceAll('{{CLIPBOARD}}', clipboardText.replaceAll('\r\n', '\n'));
		}

		if (text.includes('{{USER_LOCATION}}')) {
			let location;
			try {
				location = await getUserPosition();
			} catch (error) {
				toast.error($i18n.t('Location access not allowed'));
				location = 'LOCATION_UNKNOWN';
			}
			text = text.replaceAll('{{USER_LOCATION}}', String(location));
		}

		const sessionUser = await getSessionUser(localStorage.token);

		if (text.includes('{{USER_NAME}}')) {
			const name = sessionUser?.name || 'User';
			text = text.replaceAll('{{USER_NAME}}', name);
		}

		if (text.includes('{{USER_EMAIL}}')) {
			const email = sessionUser?.email || '';

			if (email) {
				text = text.replaceAll('{{USER_EMAIL}}', email);
			}
		}

		if (text.includes('{{USER_BIO}}')) {
			const bio = sessionUser?.bio || '';

			if (bio) {
				text = text.replaceAll('{{USER_BIO}}', bio);
			}
		}

		if (text.includes('{{USER_GENDER}}')) {
			const gender = sessionUser?.gender || '';

			if (gender) {
				text = text.replaceAll('{{USER_GENDER}}', gender);
			}
		}

		if (text.includes('{{USER_BIRTH_DATE}}')) {
			const birthDate = sessionUser?.date_of_birth || '';

			if (birthDate) {
				text = text.replaceAll('{{USER_BIRTH_DATE}}', birthDate);
			}
		}

		if (text.includes('{{USER_AGE}}')) {
			const birthDate = sessionUser?.date_of_birth || '';

			if (birthDate) {
				// calculate age using date
				const age = getAge(birthDate);
				text = text.replaceAll('{{USER_AGE}}', age);
			}
		}

		if (text.includes('{{USER_LANGUAGE}}')) {
			const language = localStorage.getItem('locale') || 'en-US';
			text = text.replaceAll('{{USER_LANGUAGE}}', language);
		}

		if (text.includes('{{CURRENT_DATE}}')) {
			const date = getFormattedDate();
			text = text.replaceAll('{{CURRENT_DATE}}', date);
		}

		if (text.includes('{{CURRENT_TIME}}')) {
			const time = getFormattedTime();
			text = text.replaceAll('{{CURRENT_TIME}}', time);
		}

		if (text.includes('{{CURRENT_DATETIME}}')) {
			const dateTime = getCurrentDateTime();
			text = text.replaceAll('{{CURRENT_DATETIME}}', dateTime);
		}

		if (text.includes('{{CURRENT_TIMEZONE}}')) {
			const timezone = getUserTimezone();
			text = text.replaceAll('{{CURRENT_TIMEZONE}}', timezone);
		}

		if (text.includes('{{CURRENT_WEEKDAY}}')) {
			const weekday = getWeekday();
			text = text.replaceAll('{{CURRENT_WEEKDAY}}', weekday);
		}

		return text;
	};

	const replaceVariables = (variables: Record<string, any>) => {
		console.log('Replacing variables:', variables);

		const chatInput = document.getElementById('chat-input');

		if (chatInput) {
			chatInputElement.replaceVariables(variables);
			chatInputElement.focus();
		}
	};

	export const setText = async (text?: string, cb?: (text: string) => void) => {
		const chatInput = document.getElementById('chat-input');

		if (chatInput) {
			if (text !== '') {
				text = await textVariableHandler(text || '');
			}

			chatInputElement?.setText(text);
			chatInputElement?.focus();

			if (text !== '') {
				text = await inputVariableHandler(text);
			}

			await tick();
			if (cb) await cb(text);
		}
	};

	const getCommand = () => {
		const chatInput = document.getElementById('chat-input');
		let word = '';

		if (chatInput) {
			word = chatInputElement?.getWordAtDocPos();
		}

		return word;
	};

	const replaceCommandWithText = (text) => {
		const chatInput = document.getElementById('chat-input');
		if (!chatInput) return;

		chatInputElement?.replaceCommandWithText(text);
	};

	const insertTextAtCursor = async (text: string) => {
		const chatInput = document.getElementById('chat-input');
		if (!chatInput) return;

		text = await textVariableHandler(text);

		if (command) {
			replaceCommandWithText(text);
		} else {
			chatInputElement?.insertContent(text);
		}

		await tick();
		text = await inputVariableHandler(text);
		await tick();

		const chatInputContainer = document.getElementById('chat-input-container');
		if (chatInputContainer) {
			chatInputContainer.scrollTop = chatInputContainer.scrollHeight;
		}

		await tick();
		if (chatInput) {
			chatInput.focus();
			chatInput.dispatchEvent(new Event('input'));

			const words = extractCurlyBraceWords(prompt);

			if (words.length > 0) {
				const word = words.at(0);
				await tick();
			} else {
				chatInput.scrollTop = chatInput.scrollHeight;
			}
		}
	};

	let command = '';
	export let showCommands = false;
	$: showCommands =
		['/', '#', '@', '$'].includes(command?.charAt(0)) || '\\#' === command?.slice(0, 2);
	let suggestions = null;

	let showTools = false;

	let loaded = false;
	let showThinkingDropdown = false;

	let isComposing = false;
	// Safari has a bug where compositionend is not triggered correctly #16615
	// when using the virtual keyboard on iOS.
	let compositionEndedAt = -2e8;
	const isSafari = /^((?!chrome|android).)*safari/i.test(navigator.userAgent);
	function inOrNearComposition(event: Event) {
		if (isComposing) {
			return true;
		}
		// See https://www.stum.de/2016/06/24/handling-ime-events-in-javascript/.
		// On Japanese input method editors (IMEs), the Enter key is used to confirm character
		// selection. On Safari, when Enter is pressed, compositionend and keydown events are
		// emitted. The keydown event triggers newline insertion, which we don't want.
		// This method returns true if the keydown event should be ignored.
		// We only ignore it once, as pressing Enter a second time *should* insert a newline.
		// Furthermore, the keydown event timestamp must be close to the compositionEndedAt timestamp.
		// This guards against the case where compositionend is triggered without the keyboard
		// (e.g. character confirmation may be done with the mouse), and keydown is triggered
		// afterwards- we wouldn't want to ignore the keydown event in this case.
		if (isSafari && Math.abs(event.timeStamp - compositionEndedAt) < 500) {
			compositionEndedAt = -2e8;
			return true;
		}
		return false;
	}

	let chatInputContainerElement;
	let chatInputElement;

	let filesInputElement;
	let commandsElement;

	let inputFiles;

	let showInputModal = false;

	export let dragged = false;
	let chatDragged = false;
	let shiftKey = false;
	let isInputMultiline = false;
	let chatInputContainerEl: HTMLElement | null = null;

	let user = null;
	export let placeholder = '';

	let visionCapableModels = [];
	$: visionCapableModels = (atSelectedModel?.id ? [atSelectedModel.id] : selectedModels).filter(
		(model) => $models.find((m) => m.id === model)?.info?.meta?.capabilities?.vision ?? true
	);

	let fileUploadCapableModels = [];
	$: fileUploadCapableModels = (atSelectedModel?.id ? [atSelectedModel.id] : selectedModels).filter(
		(model) => $models.find((m) => m.id === model)?.info?.meta?.capabilities?.file_upload ?? true
	);

	let webSearchCapableModels = [];
	$: webSearchCapableModels = (atSelectedModel?.id ? [atSelectedModel.id] : selectedModels).filter(
		(model) => $models.find((m) => m.id === model)?.info?.meta?.capabilities?.web_search ?? true
	);

	let imageGenerationCapableModels = [];
	$: imageGenerationCapableModels = (
		atSelectedModel?.id ? [atSelectedModel.id] : selectedModels
	).filter(
		(model) =>
			$models.find((m) => m.id === model)?.info?.meta?.capabilities?.image_generation ?? true
	);

	let codeInterpreterCapableModels = [];
	$: codeInterpreterCapableModels = (
		atSelectedModel?.id ? [atSelectedModel.id] : selectedModels
	).filter(
		(model) =>
			$models.find((m) => m.id === model)?.info?.meta?.capabilities?.code_interpreter ?? true
	);

	let toggleFilters = [];
	$: toggleFilters = (atSelectedModel?.id ? [atSelectedModel.id] : selectedModels)
		.map((id) => ($models.find((model) => model.id === id) || {})?.filters ?? [])
		.reduce((acc, filters) => acc.filter((f1) => filters.some((f2) => f2.id === f1.id)));

	let showToolsButton = false;
	$: showToolsButton = ($tools ?? []).length > 0 || ($toolServers ?? []).length > 0;

	let showWebSearchButton = false;
	$: showWebSearchButton =
		$_user.role === 'admin' || $_user?.permissions?.features?.web_search;

	let showImageGenerationButton = false;
	$: showImageGenerationButton =
		(atSelectedModel?.id ? [atSelectedModel.id] : selectedModels).length ===
			imageGenerationCapableModels.length &&
		$config?.features?.enable_image_generation &&
		($_user.role === 'admin' || $_user?.permissions?.features?.image_generation);

	let showCodeInterpreterButton = false;
	$: showCodeInterpreterButton =
		!$selectedTerminalId &&
		(atSelectedModel?.id ? [atSelectedModel.id] : selectedModels).length ===
			codeInterpreterCapableModels.length &&
		$config?.features?.enable_code_interpreter &&
		($_user.role === 'admin' || $_user?.permissions?.features?.code_interpreter);

	let showCodeExecutionButton = false;
	$: showCodeExecutionButton =
		($config?.features?.enable_code_execution !== false) &&
		($_user.role === 'admin' || $_user?.permissions?.features?.code_execution !== false);

	let showStableDiffusionButton = false;
	$: showStableDiffusionButton =
		$config?.features?.enable_stable_diffusion &&
		($_user.role === 'admin' || $_user?.permissions?.features?.stable_diffusion);

	let showThinkingButton = false;
	$: showThinkingButton = selectedModels.length > 0 && selectedModels.every(
		(model) => $models.find((m) => m.id === model)?.info?.meta?.capabilities?.toggle_reasoning ?? false
	);
	$: if (!showThinkingButton) {
		thinkingEnabled = true;
	}

	// Disable code interpreter when terminal is active (mutually exclusive)
	$: if ($selectedTerminalId && codeInterpreterEnabled) {
		codeInterpreterEnabled = false;
	}

	const scrollToBottom = () => {
		const element = document.getElementById('messages-container');
		element.scrollTo({
			top: element.scrollHeight,
			behavior: 'smooth'
		});
	};

	const screenCaptureHandler = async () => {
		try {
			// Request screen media
			const mediaStream = await navigator.mediaDevices.getDisplayMedia({
				video: { cursor: 'never' },
				audio: false
			});
			// Once the user selects a screen, temporarily create a video element
			const video = document.createElement('video');
			video.srcObject = mediaStream;
			// Ensure the video loads without affecting user experience or tab switching
			await video.play();
			// Set up the canvas to match the video dimensions
			const canvas = document.createElement('canvas');
			canvas.width = video.videoWidth;
			canvas.height = video.videoHeight;
			// Grab a single frame from the video stream using the canvas
			const context = canvas.getContext('2d');
			context.drawImage(video, 0, 0, canvas.width, canvas.height);
			// Stop all video tracks (stop screen sharing) after capturing the image
			mediaStream.getTracks().forEach((track) => track.stop());

			// bring back focus to this current tab, so that the user can see the screen capture
			window.focus();

			// Convert the canvas to a Base64 image URL
			const imageUrl = canvas.toDataURL('image/png');
			const blob = await (await fetch(imageUrl)).blob();
			const file = new File([blob], `screen-capture-${Date.now()}.png`, { type: 'image/png' });
			inputFilesHandler([file]);
			// Clean memory: Clear video srcObject
			video.srcObject = null;
		} catch (error) {
			// Handle any errors (e.g., user cancels screen sharing)
			console.error('Error capturing screen:', error);
		}
	};

	const uploadFileHandler = async (file, process = true, itemData = {}) => {
		if ($_user?.role !== 'admin' && !($_user?.permissions?.chat?.file_upload ?? true)) {
			toast.error($i18n.t('You do not have permission to upload files.'));
			return null;
		}

		if (fileUploadCapableModels.length !== selectedModels.length) {
			toast.error($i18n.t('Model(s) do not support file upload'));
			return null;
		}

		const tempItemId = uuidv4();
		const fileItem = {
			type: 'file',
			file: '',
			id: null,
			url: '',
			name: file.name,
			collection_name: '',
			status: 'uploading',
			size: file.size,
			error: '',
			itemId: tempItemId,
			...itemData
		};

		if (fileItem.size == 0) {
			toast.error($i18n.t('You cannot upload an empty file.'));
			return null;
		}

		files = [...files, fileItem];

		if (!$temporaryChatEnabled) {
			try {
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

				// During the file upload, file content is automatically extracted.
				const uploadedFile = await uploadFile(localStorage.token, file, metadata, process);

				if (uploadedFile) {
					console.log('File upload completed:', {
						id: uploadedFile.id,
						name: fileItem.name,
						collection: uploadedFile?.meta?.collection_name
					});

					if (uploadedFile.error) {
						console.warn('File upload warning:', uploadedFile.error);
						toast.warning(uploadedFile.error);
					}

					fileItem.status = 'uploaded';
					fileItem.file = uploadedFile;
					fileItem.id = uploadedFile.id;
					fileItem.collection_name =
						uploadedFile?.meta?.collection_name || uploadedFile?.collection_name;
					fileItem.content_type = uploadedFile.meta?.content_type || uploadedFile.content_type;
					fileItem.url = `${uploadedFile.id}`;

					files = files;
				} else {
					files = files.filter((item) => item?.itemId !== tempItemId);
				}
			} catch (e) {
				toast.error(`${e}`);
				files = files.filter((item) => item?.itemId !== tempItemId);
			}
		} else {
			// If temporary chat is enabled, we just add the file to the list without uploading it.

			const content = await extractContentFromFile(file).catch((error) => {
				toast.error(
					$i18n.t('Failed to extract content from the file: {{error}}', { error: error })
				);
				return null;
			});

			if (content === null) {
				toast.error($i18n.t('Failed to extract content from the file.'));
				files = files.filter((item) => item?.itemId !== tempItemId);
				return null;
			} else {
				console.log('Extracted content from file:', {
					name: file.name,
					size: file.size,
					content: content
				});

				fileItem.status = 'uploaded';
				fileItem.type = 'text';
				fileItem.content = content;
				fileItem.id = uuidv4(); // Temporary ID for the file

				files = files;
			}
		}
	};

	const inputFilesHandler = async (inputFiles) => {
		console.log('Input files handler called with:', inputFiles);

		if (
			($config?.file?.max_count ?? null) !== null &&
			files.length + inputFiles.length > $config?.file?.max_count
		) {
			toast.error(
				$i18n.t(`You can only chat with a maximum of {{maxCount}} file(s) at a time.`, {
					maxCount: $config?.file?.max_count
				})
			);
			return;
		}

		inputFiles.forEach(async (file) => {
			console.log('Processing file:', {
				name: file.name,
				type: file.type,
				size: file.size,
				extension: file.name.split('.').at(-1)
			});

			if (
				($config?.file?.max_size ?? null) !== null &&
				file.size > ($config?.file?.max_size ?? 0) * 1024 * 1024
			) {
				console.log('File exceeds max size limit:', {
					fileSize: file.size,
					maxSize: ($config?.file?.max_size ?? 0) * 1024 * 1024
				});
				toast.error(
					$i18n.t(`File size should not exceed {{maxSize}} MB.`, {
						maxSize: $config?.file?.max_size
					})
				);
				return;
			}

			if (file['type'].startsWith('image/')) {
				if (visionCapableModels.length === 0) {
					toast.error($i18n.t('Selected model(s) do not support image inputs'));
					return;
				}

				const compressImageHandler = async (imageUrl, settings = {}, config = {}) => {
					// Quick shortcut so we don't do unnecessary work.
					const settingsCompression = settings?.imageCompression ?? false;
					const configWidth = config?.file?.image_compression?.width ?? null;
					const configHeight = config?.file?.image_compression?.height ?? null;

					// If neither settings nor config wants compression, return original URL.
					if (!settingsCompression && !configWidth && !configHeight) {
						return imageUrl;
					}

					// Default to null (no compression unless set)
					let width = null;
					let height = null;

					// If user/settings want compression, pick their preferred size.
					if (settingsCompression) {
						width = settings?.imageCompressionSize?.width ?? null;
						height = settings?.imageCompressionSize?.height ?? null;
					}

					// Apply config limits as an upper bound if any
					if (configWidth && (width === null || width > configWidth)) {
						width = configWidth;
					}
					if (configHeight && (height === null || height > configHeight)) {
						height = configHeight;
					}

					// Do the compression if required
					if (width || height) {
						return await compressImage(imageUrl, width, height);
					}
					return imageUrl;
				};

				let reader = new FileReader();

				reader.onload = async (event) => {
					let imageUrl = event.target.result;

					// Compress the image if settings or config require it
					imageUrl = await compressImageHandler(imageUrl, $settings, $config);

					if ($temporaryChatEnabled) {
						files = [
							...files,
							{
								type: 'image',
								url: imageUrl
							}
						];
					} else {
						const blob = await (await fetch(imageUrl)).blob();
						const compressedFile = new File([blob], file.name, { type: file.type });

						uploadFileHandler(compressedFile, false);
					}
				};

				reader.readAsDataURL(file['type'] === 'image/heic' ? await convertHeicToJpeg(file) : file);
			} else {
				uploadFileHandler(file);
			}
		});
	};

	const createNote = async () => {
		if (inputContent?.md.trim() === '' && inputContent?.html.trim() === '') {
			toast.error($i18n.t('Cannot create an empty note.'));
			return;
		}

		const res = await createNoteHandler(
			dayjs().format('YYYY-MM-DD'),
			inputContent?.md,
			inputContent?.html
		);

		if (res) {
			// Clear the input content saved in session storage.
			sessionStorage.removeItem('chat-input');
			goto(`/notes/${res.id}`);
		}
	};

	const onDragOver = (e: DragEvent) => {
		e.preventDefault();

		// Check if a file is being dragged.
		if (e.dataTransfer?.types?.includes('Files')) {
			dragged = true;
		} else {
			dragged = false;
		}
	};

	const onDragLeave = (e: DragEvent) => {
		if ((e.currentTarget as HTMLElement)?.contains(e.relatedTarget as Node)) {
			return;
		}
		dragged = false;
	};

	const onDrop = async (e: DragEvent) => {
		e.preventDefault();
		console.log(e);

		if (e.dataTransfer?.files) {
			const inputFiles = Array.from(e.dataTransfer?.files);
			if (inputFiles && inputFiles.length > 0) {
				console.log(inputFiles);
				inputFilesHandler(inputFiles);
			}
		}

		dragged = false;
	};

	// --- Chat drag-and-drop onto the input bar ---
	const onInputDragOver = (e: DragEvent) => {
		e.preventDefault();
		if (e.dataTransfer?.types?.includes('text/plain')) {
			chatDragged = true;
		}
	};

	const onInputDragLeave = (e: DragEvent) => {
		if ((e.currentTarget as HTMLElement)?.contains(e.relatedTarget as Node)) {
			return;
		}
		chatDragged = false;
	};

	const onInputDrop = async (e: DragEvent) => {
		const textData = e.dataTransfer?.getData('text/plain');
		if (!textData) return;

		let data;
		try {
			data = JSON.parse(textData);
		} catch {
			return; // Not JSON — let the default behavior handle it
		}

		if (data?.type !== 'chat' || !data?.id) return;

		// It's a chat drop — prevent the text from being inserted
		e.preventDefault();
		e.stopPropagation();
		chatDragged = false;

		// Ignore current conversation
		if (data.id === $chatId) return;

		// Ignore duplicates
		if (files.find((f) => f.id === data.id)) return;

		const chat = await getChatById(localStorage.token, data.id);
		if (!chat) return;

		files = [
			...files,
			{
				type: 'chat',
				id: chat.id,
				name: chat.title,
				title: chat.title,
				updated_at: chat.updated_at,
				description: dayjs(chat.updated_at * 1000).fromNow(),
				status: 'processed'
			}
		];
	};

	const onKeyDown = (e: KeyboardEvent) => {
		if (e.key === 'Shift') {
			shiftKey = true;
		}

		// Cmd/Ctrl+Shift+L (legacy hotkey kept for no-op)
		if (e.key.toLowerCase() === 'l' && (e.metaKey || e.ctrlKey) && e.shiftKey) {
			e.preventDefault();
			return;
		}

		if (e.key === 'Escape') {
			console.log('Escape');
			dragged = false;
		}
	};

	const onKeyUp = (e: KeyboardEvent) => {
		if (e.key === 'Shift') {
			shiftKey = false;
		}
	};

	const onFocus = () => {};

	const onBlur = () => {
		shiftKey = false;
	};

	onMount(() => {
		suggestions = [
			{
				char: '@',
				render: getSuggestionRenderer(CommandSuggestionList, {
					i18n,
					onSelect: (e) => {
						const { type, data } = e;

						if (type === 'model') {
							atSelectedModel = data;
						}

						document.getElementById('chat-input')?.focus();
					},

					insertTextHandler: insertTextAtCursor,
					onUpload: (e) => {
						const { type, data } = e;

						if (type === 'file') {
							if (files.find((f) => f.id === data.id)) {
								return;
							}
							files = [
								...files,
								{
									...data,
									status: 'processed'
								}
							];
						} else {
							onUpload(e);
						}
					}
				})
			},
			{
				char: '/',
				render: getSuggestionRenderer(CommandSuggestionList, {
					i18n,
					onSelect: (e) => {
						const { type, data } = e;

						if (type === 'model') {
							atSelectedModel = data;
						}

						document.getElementById('chat-input')?.focus();
					},

					insertTextHandler: insertTextAtCursor,
					onUpload: (e) => {
						const { type, data } = e;

						if (type === 'file') {
							if (files.find((f) => f.id === data.id)) {
								return;
							}
							files = [
								...files,
								{
									...data,
									status: 'processed'
								}
							];
						} else {
							onUpload(e);
						}
					}
				})
			},
			{
				char: '#',
				render: getSuggestionRenderer(CommandSuggestionList, {
					i18n,
					onSelect: (e) => {
						const { type, data } = e;

						if (type === 'model') {
							atSelectedModel = data;
						}

						document.getElementById('chat-input')?.focus();
					},

					insertTextHandler: insertTextAtCursor,
					onUpload: (e) => {
						const { type, data } = e;

						if (type === 'file') {
							if (files.find((f) => f.id === data.id)) {
								return;
							}
							files = [
								...files,
								{
									...data,
									status: 'processed'
								}
							];
						} else {
							onUpload(e);
						}
					}
				})
			},
			{
				char: '$',
				render: getSuggestionRenderer(CommandSuggestionList, {
					i18n,
					onSelect: (e) => {
						document.getElementById('chat-input')?.focus();
					},

					insertTextHandler: insertTextAtCursor,
					onUpload: () => {}
				})
			}
		];
		loaded = true;

		window.setTimeout(() => {
			const chatInput = document.getElementById('chat-input');
			chatInput?.focus();
		}, 0);

		window.addEventListener('keydown', onKeyDown);
		window.addEventListener('keyup', onKeyUp);

		window.addEventListener('focus', onFocus);
		window.addEventListener('blur', onBlur);

		let isDestroyed = false;
		let dropzoneElement: HTMLElement | null = null;
		let inputDropzoneElement: HTMLElement | null = null;
		const initialize = async () => {
			await tick();
			if (isDestroyed) return;

			dropzoneElement = document.getElementById('chat-pane');
			if (dropzoneElement) {
				dropzoneElement.addEventListener('dragover', onDragOver);
				dropzoneElement.addEventListener('drop', onDrop);
				dropzoneElement.addEventListener('dragleave', onDragLeave);
			}

			inputDropzoneElement = document.getElementById('message-input-container');
			if (inputDropzoneElement) {
				inputDropzoneElement.addEventListener('dragover', onInputDragOver);
				inputDropzoneElement.addEventListener('drop', onInputDrop, true);
				inputDropzoneElement.addEventListener('dragleave', onInputDragLeave);
			}

			tools.set(await getTools(localStorage.token));
		};
		initialize();

		return () => {
			isDestroyed = true;

			window.removeEventListener('keydown', onKeyDown);
			window.removeEventListener('keyup', onKeyUp);

			window.removeEventListener('focus', onFocus);
			window.removeEventListener('blur', onBlur);

			if (dropzoneElement) {
				dropzoneElement.removeEventListener('dragover', onDragOver);
				dropzoneElement.removeEventListener('drop', onDrop);
				dropzoneElement.removeEventListener('dragleave', onDragLeave);
			}

			if (inputDropzoneElement) {
				inputDropzoneElement.removeEventListener('dragover', onInputDragOver);
				inputDropzoneElement.removeEventListener('drop', onInputDrop, true);
				inputDropzoneElement.removeEventListener('dragleave', onInputDragLeave);
			}
		};
	});
</script>

<svelte:window on:click={(e) => {
	if (showThinkingDropdown) {
		const container = document.getElementById('thinking-dropdown-container');
		if (container && !container.contains(e.target)) {
			showThinkingDropdown = false;
		}
	}
}} />

<ToolServersModal bind:show={showTools} {selectedToolIds} />

<InputVariablesModal
	bind:show={showInputVariablesModal}
	variables={inputVariables}
	onSave={inputVariablesModalCallback}
/>

<ValvesModal
	bind:show={showValvesModal}
	userValves={true}
	type={selectedValvesType}
	id={selectedValvesItemId ?? null}
	on:save={async () => {
		await tick();
	}}
	on:close={() => {
	}}
/>

<InputModal
	bind:show={showInputModal}
	bind:value={prompt}
	bind:inputContent
	onChange={(content) => {
		console.log(content);
		chatInputElement?.setContent(content?.json ?? null);
	}}
	onClose={async () => {
		await tick();
		chatInputElement?.focus();
	}}
/>

{#if loaded}
	<div class="w-full font-primary">
		<div class=" mx-auto inset-x-0 bg-transparent flex justify-center">
			<div
				class="flex flex-col px-3 {($settings?.widescreenMode ?? null)
					? 'max-w-full'
					: 'max-w-2xl'} w-full"
			>
				<div class="relative">
					{#if autoScroll === false && history?.currentId}
						<div
							class=" absolute -top-12 left-0 right-0 flex justify-center z-30 pointer-events-none"
						>
							<button
								class=" bg-white border border-gray-100 dark:border-none dark:bg-white/20 p-1.5 rounded-full pointer-events-auto"
								on:click={() => {
									autoScroll = true;
									scrollToBottom();
								}}
							>
								<svg
									xmlns="http://www.w3.org/2000/svg"
									viewBox="0 0 20 20"
									fill="currentColor"
									class="w-5 h-5"
								>
									<path
										fill-rule="evenodd"
										d="M10 3a.75.75 0 01.75.75v10.638l3.96-4.158a.75.75 0 111.08 1.04l-5.25 5.5a.75.75 0 01-1.08 0l-5.25-5.5a.75.75 0 111.08-1.04l3.96 4.158V3.75A.75.75 0 0110 3z"
										clip-rule="evenodd"
									/>
								</svg>
							</button>
						</div>
					{/if}
				</div>
			</div>
		</div>

		<div class="bg-transparent">
			<div
				class="{($settings?.widescreenMode ?? null)
					? 'max-w-full'
					: 'max-w-2xl'} px-2.5 mx-auto inset-x-0"
			>
				<div class="">
					<input
						bind:this={filesInputElement}
						bind:files={inputFiles}
						type="file"
						hidden
						multiple
						on:change={async () => {
							if (inputFiles && inputFiles.length > 0) {
								const _inputFiles = Array.from(inputFiles);
								inputFilesHandler(_inputFiles);
							} else {
								toast.error($i18n.t(`File not found.`));
							}

							filesInputElement.value = '';
						}}
					/>

					<form
						class="w-full flex flex-col gap-1.5"
						on:submit|preventDefault={() => {
							// check if selectedModels support image input
							if (!sendDisabled && (prompt !== '' || files.length > 0)) {
								dispatch('submit', prompt);
							}
						}}
					>
						<button
							id="generate-message-pair-button"
							class="hidden"
							on:click={() => createMessagePair(prompt)}
						/>

						<!-- Queued messages display -->
						{#if messageQueue.length > 0}
							<div
								class="mb-1 mx-2 py-0.5 px-1.5 rounded-2xl bg-white dark:bg-gray-900/60 border border-gray-100 dark:border-gray-800/50 overflow-x-hidden overflow-y-auto max-h-[25vh]"
							>
								{#each messageQueue as queuedMessage (queuedMessage.id)}
									<QueuedMessageItem
										id={queuedMessage.id}
										content={queuedMessage.prompt}
										files={queuedMessage.files}
										onSendNow={onQueueSendNow}
										onEdit={onQueueEdit}
										onDelete={onQueueDelete}
									/>
								{/each}
							</div>
						{/if}

						<div
							id="message-input-container"
							class="flex-1 flex {isCompact ? 'flex-row items-center rounded-full' : 'flex-col rounded-3xl'} relative z-40 w-full shadow-lg border {chatDragged
								? 'border-blue-400 dark:border-blue-500 ring-2 ring-blue-300/50 dark:ring-blue-500/30'
								: $temporaryChatEnabled
								? 'border-dashed border-gray-100 dark:border-gray-800 hover:border-gray-200 focus-within:border-gray-200 hover:dark:border-gray-700 focus-within:dark:border-gray-700'
								: ' border-gray-100/30 dark:border-gray-850/30 hover:border-gray-200 focus-within:border-gray-100 hover:dark:border-gray-800 focus-within:dark:border-gray-800'}  transition {isCompact ? 'px-1 py-2' : 'px-1'} bg-white/5 dark:bg-gray-850 dark:text-gray-100"
							dir={$settings?.chatDirection ?? 'auto'}
						>
							{#if !isCompact}
								{#if atSelectedModel !== undefined}
								<div class="px-3 pt-3 text-left w-full flex flex-col z-10">
									<div class="flex items-center justify-between w-full">
										<div class="pl-[1px] flex items-center gap-2 text-sm dark:text-gray-500">
											<img
												alt="model profile"
												class="size-3.5 max-w-[28px] object-cover rounded-full"
												src={`${WEBUI_API_BASE_URL}/models/model/profile/image?id=${$models.find((model) => model.id === atSelectedModel.id).id}&lang=${$i18n.language}`}
											/>
											<div class="translate-y-[0.5px]">
												<span class="">{atSelectedModel.name}</span>
											</div>
										</div>
										<div>
											<button
												class="flex items-center dark:text-gray-500"
												on:click={() => {
													atSelectedModel = undefined;
												}}
											>
												<XMark />
											</button>
										</div>
									</div>
								</div>
							{/if}

							{#if files.length > 0}
								<div
									class="mx-2 mt-2.5 pb-1.5 flex items-center flex-wrap gap-2"
									dir={$settings?.chatDirection ?? 'auto'}
								>
									{#each files as file, fileIdx}
										{#if file.type === 'image' || (file?.content_type ?? '').startsWith('image/')}
											{@const fileUrl =
												file.url.startsWith('data') || file.url.startsWith('http')
													? file.url
													: `${WEBUI_API_BASE_URL}/files/${file.url}${file?.content_type ? '/content' : ''}`}
											<div class=" relative group">
												<div class="relative flex items-center">
													<Image
														src={fileUrl}
														alt=""
														imageClassName=" size-8 rounded-lg object-cover"
													/>
													{#if atSelectedModel ? visionCapableModels.length === 0 : selectedModels.length !== visionCapableModels.length}
														<Tooltip
															className=" absolute top-1 left-1"
															content={$i18n.t('{{ models }}', {
																models: [...(atSelectedModel ? [atSelectedModel] : selectedModels)]
																	.filter((id) => !visionCapableModels.includes(id))
																	.join(', ')
															})}
														>
															<svg
																xmlns="http://www.w3.org/2000/svg"
																viewBox="0 0 24 24"
																fill="currentColor"
																aria-hidden="true"
																class="size-4 fill-yellow-300"
															>
																<path
																	fill-rule="evenodd"
																	d="M9.401 3.003c1.155-2 4.043-2 5.197 0l7.355 12.748c1.154 2-.29 4.5-2.599 4.5H4.645c-2.309 0-3.752-2.5-2.598-4.5L9.4 3.003ZM12 8.25a.75.75 0 0 1 .75.75v3.75a.75.75 0 0 1-1.5 0V9a.75.75 0 0 1 .75-.75Zm0 8.25a.75.75 0 1 0 0-1.5.75.75 0 0 0 0 1.5Z"
																	clip-rule="evenodd"
																/>
															</svg>
														</Tooltip>
													{/if}
												</div>
												<div class=" absolute -top-1 -right-1">
													<button
														class=" bg-white text-black border border-white rounded-full {($settings?.highContrastMode ??
														false)
															? ''
															: 'outline-hidden focus:outline-hidden group-hover:visible invisible transition'}"
														type="button"
														aria-label={$i18n.t('Remove file')}
														on:click={() => {
															files.splice(fileIdx, 1);
															files = files;
														}}
													>
														<svg
															xmlns="http://www.w3.org/2000/svg"
															viewBox="0 0 20 20"
															fill="currentColor"
															aria-hidden="true"
															class="size-4"
														>
															<path
																d="M6.28 5.22a.75.75 0 00-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 101.06 1.06L10 11.06l3.72 3.72a.75.75 0 101.06-1.06L11.06 10l3.72-3.72a.75.75 0 00-1.06-1.06L10 8.94 6.28 5.22z"
															/>
														</svg>
													</button>
												</div>
											</div>
										{:else}
											<FileItem
												item={file}
												name={file.name}
												type={file.type}
												size={file?.size}
												loading={file.status === 'uploading'}
												dismissible={true}
												edit={true}
												small={true}
												modal={['file', 'collection'].includes(file?.type)}
												on:dismiss={async () => {
													// Remove from UI state
													files.splice(fileIdx, 1);
													files = files;
												}}
												on:click={() => {
													console.log(file);
												}}
											/>
										{/if}
									{/each}
								</div>
							{/if}
						{/if}

						{#if isCompact}
							<InputMenu
								bind:files
								selectedModels={atSelectedModel ? [atSelectedModel.id] : selectedModels}
								{fileUploadCapableModels}
								{inputFilesHandler}
								uploadFilesHandler={() => {
									filesInputElement.click();
								}}
								uploadGoogleDriveHandler={async () => {
									try {
										const fileData = await createPicker();
										if (fileData) {
											const file = new File([fileData.blob], fileData.name, {
												type: fileData.blob.type
											});
											await uploadFileHandler(file);
										} else {
											console.log('No file was selected from Google Drive');
										}
									} catch (error) {
										console.error('Google Drive Error:', error);
										toast.error(
											$i18n.t('Error accessing Google Drive: {{error}}', {
												error: error.message
											})
										);
									}
								}}
								uploadOneDriveHandler={async (authorityType) => {
									try {
										const fileData = await pickAndDownloadFile(authorityType);
										if (fileData) {
											const file = new File([fileData.blob], fileData.name, {
												type: fileData.blob.type || 'application/octet-stream'
											});
											await uploadFileHandler(file);
										} else {
											console.log('No file was selected from OneDrive');
										}
									} catch (error) {
										console.error('OneDrive Error:', error);
									}
								}}
								{onUpload}
								onClose={async () => {
									await tick();
									const chatInput = document.getElementById('chat-input');
									chatInput?.focus();
								}}
								{toggleFilters}
								{showWebSearchButton}
								{showImageGenerationButton}
								{showCodeInterpreterButton}
								{showCodeExecutionButton}
								{showStableDiffusionButton}
								bind:selectedToolIds
								bind:selectedFilterIds
								bind:webSearchEnabled
								bind:imageGenerationEnabled
								bind:codeInterpreterEnabled
								bind:codeExecutionEnabled
								bind:stableDiffusionEnabled
								onShowValves={(e) => {
									const { type, id } = e;
									selectedValvesType = type;
									selectedValvesItemId = id;
									showValvesModal = true;
								}}
							>
								<div
									class="bg-transparent hover:bg-gray-100 text-gray-700 dark:text-white dark:hover:bg-gray-800 rounded-full size-8 flex justify-center items-center outline-hidden focus:outline-hidden"
								>
									<PlusAlt className="size-5.5" />
								</div>
							</InputMenu>
						{/if}

							<div class="{isCompact ? 'flex-1 min-w-0 px-1 flex items-center' : 'px-2.5'}">
								<div
									bind:this={chatInputContainerEl}
									class="scrollbar-hidden rtl:text-right ltr:text-left bg-transparent dark:text-gray-100 outline-hidden w-full px-1 resize-none h-fit max-h-96 overflow-auto {files.length ===
									0
										? atSelectedModel !== undefined
											? 'pt-1.5'
											: isCompact ? '' : 'pt-2.5'
										: ''} {isCompact ? '' : 'pb-1'}"
									id="chat-input-container"
								>
									{#if suggestions}
										{#key $settings?.richTextInput ?? false}
											{#key $settings?.showFormattingToolbar ?? false}
												<RichTextInput
													bind:this={chatInputElement}
													id="chat-input"
													editable={!showInputModal}
													onChange={(content) => {
														prompt = content.md;
														inputContent = content;
														command = getCommand();

														const nodes = content.json?.content;
														const isEmpty = !nodes || nodes.length === 0 ||
															(nodes.length === 1 && (!nodes[0].content || nodes[0].content.length === 0));

														if (isEmpty) {
															isInputMultiline = false;
															return;
														}

														const hasStructural = nodes.length > 1 ||
															(Array.isArray(nodes[0].content) && nodes[0].content.some((n) => n.type === 'hardBreak'));

														if (hasStructural) {
															isInputMultiline = true;
															return;
														}

														// Visual wrapping: only escalate, never de-escalate
														// (expanded layout width differs from compact, causing oscillation)
														tick().then(() => {
															if (!chatInputContainerEl) return;
															const firstP = chatInputContainerEl.querySelector('.ProseMirror p');
															if (!firstP) return;
															const style = getComputedStyle(firstP);
															const lh = parseFloat(style.lineHeight);
															const effectiveLH = isNaN(lh) ? parseFloat(style.fontSize) * 1.5 : lh;
															if (firstP.getBoundingClientRect().height > effectiveLH + 4) {
																isInputMultiline = true;
															}
														});
													}}
													json={true}
													richText={$settings?.richTextInput ?? false}
													messageInput={true}
													showFormattingToolbar={$settings?.showFormattingToolbar ?? false}
													floatingMenuPlacement={'top-start'}
													insertPromptAsRichText={$settings?.insertPromptAsRichText ?? false}
													shiftEnter={!($settings?.ctrlEnterToSend ?? false) &&
														!$mobile &&
														!(
															'ontouchstart' in window ||
															navigator.maxTouchPoints > 0 ||
															navigator.msMaxTouchPoints > 0
														)}
													placeholder={placeholder ? placeholder : $i18n.t('Send a Message')}
													largeTextAsFile={($settings?.largeTextAsFile ?? false) && !shiftKey}
													autocomplete={$config?.features?.enable_autocomplete_generation &&
														($settings?.promptAutocomplete ?? false)}
													generateAutoCompletion={async (text) => {
														if (selectedModelIds.length === 0 || !selectedModelIds.at(0)) {
															toast.error($i18n.t('Please select a model first.'));
														}

														const res = await generateAutoCompletion(
															localStorage.token,
															selectedModelIds.at(0),
															text,
															history?.currentId
																? createMessagesList(history, history.currentId)
																: null
														).catch((error) => {
															console.log(error);

															return null;
														});

														console.log(res);
														return res;
													}}
													{suggestions}
													oncompositionstart={() => (isComposing = true)}
													oncompositionend={(e) => {
														compositionEndedAt = e.timeStamp;
														isComposing = false;
													}}
													on:keydown={async (e) => {
														e = e.detail.event;

														const isCtrlPressed = e.ctrlKey || e.metaKey; // metaKey is for Cmd key on Mac
														const suggestionsContainerElement =
															document.getElementById('suggestions-container');

														if (e.key === 'Escape') {
															stopResponse();
														}

														if (prompt === '' && e.key == 'ArrowUp') {
															e.preventDefault();

															const userMessageElement = [
																...document.getElementsByClassName('user-message')
															]?.at(-1);

															if (userMessageElement) {
																userMessageElement.scrollIntoView({ block: 'center' });
																const editButton = [
																	...document.getElementsByClassName('edit-user-message-button')
																]?.at(-1);

																editButton?.click();
															}
														}

														if (!suggestionsContainerElement) {
															if (
																!$mobile ||
																!(
																	'ontouchstart' in window ||
																	navigator.maxTouchPoints > 0 ||
																	navigator.msMaxTouchPoints > 0
																)
															) {
																if (inOrNearComposition(e)) {
																	return;
																}

																// Uses keyCode '13' for Enter key for chinese/japanese keyboards.
																//
																// Depending on the user's settings, it will send the message
																// either when Enter is pressed or when Ctrl+Enter is pressed.
																const enterPressed =
																	($settings?.ctrlEnterToSend ?? false)
																		? (e.key === 'Enter' || e.keyCode === 13) && isCtrlPressed
																		: (e.key === 'Enter' || e.keyCode === 13) && !e.shiftKey;

																if (enterPressed) {
																	e.preventDefault();
																	if (!sendDisabled && (prompt !== '' || files.length > 0)) {
																		dispatch('submit', prompt);
																	}
																}
															}
														}

														if (e.key === 'Escape') {
															console.log('Escape');
															atSelectedModel = undefined;
															selectedToolIds = [];
															selectedFilterIds = [];

															webSearchEnabled = false;
															imageGenerationEnabled = false;
															codeInterpreterEnabled = false;
															stableDiffusionEnabled = false;
														}
													}}
													on:paste={async (e) => {
														e = e.detail.event;
														console.log(e);

														const clipboardData = e.clipboardData || window.clipboardData;

														if (clipboardData && clipboardData.items) {
															for (const item of clipboardData.items) {
																if (item.type === 'text/plain') {
																	if (($settings?.largeTextAsFile ?? false) && !shiftKey) {
																		const text = clipboardData.getData('text/plain');

																		if (text.length > PASTED_TEXT_CHARACTER_LIMIT) {
																			e.preventDefault();
																			const blob = new Blob([text], { type: 'text/plain' });
																			const file = new File(
																				[blob],
																				`Pasted_Text_${Date.now()}.txt`,
																				{
																					type: 'text/plain'
																				}
																			);

																			await uploadFileHandler(file, true, { context: 'full' });
																		}
																	}
																} else {
																	const file = item.getAsFile();
																	if (file) {
																		await inputFilesHandler([file]);
																		e.preventDefault();
																	}
																}
															}
														}
													}}
												/>
											{/key}
										{/key}
									{/if}
								</div>
							</div>

							{#if isCompact}
								<div class="self-center flex items-center gap-3 shrink-0 pr-1">
									{#if showThinkingButton}
										<div class="relative flex items-center self-center" id="thinking-dropdown-container">
											<button
												type="button"
												class="flex items-center gap-1.5 px-2.5 py-1.5 rounded-full transition cursor-pointer bg-transparent text-gray-600 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-800"
												style="font-size: 0.79rem; font-family: 'Segoe UI', sans-serif; font-weight: 400; letter-spacing: 0.01em;"
												aria-label={thinkingEnabled ? 'Raciocínio' : 'Rápido'}
												on:click|preventDefault={() => { showThinkingDropdown = !showThinkingDropdown; }}
											>
												<span>{thinkingEnabled ? 'Raciocínio' : 'Rápido'}</span>
												<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="size-3.5 transition-transform {showThinkingDropdown ? 'rotate-180' : ''}">
													<path fill-rule="evenodd" d="M14.78 12.78a.75.75 0 0 1-1.06 0L10 9.06l-3.72 3.72a.75.75 0 0 1-1.06-1.06l4.25-4.25a.75.75 0 0 1 1.06 0l4.25 4.25a.75.75 0 0 1 0 1.06Z" clip-rule="evenodd" />
												</svg>
											</button>

											{#if showThinkingDropdown}
												<div
													class="absolute bottom-full mb-1.5 right-0 z-50 w-[15.5rem] rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-850 shadow-md p-1 text-sm"
													style="font-family: 'Segoe UI', sans-serif;"
													transition:fly={{ y: 5, duration: 150 }}
													on:click|stopPropagation
												>
													<button
														type="button"
														class="flex w-full items-center gap-2.5 px-2 py-2 hover:bg-gray-100 dark:hover:bg-gray-800 transition cursor-pointer text-gray-700 dark:text-gray-200 rounded-md"
														on:click={() => { thinkingEnabled = false; showThinkingDropdown = false; }}
													>
														<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="size-4">
															<path fill-rule="evenodd" d="M11.3 1.046A1 1 0 0112 2v5h4a1 1 0 01.82 1.573l-7 10A1 1 0 018 18v-5H4a1 1 0 01-.82-1.573l7-10a1 1 0 011.12-.38z" clip-rule="evenodd" />
														</svg>
														<div class="flex-1 text-left"><div>Rápido</div><div class="text-[13px] text-gray-400 dark:text-gray-500 font-normal">Para respostas rápidas</div></div>
														{#if !thinkingEnabled}
															<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="size-4">
																<path fill-rule="evenodd" d="M16.704 4.153a.75.75 0 01.143 1.052l-8 10.5a.75.75 0 01-1.127.075l-4.5-4.5a.75.75 0 011.06-1.06l3.894 3.893 7.48-9.817a.75.75 0 011.05-.143z" clip-rule="evenodd" />
															</svg>
														{/if}
													</button>
													<button
														type="button"
														class="flex w-full items-center gap-2.5 px-2 py-2 hover:bg-gray-100 dark:hover:bg-gray-800 transition cursor-pointer text-gray-700 dark:text-gray-200 rounded-md"
														on:click={() => { thinkingEnabled = true; showThinkingDropdown = false; }}
													>
														<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" class="size-4">
															<path d="M12 2a7 7 0 0 0-7 7c0 2.862 1.782 5.3 4.25 6.318V17.5a.75.75 0 0 0 .75.75h4a.75.75 0 0 0 .75-.75v-2.182C17.218 14.3 19 11.862 19 9a7 7 0 0 0-7-7ZM9.25 19.75a.75.75 0 0 0 0 1.5h5.5a.75.75 0 0 0 0-1.5h-5.5ZM9.75 22.75a.75.75 0 0 0 0 1.5h4.5a.75.75 0 0 0 0-1.5h-4.5Z" />
														</svg>
														<div class="flex-1 text-left"><div>Raciocínio</div><div class="text-[13px] text-gray-400 dark:text-gray-500 font-normal">Para tarefas complexas</div></div>
														{#if thinkingEnabled}
															<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="size-4">
																<path fill-rule="evenodd" d="M16.704 4.153a.75.75 0 01.143 1.052l-8 10.5a.75.75 0 01-1.127.075l-4.5-4.5a.75.75 0 011.06-1.06l3.894 3.893 7.48-9.817a.75.75 0 011.05-.143z" clip-rule="evenodd" />
															</svg>
														{/if}
													</button>
												</div>
											{/if}
										</div>
									{/if}

									<Tooltip content={$i18n.t('Send message')}>
										<button
											id="send-message-button"
											class="{!sendDisabled && (prompt !== '' || files.length > 0)
												? 'bg-black text-white hover:bg-gray-900 dark:bg-white dark:text-black dark:hover:bg-gray-100 '
												: 'text-white bg-gray-200 dark:text-gray-900 dark:bg-gray-700 disabled'} transition rounded-full p-1.5 self-center"
											type="submit"
											disabled={sendDisabled || (prompt === '' && files.length === 0)}
										>
											<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" fill="currentColor" class="size-5">
												<path fill-rule="evenodd" d="M8 14a.75.75 0 0 1-.75-.75V4.56L4.03 7.78a.75.75 0 0 1-1.06-1.06l4.5-4.5a.75.75 0 0 1 1.06 0l4.5 4.5a.75.75 0 0 1-1.06 1.06L8.75 4.56v8.69A.75.75 0 0 1 8 14Z" clip-rule="evenodd" />
											</svg>
										</button>
									</Tooltip>
								</div>
							{/if}

							{#if !isCompact}
							<div class=" flex justify-between mt-2 mb-2.5 mx-0.5 max-w-full" dir="ltr">
								<div class="ml-1 self-end flex items-center flex-1 max-w-[80%] @container">
									<InputMenu
										bind:files
										selectedModels={atSelectedModel ? [atSelectedModel.id] : selectedModels}
										{fileUploadCapableModels}
										{inputFilesHandler}
										uploadFilesHandler={() => {
											filesInputElement.click();
										}}
										uploadGoogleDriveHandler={async () => {
											try {
												const fileData = await createPicker();
												if (fileData) {
													const file = new File([fileData.blob], fileData.name, {
														type: fileData.blob.type
													});
													await uploadFileHandler(file);
												} else {
													console.log('No file was selected from Google Drive');
												}
											} catch (error) {
												console.error('Google Drive Error:', error);
												toast.error(
													$i18n.t('Error accessing Google Drive: {{error}}', {
														error: error.message
													})
												);
											}
										}}
										uploadOneDriveHandler={async (authorityType) => {
											try {
												const fileData = await pickAndDownloadFile(authorityType);
												if (fileData) {
													const file = new File([fileData.blob], fileData.name, {
														type: fileData.blob.type || 'application/octet-stream'
													});
													await uploadFileHandler(file);
												} else {
													console.log('No file was selected from OneDrive');
												}
											} catch (error) {
												console.error('OneDrive Error:', error);
											}
										}}
										{onUpload}
										onClose={async () => {
											await tick();
										const chatInput = document.getElementById('chat-input');
										chatInput?.focus();
									}}
									{toggleFilters}
									{showWebSearchButton}
									{showImageGenerationButton}
									{showCodeInterpreterButton}
									{showCodeExecutionButton}
									{showStableDiffusionButton}
									bind:selectedToolIds
									bind:selectedFilterIds
									bind:webSearchEnabled
									bind:imageGenerationEnabled
									bind:codeInterpreterEnabled
									bind:codeExecutionEnabled
									bind:stableDiffusionEnabled
									onShowValves={(e) => {
										const { type, id } = e;
										selectedValvesType = type;
										selectedValvesItemId = id;
										showValvesModal = true;
									}}
								>
									<div
										id="input-menu-button"
										class="bg-transparent hover:bg-gray-100 text-gray-700 dark:text-white dark:hover:bg-gray-800 rounded-full size-8 flex justify-center items-center outline-hidden focus:outline-hidden"
									>
										<PlusAlt className="size-5.5" />
									</div>
								</InputMenu>
									{#if selectedModelIds.length === 1 && $models.find((m) => m.id === selectedModelIds[0])?.has_user_valves}
										<div class="ml-1 flex gap-1.5">
											<Tooltip content={$i18n.t('Valves')} placement="top">
												<button
													type="button"
													id="model-valves-button"
													class="bg-transparent hover:bg-gray-100 text-gray-700 dark:text-white dark:hover:bg-gray-800 rounded-full size-8 flex justify-center items-center outline-hidden focus:outline-hidden"
													on:click={() => {
														selectedValvesType = 'function';
														selectedValvesItemId = selectedModelIds[0]?.split('.')[0];
														showValvesModal = true;
													}}
												>
													<Knobs className="size-4" strokeWidth="1.5" />
												</button>
											</Tooltip>
										</div>
									{/if}

									<div class="ml-2.5 flex gap-1.5">
										{#if (selectedToolIds ?? []).length > 0}
											<Tooltip
												content={$i18n.t('{{COUNT}} Available Tools', {
													COUNT: (selectedToolIds ?? []).length
												})}
											>
												<button
													class="translate-y-[0.5px] px-1 flex gap-1 items-center text-gray-600 dark:text-gray-300 hover:text-gray-700 dark:hover:text-gray-200 rounded-lg self-center transition"
													aria-label="Available Tools"
													type="button"
													on:click={() => {
														showTools = !showTools;
													}}
												>
													<Wrench className="size-4" strokeWidth="1.75" />

													<span class="text-sm">
														{(selectedToolIds ?? []).length}
													</span>
												</button>
											</Tooltip>
										{/if}

										{#each selectedFilterIds as filterId}
											{@const filter = toggleFilters.find((f) => f.id === filterId)}
											{#if filter}
												<Tooltip content={filter?.name} placement="top">
													<button
														on:click|preventDefault={() => {
															selectedFilterIds = selectedFilterIds.filter((id) => id !== filterId);
														}}
														type="button"
														class="group py-[7px] px-2.5 flex gap-1.5 items-center text-[0.8125rem] rounded-full transition-colors duration-300 focus:outline-hidden max-w-full overflow-hidden {selectedFilterIds.includes(filterId) ? 'text-sky-500 dark:text-sky-300 hover:bg-sky-100 dark:hover:bg-sky-600/10' : 'bg-transparent text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800'} capitalize"
													>
														<div class="relative size-4 shrink-0 flex items-center justify-center">
															<span class="group-hover:hidden flex items-center justify-center">
																{#if filter?.icon}
																	<div class="size-4 items-center flex justify-center">
																		<img src={filter.icon} class="size-3.5 {filter.icon.includes('data:image/svg') ? 'dark:invert-[80%]' : ''}" style="fill: currentColor;" alt={filter.name} />
																	</div>
																{:else}
																	<Sparkles className="size-4" strokeWidth="1.75" />
																{/if}
															</span>
															<span class="hidden group-hover:flex items-center justify-center">
																<XMark className="size-4" strokeWidth="1.75" />
															</span>
														</div>
													</button>
												</Tooltip>
											{/if}
										{/each}

										{#if webSearchEnabled}
											<button
												on:click|preventDefault={() => (webSearchEnabled = !webSearchEnabled)}
												type="button"
												class="group py-[7px] px-2.5 flex gap-1.5 items-center text-[0.8125rem] rounded-full transition-colors duration-300 focus:outline-hidden max-w-full overflow-hidden text-sky-500 dark:text-sky-300 hover:bg-sky-100 dark:hover:bg-sky-600/10"
											>
												<div class="relative size-4 shrink-0 flex items-center justify-center">
													<span class="group-hover:hidden flex items-center justify-center">
														<GlobeAlt className="size-4" strokeWidth="1.75" />
													</span>
													<span class="hidden group-hover:flex items-center justify-center">
														<XMark className="size-4" strokeWidth="1.75" />
													</span>
												</div>
												<span class="text-[0.8125rem] font-medium hidden @sm:inline">Busca</span>
											</button>
										{/if}

										{#if imageGenerationEnabled}
											<button
												on:click|preventDefault={() => (imageGenerationEnabled = !imageGenerationEnabled)}
												type="button"
												class="group py-[7px] px-2.5 flex gap-1.5 items-center text-[0.8125rem] rounded-full transition-colors duration-300 focus:outline-hidden max-w-full overflow-hidden text-sky-500 dark:text-sky-300 hover:bg-sky-100 dark:hover:bg-sky-700/10"
											>
												<div class="relative size-4 shrink-0 flex items-center justify-center">
													<span class="group-hover:hidden flex items-center justify-center">
														<Photo className="size-4" strokeWidth="1.75" />
													</span>
													<span class="hidden group-hover:flex items-center justify-center">
														<XMark className="size-4" strokeWidth="1.75" />
													</span>
												</div>
												<span class="text-[0.8125rem] font-medium hidden @sm:inline">Imagem</span>
											</button>
										{/if}

										{#if codeInterpreterEnabled}
											<button
												aria-label={codeInterpreterEnabled ? $i18n.t('Disable Code Interpreter') : $i18n.t('Enable Code Interpreter')}
												aria-pressed={codeInterpreterEnabled}
												on:click|preventDefault={() => (codeInterpreterEnabled = !codeInterpreterEnabled)}
												type="button"
												class="group py-[7px] px-2.5 flex gap-1.5 items-center text-[0.8125rem] transition-colors duration-300 max-w-full overflow-hidden text-amber-500 dark:text-amber-300 hover:bg-amber-100 dark:hover:bg-amber-700/10 {($settings?.highContrastMode ?? false) ? 'm-1' : 'focus:outline-hidden rounded-full'}"
											>
												<div class="relative size-4 shrink-0 flex items-center justify-center">
													<span class="group-hover:hidden flex items-center justify-center">
														<Terminal className="size-4" strokeWidth="1.75" />
													</span>
													<span class="hidden group-hover:flex items-center justify-center">
														<XMark className="size-4" strokeWidth="1.75" />
													</span>
												</div>
												<span class="text-[0.8125rem] font-medium hidden @sm:inline">Intérprete</span>
											</button>
										{/if}

										{#if codeExecutionEnabled}
											<button
												aria-label={codeExecutionEnabled ? $i18n.t('Disable Code Execution') : $i18n.t('Enable Code Execution')}
												aria-pressed={codeExecutionEnabled}
												on:click|preventDefault={() => (codeExecutionEnabled = !codeExecutionEnabled)}
												type="button"
												class="group py-[7px] px-2.5 flex gap-1.5 items-center text-[0.8125rem] transition-colors duration-300 max-w-full overflow-hidden text-emerald-500 dark:text-emerald-300 hover:bg-emerald-100 dark:hover:bg-emerald-700/10 {($settings?.highContrastMode ?? false) ? 'm-1' : 'focus:outline-hidden rounded-full'}"
											>
												<div class="relative size-4 shrink-0 flex items-center justify-center">
													<span class="group-hover:hidden flex items-center justify-center">
														<svg aria-hidden="true" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5" class="size-4"><path stroke-linecap="round" stroke-linejoin="round" d="m21 7.5-9-5.25L3 7.5m18 0-9 5.25m9-5.25v9l-9 5.25M3 7.5l9 5.25M3 7.5v9l9 5.25m0-9v9"/></svg>
													</span>
													<span class="hidden group-hover:flex items-center justify-center">
														<XMark className="size-4" strokeWidth="1.75" />
													</span>
												</div>
												<span class="text-[0.8125rem] font-medium hidden @sm:inline">Artefatos</span>
											</button>
										{/if}

										{#if stableDiffusionEnabled}
											<button
												on:click|preventDefault={() => (stableDiffusionEnabled = !stableDiffusionEnabled)}
												type="button"
												class="group py-[7px] px-2.5 flex gap-1.5 items-center text-[0.8125rem] rounded-full transition-colors duration-300 focus:outline-hidden max-w-full overflow-hidden text-pink-500 dark:text-pink-300 hover:bg-pink-100 dark:hover:bg-pink-700/10"
											>
												<div class="relative size-4 shrink-0 flex items-center justify-center">
													<span class="group-hover:hidden flex items-center justify-center">
														<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="size-4"><path fill-rule="evenodd" d="M1 5.25A2.25 2.25 0 013.25 3h13.5A2.25 2.25 0 0119 5.25v9.5A2.25 2.25 0 0116.75 17H3.25A2.25 2.25 0 011 14.75v-9.5zm1.5 5.81v3.69c0 .414.336.75.75.75h13.5a.75.75 0 00.75-.75v-2.69l-2.22-2.219a.75.75 0 00-1.06 0l-1.91 1.909.47.47a.75.75 0 11-1.06 1.06L6.53 8.091a.75.75 0 00-1.06 0l-3.97 3.97zM12 7a1 1 0 11-2 0 1 1 0 012 0z" clip-rule="evenodd" /></svg>
													</span>
													<span class="hidden group-hover:flex items-center justify-center">
														<XMark className="size-4" strokeWidth="1.75" />
													</span>
												</div>
												<span class="text-[0.8125rem] font-medium hidden @sm:inline">Imagem</span>
											</button>
										{/if}

									</div>
								</div>
								<div class="self-end flex space-x-1 mr-1 shrink-0 gap-[0.5px]">
									{#if generating || (history?.currentId && history?.messages[history.currentId]?.done !== true) || uploadPending}
										<Tooltip content={$i18n.t('Stop')}>
											<button
												class="bg-white hover:bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-white dark:hover:bg-gray-800 transition rounded-full p-1.5"
												type="button"
												on:click={() => {
													stopResponse();
												}}
											>
												<svg
													xmlns="http://www.w3.org/2000/svg"
													viewBox="0 0 24 24"
													fill="currentColor"
													class="size-5"
												>
													<path
														fill-rule="evenodd"
														d="M2.25 12c0-5.385 4.365-9.75 9.75-9.75s9.75 4.365 9.75 9.75-4.365 9.75-9.75 9.75S2.25 17.385 2.25 12zm6-2.438c0-.724.588-1.312 1.313-1.312h4.874c.725 0 1.313.588 1.313 1.313v4.874c0 .725-.588 1.313-1.313 1.313H9.564a1.312 1.312 0 01-1.313-1.313V9.564z"
														clip-rule="evenodd"
													/>
												</svg>
											</button>
										</Tooltip>
									{:else}
										{#if (selectedToolIds ?? []).length > 0 || ($terminalServers ?? []).some((s) => s.url)}
											<TerminalMenu bind:show={showTools} />
										{/if}

										{#if showThinkingButton}
											<div class="relative flex items-center self-center mr-2" id="thinking-dropdown-container">
												<button
													type="button"
													class="flex items-center gap-1.5 px-2.5 py-1.5 rounded-full transition cursor-pointer bg-transparent text-gray-600 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-800"
													style="font-size: 0.79rem; font-family: 'Segoe UI', sans-serif; font-weight: 400; letter-spacing: 0.01em;"
													aria-label={thinkingEnabled ? 'Raciocínio' : 'Rápido'}
													on:click|preventDefault={() => { showThinkingDropdown = !showThinkingDropdown; }}
												>
													<span>{thinkingEnabled ? 'Raciocínio' : 'Rápido'}</span>
													<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="size-3.5 transition-transform {showThinkingDropdown ? 'rotate-180' : ''}">
														<path fill-rule="evenodd" d="M14.78 12.78a.75.75 0 0 1-1.06 0L10 9.06l-3.72 3.72a.75.75 0 0 1-1.06-1.06l4.25-4.25a.75.75 0 0 1 1.06 0l4.25 4.25a.75.75 0 0 1 0 1.06Z" clip-rule="evenodd" />
													</svg>
												</button>

												{#if showThinkingDropdown}
													<div
														class="absolute bottom-full mb-1.5 right-0 z-50 w-[15.5rem] rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-850 shadow-md p-1 text-sm"
														style="font-family: 'Segoe UI', sans-serif;"
														transition:fly={{ y: 5, duration: 150 }}
														on:click|stopPropagation
													>
														<button
															type="button"
															class="flex w-full items-center gap-2.5 px-2 py-2 hover:bg-gray-100 dark:hover:bg-gray-800 transition cursor-pointer text-gray-700 dark:text-gray-200 rounded-md"
															on:click={() => { thinkingEnabled = false; showThinkingDropdown = false; }}
														>
															<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="size-4">
																<path fill-rule="evenodd" d="M11.3 1.046A1 1 0 0112 2v5h4a1 1 0 01.82 1.573l-7 10A1 1 0 018 18v-5H4a1 1 0 01-.82-1.573l7-10a1 1 0 011.12-.38z" clip-rule="evenodd" />
															</svg>
															<div class="flex-1 text-left"><div>Rápido</div><div class="text-[13px] text-gray-400 dark:text-gray-500 font-normal">Para respostas rápidas</div></div>
															{#if !thinkingEnabled}
																<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="size-4">
																	<path fill-rule="evenodd" d="M16.704 4.153a.75.75 0 01.143 1.052l-8 10.5a.75.75 0 01-1.127.075l-4.5-4.5a.75.75 0 011.06-1.06l3.894 3.893 7.48-9.817a.75.75 0 011.05-.143z" clip-rule="evenodd" />
																</svg>
															{/if}
														</button>
														<button
															type="button"
															class="flex w-full items-center gap-2.5 px-2 py-2 hover:bg-gray-100 dark:hover:bg-gray-800 transition cursor-pointer text-gray-700 dark:text-gray-200 rounded-md"
															on:click={() => { thinkingEnabled = true; showThinkingDropdown = false; }}
														>
															<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" class="size-4">
																<path d="M12 2a7 7 0 0 0-7 7c0 2.862 1.782 5.3 4.25 6.318V17.5a.75.75 0 0 0 .75.75h4a.75.75 0 0 0 .75-.75v-2.182C17.218 14.3 19 11.862 19 9a7 7 0 0 0-7-7ZM9.25 19.75a.75.75 0 0 0 0 1.5h5.5a.75.75 0 0 0 0-1.5h-5.5ZM9.75 22.75a.75.75 0 0 0 0 1.5h4.5a.75.75 0 0 0 0-1.5h-4.5Z" />
															</svg>
															<div class="flex-1 text-left"><div>Raciocínio</div><div class="text-[13px] text-gray-400 dark:text-gray-500 font-normal">Para tarefas complexas</div></div>
															{#if thinkingEnabled}
																<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="size-4">
																	<path fill-rule="evenodd" d="M16.704 4.153a.75.75 0 01.143 1.052l-8 10.5a.75.75 0 01-1.127.075l-4.5-4.5a.75.75 0 011.06-1.06l3.894 3.893 7.48-9.817a.75.75 0 011.05-.143z" clip-rule="evenodd" />
																</svg>
															{/if}
														</button>
													</div>
												{/if}
											</div>
										{/if}

										{#if lastUsage}
											{@const totalTokens = lastUsage.total_tokens ?? ((lastUsage.prompt_tokens ?? lastUsage.input_tokens ?? 0) + (lastUsage.completion_tokens ?? lastUsage.output_tokens ?? 0))}
											{@const contextModel = (() => { const mid = atSelectedModel?.id ?? selectedModels?.[0]; return $models.find((m) => m.id === mid); })()}
											{@const contextWindow = contextModel?.llamacpp?.n_ctx || contextModel?.info?.params?.num_ctx || contextModel?.info?.meta?.context_length || 128000}
											{@const usageRatio = Math.min(totalTokens / contextWindow, 1)}
											{@const ringRadius = 9}
											{@const circumference = 2 * Math.PI * ringRadius}
											{@const strokeOffset = circumference * (1 - usageRatio)}
											{@const ringColor = usageRatio > 0.9 ? '#ef4444' : usageRatio > 0.7 ? '#f59e0b' : '#6b7280'}
											<!-- svelte-ignore a11y-no-static-element-interactions -->
											<div
												class="relative flex items-center mr-3"
												on:mouseenter={() => (showTokenPopup = true)}
												on:mouseleave={() => (showTokenPopup = false)}
											>
												<div class="flex items-center gap-1 px-1 cursor-default select-none">
													<svg width="24" height="24" viewBox="0 0 22 22" class="shrink-0">
														<circle cx="11" cy="11" r={ringRadius} fill="none" stroke="currentColor" stroke-width="2" class="text-gray-200 dark:text-gray-700" />
														<circle cx="11" cy="11" r={ringRadius} fill="none" stroke={ringColor} stroke-width="2" stroke-linecap="round" stroke-dasharray={circumference} stroke-dashoffset={strokeOffset} transform="rotate(-90 11 11)" class="transition-all duration-500" />
													</svg>
													<span class="text-[14px] font-medium tabular-nums" style="color: {ringColor}">{(usageRatio * 100).toFixed(1)}%</span>
												</div>

												{#if showTokenPopup}
													<div
														class="absolute bottom-full mb-2.5 z-[60] w-56 rounded-xl border border-gray-200/70 dark:border-gray-700/60 bg-white dark:bg-gray-850 shadow-xl p-3.5 {$mobile ? 'right-0' : $showArtifacts ? 'right-0' : 'right-1/2 translate-x-1/2'}"
														style="font-family: 'Segoe UI', sans-serif;"
														transition:fly={{ y: 4, duration: 150 }}
													>
														<div class="flex items-center gap-1.5 mb-2.5">
															<svg width="16" height="16" viewBox="0 0 22 22" class="shrink-0">
																<circle cx="11" cy="11" r="9" fill="none" stroke="currentColor" stroke-width="2" class="text-gray-300 dark:text-gray-600" />
																<circle cx="11" cy="11" r="9" fill="none" stroke={ringColor} stroke-width="2" stroke-linecap="round" stroke-dasharray={circumference} stroke-dashoffset={strokeOffset} transform="rotate(-90 11 11)" />
															</svg>
															<span class="text-[14px] font-semibold text-gray-700 dark:text-gray-200">Uso de Tokens</span>
														</div>
														<div class="w-full h-1.5 rounded-full bg-gray-100 dark:bg-gray-700 mb-3 overflow-hidden">
															<div class="h-full rounded-full transition-all duration-500" style="width: {Math.max(usageRatio * 100, 1)}%; background-color: {ringColor}" />
														</div>
														<div class="space-y-1.5">
															<div class="flex justify-between items-center">
																<span class="text-[14px] text-gray-500 dark:text-gray-400">Total</span>
																<span class="text-[14px] font-semibold tabular-nums text-gray-700 dark:text-gray-200">{formatTokens(totalTokens)}</span>
															</div>
															<div class="flex justify-between items-center">
																<span class="text-[14px] text-gray-500 dark:text-gray-400">Contexto</span>
																<span class="text-[14px] font-semibold tabular-nums text-gray-700 dark:text-gray-200">{formatTokens(contextWindow)}</span>
															</div>
															<div class="flex justify-between items-center pt-1.5 mt-1 border-t border-gray-100 dark:border-gray-700/50">
																<span class="text-[14px] text-gray-500 dark:text-gray-400">Utilização</span>
																<span class="text-[14px] font-semibold tabular-nums" style="color: {ringColor}">{(usageRatio * 100).toFixed(1)}%</span>
															</div>
														</div>
													</div>
												{/if}
											</div>
										{/if}

										<div class=" flex items-center">
											<Tooltip content={uploadPending ? $i18n.t('Waiting for upload...') : $i18n.t('Send message')}>
												<button
													id="send-message-button"
													class="{!sendDisabled && (prompt !== '' || files.length > 0 || uploadPending)
														? 'bg-black text-white hover:bg-gray-900 dark:bg-white dark:text-black dark:hover:bg-gray-100 '
														: 'text-white bg-gray-200 dark:text-gray-900 dark:bg-gray-700 disabled'} transition rounded-full p-1.5 self-center"
													type="submit"
													disabled={sendDisabled || (prompt === '' && files.length === 0) || uploadPending}
												>
													{#if uploadPending}
														<Spinner className="size-5" />
													{:else}
														<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" fill="currentColor" class="size-5">
															<path fill-rule="evenodd" d="M8 14a.75.75 0 0 1-.75-.75V4.56L4.03 7.78a.75.75 0 0 1-1.06-1.06l4.5-4.5a.75.75 0 0 1 1.06 0l4.5 4.5a.75.75 0 0 1-1.06 1.06L8.75 4.56v8.69A.75.75 0 0 1 8 14Z" clip-rule="evenodd" />
														</svg>
													{/if}
												</button>
											</Tooltip>
										</div>
									{/if}
								</div>
							</div>
							{/if}
						</div>
					</form>
				</div>
			</div>
		</div>
	</div>
{/if}
