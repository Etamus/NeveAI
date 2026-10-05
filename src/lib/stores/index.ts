import { APP_NAME } from '$lib/constants';
import { type Writable, writable } from 'svelte/store';
import type { ModelConfig } from '$lib/apis';
import type { Banner } from '$lib/types';
import type { Socket } from 'socket.io-client';
import type { AudioQueue } from '$lib/utils/audio';

// Lazy-loaded emoji shortcodes (avoid blocking startup with 116KB JSON processing)
export const shortCodesToEmojis = writable({});

export type NeveDownloadToastState = {
	name: string;
	progress: number;
	label: string;
	cancelling: boolean;
	onCancel: () => void;
};

export const neveDownloadToast: Writable<NeveDownloadToastState | null> = writable(null);

let _emojiLoaded = false;
export async function loadShortCodesToEmojis() {
	if (_emojiLoaded) return;
	_emojiLoaded = true;
	const emojiShortCodes = (await import('$lib/emoji-shortcodes.json')).default;
	shortCodesToEmojis.set(
		Object.entries(emojiShortCodes).reduce((acc, [key, value]) => {
			if (typeof value === 'string') {
				acc[value] = key;
			} else {
				for (const v of value) {
					acc[v] = key;
				}
			}
			return acc;
		}, {})
	);
}

// Backend
export const NEVEAI_NAME = writable(APP_NAME);

export const NEVEAI_VERSION = writable(null);
export const NEVEAI_DEPLOYMENT_ID = writable(null);

export const config: Writable<Config | undefined> = writable(undefined);
export const user: Writable<SessionUser | undefined> = writable(undefined);

// Per-chat feature toggles (updated reactively by Chat.svelte)
// Used by deep components (e.g. CodeBlock) that cannot receive props easily
export const chatCodeExecutionEnabled = writable(false);

// Electron App
export const isApp = writable(false);
export const appInfo = writable(null);

// Frontend

export const mobile = writable(false);

export const socket: Writable<null | Socket> = writable(null);
export const activeChatIds: Writable<Set<string>> = writable(new Set());

export const theme = writable('system');

export const TTSWorker = writable(null);

export const chatId = writable('');
export const chatTitle = writable('');

export const chats = writable(null);
export const pinnedChats = writable([]);
export const tags = writable([]);
export const folders = writable([]);

export const selectedFolder = writable(null);

export const models: Writable<Model[]> = writable([]);

export const knowledge: Writable<null | Document[]> = writable(null);
export const tools = writable(null);

export const toolServers = writable([]);
export const terminalServers = writable([]);

// Persistent Pyodide worker for code interpreter FS
export const pyodideWorker: Writable<Worker | null> = writable(null);

export const banners: Writable<Banner[]> = writable([]);

export const settings: Writable<Settings> = writable({});

export const audioQueue = writable<AudioQueue | null>(null);

export const sidebarWidth = writable(260);

export const showSidebar = writable(false);
export const showSearch = writable(false);
export const showSettings = writable(false);
export const showSettingsTab = writable('');
export const showSettingsModelId = writable('');
export const showLocalModelsModal = writable(false);
const showChangelog = writable(false);

export const showControls = writable(false);
export const showModelSettings = writable(false);
export const showEmbeds = writable(false);
export const showArtifacts = writable(false);
export const showCallOverlay = writable(false);
export const showFileNavPath: Writable<string | null> = writable(null);
export const showFileNavDir: Writable<string | null> = writable(null);
export const selectedTerminalId: Writable<string | null> = writable(null);

export const artifactCode = writable(null);
export const artifactContents = writable(null);

export const embed = writable(null);

export const temporaryChatEnabled = writable(false);
export const scrollPaginationEnabled = writable(false);
export const currentChatPage = writable(1);

export const isLastActiveTab = writable(true);
export const playingNotificationSound = writable(false);

export type Model = OpenAIModel;

type BaseModel = {
	[key: string]: any;
	id: string;
	name: string;
	info?: ModelConfig;
	owned_by: string;
};

interface OpenAIModel extends BaseModel {
	owned_by: string;
	external: boolean;
	source?: string;
}

type Settings = {
	[key: string]: any;
	favoriteModels?: string[];
	toolServers?: any[];
	terminalServers?: any[];
	directConnections?: any[];
	detectArtifacts?: boolean;
	showUpdateToast?: boolean;
	showChangelog?: boolean;
	showEmojiInCall?: boolean;
	voiceInterruption?: boolean;
	collapseCodeBlocks?: boolean;
	expandDetails?: boolean;
	streamResponse?: boolean;
	notificationSound?: boolean;
	notificationSoundAlways?: boolean;
	stylizedPdfExport?: boolean;
	notifications?: any;
	imageCompression?: boolean;
	imageCompressionSize?: any;
	textScale?: number;
	widescreenMode?: null;
	largeTextAsFile?: boolean;
	promptAutocomplete?: boolean;
	hapticFeedback?: boolean;
	responseAutoCopy?: any;
	richTextInput?: boolean;
	params?: any;
	userLocation?: any;
	webSearch?: any;
	memory?: boolean;
	autoFollowUps?: boolean;
	splitLargeChunks?(body: any, splitLargeChunks: any): unknown;
	backgroundImageUrl?: null;
	landingPageMode?: string;
	iframeSandboxAllowForms?: boolean;
	iframeSandboxAllowSameOrigin?: boolean;
	scrollOnBranchChange?: boolean;
	chatBubble?: boolean;
	copyFormatted?: boolean;
	models?: string[];
	conversationMode?: boolean;
	speechAutoSend?: boolean;
	responseAutoPlayback?: boolean;
	audio?: AudioSettings;
	showUsername?: boolean;
	highContrastMode?: boolean;
	title?: TitleSettings;
	showChatTitleInTab?: boolean;
	splitLargeDeltas?: boolean;
	chatDirection?: 'ltr' | 'rtl' | 'auto';
	ctrlEnterToSend?: boolean;
	renderMarkdownInPreviews?: boolean;

	system?: string;
	seed?: number;
	temperature?: string;
	repeat_penalty?: string;
	top_k?: string;
	top_p?: string;
	num_ctx?: string;
	num_batch?: string;
	num_keep?: string;
	options?: ModelOptions;
};

type ModelOptions = {
	stop?: boolean;
};

type AudioSettings = {
	stt: any;
	tts: any;
	STTEngine?: string;
	TTSEngine?: string;
	speaker?: string;
	model?: string;
	nonLocalVoices?: boolean;
};

type TitleSettings = {
	auto?: boolean;
	model?: string;
	modelExternal?: string;
	prompt?: string;
};

type Document = {
	collection_name: string;
	filename: string;
	name: string;
	title: string;
};

type Config = {
	[key: string]: any;
	status: boolean;
	name: string;
	version: string;
	default_locale: string;
	default_models: string;
	default_prompt_suggestions: PromptSuggestion[];
	features: {
		[key: string]: any;
		auth: boolean;
		auth_trusted_header: boolean;
		enable_api_keys: boolean;
		enable_signup: boolean;
		enable_login_form: boolean;
		enable_web_search?: boolean;
		enable_stable_diffusion?: boolean;
		enable_music_generation?: boolean;
		enable_video_generation?: boolean;
		enable_admin_export: boolean;
		enable_admin_chat_access: boolean;
		enable_admin_analytics: boolean;
		enable_community_sharing: boolean;
		enable_memories: boolean;
		enable_autocomplete_generation: boolean;
		enable_direct_connections: boolean;
		enable_version_update_check: boolean;
		folder_max_file_count?: number;
	};
	oauth: {
		providers: {
			[key: string]: string;
		};
	};
	ui?: {
		[key: string]: any;
		pending_user_overlay_title?: string;
		pending_user_overlay_content?: string;
	};
};

type PromptSuggestion = {
	content: string;
	title: [string, string];
};

export type SessionUser = {
	[key: string]: any;
	permissions: any;
	id: string;
	email: string;
	name: string;
	role: string;
	profile_image_url: string;
};
