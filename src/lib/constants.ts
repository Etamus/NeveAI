import { browser, dev } from '$app/environment';
// import { version } from '../../package.json';

declare const APP_VERSION: string;
declare const APP_BUILD_HASH: string;

export const APP_NAME = 'Neve';

export const NEVEAI_HOSTNAME = browser ? (dev ? `` : ``) : '';
export const NEVEAI_BASE_URL = browser ? (dev ? `` : ``) : ``;
export const NEVEAI_API_BASE_URL = `${NEVEAI_BASE_URL}/api/v1`;

export const AUDIO_API_BASE_URL = `${NEVEAI_BASE_URL}/api/v1/audio`;
export const RETRIEVAL_API_BASE_URL = `${NEVEAI_BASE_URL}/api/v1/retrieval`;

export const NEVEAI_VERSION = APP_VERSION;

export const DEFAULT_CAPABILITIES = {
	file_context: true,
	vision: true,
	file_upload: true,
	web_search: true,
	citations: true,
	status_updates: true,
	usage: undefined,
	builtin_tools: true,
	toggle_reasoning: true
};

export const PASTED_TEXT_CHARACTER_LIMIT = 1000;

// Source: https://kit.svelte.dev/docs/modules#$env-static-public
// This feature, akin to $env/static/private, exclusively incorporates environment variables
// that are prefixed with config.kit.env.publicPrefix (usually set to PUBLIC_).
// Consequently, these variables can be securely exposed to client-side code.
