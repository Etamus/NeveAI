<script lang="ts">
	import { createEventDispatcher, onMount, getContext } from 'svelte';
	import { browser } from '$app/environment';
	const dispatch = createEventDispatcher();

	import { settings, theme, user } from '$lib/stores';
	import Switch from '$lib/components/common/Switch.svelte';
	import ManageFloatingActionButtonsModal from './Interface/ManageFloatingActionButtonsModal.svelte';
	import { changeLanguage } from '$lib/i18n';
	import { getLanguagePreference, type LanguagePreference } from '$lib/i18n/languagePreferences';
	import CheckCircle from '../../icons/CheckCircle.svelte';
	import ThemePreview from './ThemePreview.svelte';

	import type { I18nStore } from '$lib/i18n';
	const i18n = getContext<I18nStore>('i18n');

	import AdvancedParams from './Advanced/AdvancedParams.svelte';
	import Textarea from '$lib/components/common/Textarea.svelte';
	export let saveSettings: Function;
	export let getModels: Function;

	// General
	let themes = ['dark', 'light'];
	const themeSelectorOptions = ['system', 'light', 'dark'];
	const getSelectedTheme = () => {
		if (!browser) return 'system';

		const storedTheme = localStorage.getItem('theme') ?? 'system';
		return themeSelectorOptions.includes(storedTheme) ? storedTheme : 'system';
	};
	let selectedTheme = getSelectedTheme();
	let selectedLanguage: LanguagePreference = getLanguagePreference();
	let showLanguageDropdown = false;
	let themeSwitchGeneration = 0;

	let enableMessageQueue = true;
	let temporaryChatByDefault = false;
	let showFloatingActionButtons = true;
	let floatingActionButtons = null;
	let showManageFloatingActionButtonsModal = false;
	let largeTextAsFile = false;
	let widescreenMode = false;
	let streamResponse = true;
	let chatBubble = true;

	let system = '';


	let params: Record<string, any> = {
		// Advanced
		stream_delta_chunk_size: null,
		function_calling: null,
		seed: null,
		temperature: null,
		reasoning_effort: null,
		logit_bias: null,
		frequency_penalty: null,
		presence_penalty: null,
		repeat_penalty: null,
		repeat_last_n: null,
		mirostat: null,
		mirostat_eta: null,
		mirostat_tau: null,
		top_k: null,
		top_p: null,
		min_p: null,
		stop: null,
		tfs_z: null,
		num_ctx: null,
		num_batch: null,
		num_keep: null,
		max_tokens: null,
		num_gpu: null
	};

	const saveHandler = async () => {
		saveSettings({
			system: system !== '' ? system : undefined,
			params: {
				stream_delta_chunk_size:
					params.stream_delta_chunk_size !== null ? params.stream_delta_chunk_size : undefined,
				function_calling: params.function_calling !== null ? params.function_calling : undefined,
				seed: (params.seed !== null ? params.seed : undefined) ?? undefined,
				stop: params.stop ? params.stop.split(',').filter((e) => e) : undefined,
				temperature: params.temperature !== null ? params.temperature : undefined,
				reasoning_effort: params.reasoning_effort !== null ? params.reasoning_effort : undefined,
				logit_bias: params.logit_bias !== null ? params.logit_bias : undefined,
				frequency_penalty: params.frequency_penalty !== null ? params.frequency_penalty : undefined,
				presence_penalty: params.frequency_penalty !== null ? params.frequency_penalty : undefined,
				repeat_penalty: params.frequency_penalty !== null ? params.frequency_penalty : undefined,
				repeat_last_n: params.repeat_last_n !== null ? params.repeat_last_n : undefined,
				mirostat: params.mirostat !== null ? params.mirostat : undefined,
				mirostat_eta: params.mirostat_eta !== null ? params.mirostat_eta : undefined,
				mirostat_tau: params.mirostat_tau !== null ? params.mirostat_tau : undefined,
				top_k: params.top_k !== null ? params.top_k : undefined,
				top_p: params.top_p !== null ? params.top_p : undefined,
				min_p: params.min_p !== null ? params.min_p : undefined,
				tfs_z: params.tfs_z !== null ? params.tfs_z : undefined,
				num_ctx: params.num_ctx !== null ? params.num_ctx : undefined,
				num_batch: params.num_batch !== null ? params.num_batch : undefined,
				num_keep: params.num_keep !== null ? params.num_keep : undefined,
				max_tokens: params.max_tokens !== null ? params.max_tokens : undefined,
				use_mmap: params.use_mmap !== null ? params.use_mmap : undefined,
				use_mlock: params.use_mlock !== null ? params.use_mlock : undefined,
				num_thread: params.num_thread !== null ? params.num_thread : undefined,
				num_gpu: params.num_gpu !== null ? params.num_gpu : undefined,
				think: params.think !== null ? params.think : undefined,
				keep_alive: params.keep_alive !== null ? params.keep_alive : undefined,
				format: params.format !== null ? params.format : undefined
			}
		});
		dispatch('save');
	};

	onMount(async () => {
		selectedTheme = getSelectedTheme();
		selectedLanguage = getLanguagePreference();

		enableMessageQueue = $settings?.enableMessageQueue ?? true;
		temporaryChatByDefault = $settings?.temporaryChatByDefault ?? false;
		showFloatingActionButtons = $settings?.showFloatingActionButtons ?? true;
		floatingActionButtons = $settings?.floatingActionButtons ?? null;
		largeTextAsFile = $settings?.largeTextAsFile ?? false;
		widescreenMode = $settings?.widescreenMode ?? false;
		streamResponse = $settings?.streamResponse ?? true;
		chatBubble = $settings?.chatBubble ?? true;

		system = $settings.system ?? '';

		const settingsParams = { ...($settings.params ?? {}) };
		delete settingsParams.stream_response;
		params = { ...params, ...settingsParams };
		params.stop = $settings?.params?.stop ? ($settings?.params?.stop ?? []).join(',') : null;
	});

	const applyTheme = (_theme: string) => {
		let themeToApply = _theme;

		if (_theme === 'system') {
			themeToApply = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
		}

		if (themeToApply === 'dark') {
			document.documentElement.style.setProperty('--color-gray-800', '#333');
			document.documentElement.style.setProperty('--color-gray-850', '#262626');
			document.documentElement.style.setProperty('--color-gray-900', '#171717');
			document.documentElement.style.setProperty('--color-gray-950', '#0d0d0d');
		}

		themes
			.filter((e) => e !== themeToApply)
			.forEach((e) => {
				e.split(' ').forEach((e) => {
					document.documentElement.classList.remove(e);
				});
			});

		themeToApply.split(' ').forEach((e) => {
			document.documentElement.classList.add(e);
		});

		const metaThemeColor = document.querySelector('meta[name="theme-color"]');
		if (metaThemeColor) {
			if (_theme.includes('system')) {
				const systemTheme = window.matchMedia('(prefers-color-scheme: dark)').matches
					? 'dark'
					: 'light';
				console.log('Setting system meta theme color: ' + systemTheme);
				metaThemeColor.setAttribute('content', systemTheme === 'light' ? '#ffffff' : '#171717');
			} else {
				console.log('Setting meta theme color: ' + _theme);
				metaThemeColor.setAttribute(
					'content',
					_theme === 'dark'
						? '#171717'
						: '#ffffff'
				);
			}
		}

		if (typeof window !== 'undefined' && window.applyTheme) {
			window.applyTheme();
		}

		console.log(_theme);
	};

	const themeChangeHandler = (_theme: string) => {
		const root = document.documentElement;
		const generation = ++themeSwitchGeneration;
		root.classList.add('theme-switching');
		void root.offsetWidth;

		theme.set(_theme);
		localStorage.setItem('theme', _theme);
		applyTheme(_theme);

		requestAnimationFrame(() => {
			requestAnimationFrame(() => {
				if (generation === themeSwitchGeneration) {
					root.classList.remove('theme-switching');
				}
			});
		});
	};

	const selectLanguage = (language: LanguagePreference) => {
		selectedLanguage = language;
		showLanguageDropdown = false;
		changeLanguage(language);
	};
</script>

<svelte:window
	on:click={(event) => {
		if (!(event.target as HTMLElement).closest('#interface-language-control')) {
			showLanguageDropdown = false;
		}
	}}
	on:keydown={(event) => {
		if (event.key === 'Escape') showLanguageDropdown = false;
	}}
/>

<ManageFloatingActionButtonsModal
	bind:show={showManageFloatingActionButtonsModal}
	{floatingActionButtons}
	onSave={(buttons) => {
		floatingActionButtons = buttons;
		saveSettings({ floatingActionButtons });
	}}
/>

<div class="flex flex-col h-full justify-between text-sm" id="tab-general" on:change={saveHandler}>
	<div class="  overflow-y-scroll max-h-[28rem] md:max-h-full">
		<div class="">


			<div class="flex w-full justify-between">
				<div class="shrink-0 whitespace-nowrap self-center text-sm font-medium">{$i18n.t('Theme')}</div>
				<div class="flex items-center">
					<div class="flex items-center gap-3 p-1" role="group" aria-label={$i18n.t('Theme')}>
						{#each themeSelectorOptions as option}
							<button type="button" data-theme-option={option} aria-pressed={selectedTheme === option}
								aria-label={$i18n.t(option === 'system' ? 'System' : option === 'light' ? 'Light' : 'Dark')}
								title={$i18n.t(option === 'system' ? 'System' : option === 'light' ? 'Light' : 'Dark')}
								class="theme-option relative shrink-0 rounded-lg outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2"
								on:click={() => { selectedTheme = option; themeChangeHandler(option); }}>
								<ThemePreview mode={option} />
							</button>
						{/each}
					</div>
				</div>
			</div>

			<div class="mt-2 py-0.5 flex w-full items-center justify-between gap-3">
				<div id="interface-language-label" class="self-center text-sm font-medium">{$i18n.t('Language')}</div>
				<div id="interface-language-control" class="relative shrink-0">
					<button
					type="button"
					class="flex items-center gap-1 rounded-full px-2 py-[7px] text-[0.8125rem] text-gray-600 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-800"
					aria-labelledby="interface-language-label"
					aria-expanded={showLanguageDropdown}
					on:click={() => { showLanguageDropdown = !showLanguageDropdown; }}
					>
						<span>{selectedLanguage === 'auto' ? $i18n.t('Automatic detection') : selectedLanguage === 'en-US' ? $i18n.t('English') : 'Português (Brasil)'}</span>
						<svg viewBox="0 0 20 20" fill="currentColor" class="size-3.5 transition-transform duration-150 {showLanguageDropdown ? '' : 'rotate-180'}" aria-hidden="true"><path fill-rule="evenodd" d="M14.78 12.78a.75.75 0 0 1-1.06 0L10 9.06l-3.72 3.72a.75.75 0 0 1-1.06-1.06l4.25-4.25a.75.75 0 0 1 1.06 0l4.25 4.25a.75.75 0 0 1 0 1.06Z" clip-rule="evenodd" /></svg>
					</button>
					{#if showLanguageDropdown}
						<div class="absolute right-0 top-full z-50 mt-1.5 w-44 rounded-lg border border-gray-200 bg-white p-1 text-sm shadow-md dark:border-gray-800 dark:bg-gray-850">
							{#each [{ id: 'auto', label: $i18n.t('Automatic detection') }, { id: 'pt-BR', label: 'Português (Brasil)' }, { id: 'en-US', label: $i18n.t('English') }] as language}
								<button type="button" class="flex w-full items-center justify-between rounded-md px-2 py-2 text-left text-gray-700 hover:bg-gray-100 dark:text-gray-200 dark:hover:bg-gray-800" on:click={() => selectLanguage(language.id as LanguagePreference)}>
									<span>{language.label}</span>{#if selectedLanguage === language.id}<CheckCircle className="size-4" strokeWidth="1.7" />{/if}
								</button>
							{/each}
						</div>
					{/if}
				</div>
			</div>

			<div class="mt-2">
				<div class=" py-0.5 flex w-full justify-between">
					<div id="widescreen-mode-label" class=" self-center text-sm">
						{$i18n.t('Widescreen Mode')}
					</div>

					<div class="flex items-center gap-2 p-1">
						<Switch
							ariaLabelledbyId="widescreen-mode-label"
							bind:state={widescreenMode}
							on:change={() => {
								saveSettings({ widescreenMode });
							}}
						/>
					</div>
				</div>
			</div>

			<div>
				<div class=" py-0.5 flex w-full justify-between">
					<div id="stream-response-label" class=" self-center text-sm">
						{$i18n.t('Stream response')}
					</div>

					<div class="flex items-center gap-2 p-1">
						<Switch
							ariaLabelledbyId="stream-response-label"
							bind:state={streamResponse}
							on:change={() => {
								saveSettings({ streamResponse });
							}}
						/>
					</div>
				</div>
			</div>

			<div>
				<div class=" py-0.5 flex w-full justify-between">
					<div id="enable-message-queue-label" class=" self-center text-sm">
						{$i18n.t('Enable Message Queue')}
					</div>

					<div class="flex items-center gap-2 p-1">
						<Switch
							ariaLabelledbyId="enable-message-queue-label"
							bind:state={enableMessageQueue}
							on:change={() => {
								saveSettings({ enableMessageQueue });
							}}
						/>
					</div>
				</div>
			</div>

			{#if $user.role === 'admin' || $user?.permissions?.chat?.temporary}
				<div>
					<div class=" py-0.5 flex w-full justify-between">
						<div id="temp-chat-default-label" class=" self-center text-sm">
							{$i18n.t('Temporary Chat by Default')}
						</div>

						<div class="flex items-center gap-2 p-1">
							<Switch
								ariaLabelledbyId="temp-chat-default-label"
								bind:state={temporaryChatByDefault}
								on:change={() => {
									saveSettings({ temporaryChatByDefault });
								}}
							/>
						</div>
					</div>
				</div>
			{/if}



		</div>

	</div>

</div>

<style>
	.theme-option::after {
		content: '';
		position: absolute;
		inset: 0;
		border: 2px solid transparent;
		border-radius: inherit;
		pointer-events: none;
		transition: border-color 150ms;
	}
	.theme-option[aria-pressed='false']:hover::after { border-color: #d1d5db; }
	:global(.dark) .theme-option[aria-pressed='false']:hover::after { border-color: #4b5563; }
	.theme-option[aria-pressed='true']::after { border-color: #3b82f6; }
</style>
