<script lang="ts">
	import { toast } from 'svelte-sonner';
	import { createEventDispatcher, onMount, getContext } from 'svelte';
	import { browser } from '$app/environment';
	const dispatch = createEventDispatcher();

	import { config, models, settings, theme, user } from '$lib/stores';
	import Switch from '$lib/components/common/Switch.svelte';
	import ManageFloatingActionButtonsModal from './Interface/ManageFloatingActionButtonsModal.svelte';

	const i18n = getContext('i18n');

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

	let enableMessageQueue = true;
	let temporaryChatByDefault = false;
	let showFloatingActionButtons = true;
	let floatingActionButtons = null;
	let showManageFloatingActionButtonsModal = false;
	let largeTextAsFile = false;
	let widescreenMode = false;
	let expandDetails = false;
	let chatBubble = true;
	let backgroundImageUrl: string | null = null;
	let filesInputElement: HTMLInputElement;
	let inputFiles: FileList | null = null;

	let system = '';

	let showAdvanced = false;

	let params = {
		// Advanced
		stream_response: null,
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
				stream_response: params.stream_response !== null ? params.stream_response : undefined,
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

		enableMessageQueue = $settings?.enableMessageQueue ?? true;
		temporaryChatByDefault = $settings?.temporaryChatByDefault ?? false;
		showFloatingActionButtons = $settings?.showFloatingActionButtons ?? true;
		floatingActionButtons = $settings?.floatingActionButtons ?? null;
		largeTextAsFile = $settings?.largeTextAsFile ?? false;
		widescreenMode = $settings?.widescreenMode ?? false;
		expandDetails = $settings?.expandDetails ?? false;
		chatBubble = $settings?.chatBubble ?? true;
		backgroundImageUrl = $settings?.backgroundImageUrl ?? null;

		system = $settings.system ?? '';

		params = { ...params, ...$settings.params };
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
		theme.set(_theme);
		localStorage.setItem('theme', _theme);
		applyTheme(_theme);
	};
</script>

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
				<div class=" self-center text-sm font-medium">{$i18n.t('Theme')}</div>
				<div class="flex items-center">
					<div class="relative flex rounded-xl bg-gray-100 dark:bg-gray-850 p-0.5">
						<div
							class="absolute top-0.5 bottom-0.5 bg-white dark:bg-gray-700 rounded-lg shadow-sm pointer-events-none transition-transform duration-200 ease-in-out"
							style="left: 2px; width: calc((100% - 4px) / 3); transform: translateX(calc({selectedTheme === 'system' ? 0 : selectedTheme === 'light' ? 1 : 2} * 100%))"
						></div>
						<button
							class="relative z-10 flex items-center justify-center p-2 transition-colors duration-150 {selectedTheme === 'system' ? 'text-gray-900 dark:text-white' : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200'}"
							on:click={() => { selectedTheme = 'system'; themeChangeHandler('system'); }}
							title={$i18n.t('System')}
						>
							<svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
								<path stroke-linecap="round" stroke-linejoin="round" d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
							</svg>
						</button>
						<button
							class="relative z-10 flex items-center justify-center p-2 transition-colors duration-150 {selectedTheme === 'light' ? 'text-gray-900 dark:text-white' : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200'}"
							on:click={() => { selectedTheme = 'light'; themeChangeHandler('light'); }}
							title={$i18n.t('Light')}
						>
							<svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
								<path stroke-linecap="round" stroke-linejoin="round" d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
							</svg>
						</button>
						<button
							class="relative z-10 flex items-center justify-center p-2 transition-colors duration-150 {selectedTheme === 'dark' ? 'text-gray-900 dark:text-white' : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200'}"
							on:click={() => { selectedTheme = 'dark'; themeChangeHandler('dark'); }}
							title={$i18n.t('Dark')}
						>
							<svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
								<path stroke-linecap="round" stroke-linejoin="round" d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
							</svg>
						</button>
					</div>
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
							tooltip={true}
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
					<div id="always-expand-label" class=" self-center text-sm">
						{$i18n.t('Always Expand Details')}
					</div>

					<div class="flex items-center gap-2 p-1">
						<Switch
							ariaLabelledbyId="always-expand-label"
							tooltip={true}
							bind:state={expandDetails}
							on:change={() => {
								saveSettings({ expandDetails });
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
							tooltip={true}
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
								tooltip={true}
								bind:state={temporaryChatByDefault}
								on:change={() => {
									saveSettings({ temporaryChatByDefault });
								}}
							/>
						</div>
					</div>
				</div>
			{/if}



			<input
				bind:this={filesInputElement}
				bind:files={inputFiles}
				type="file"
				hidden
				accept="image/*"
				on:change={() => {
					let reader = new FileReader();
					reader.onload = (event) => {
						let originalImageUrl = `${event.target.result}`;
						backgroundImageUrl = originalImageUrl;
						saveSettings({ backgroundImageUrl });
					};

					if (
						inputFiles &&
						inputFiles.length > 0 &&
						['image/gif', 'image/webp', 'image/jpeg', 'image/png'].includes(inputFiles[0]['type'])
					) {
						reader.readAsDataURL(inputFiles[0]);
					} else {
						console.log(`Unsupported File Type '${inputFiles[0]['type']}'.`);
						inputFiles = null;
					}
				}}
			/>

			<div>
				<div class=" py-0.5 flex w-full justify-between">
					<div id="chat-background-label" class=" self-center text-sm">
						{$i18n.t('Chat Background Image')}
					</div>

					<button
						aria-labelledby="chat-background-label background-image-url-state"
						class="p-1 px-3 text-sm flex rounded-sm transition"
						on:click={() => {
							if (backgroundImageUrl !== null) {
								backgroundImageUrl = null;
								saveSettings({ backgroundImageUrl });
							} else {
								filesInputElement.click();
							}
						}}
						type="button"
					>
						<span class="ml-2 self-center" id="background-image-url-state"
							>{backgroundImageUrl !== null ? $i18n.t('Reset') : $i18n.t('Upload')}</span
						>
					</button>
				</div>
			</div>

		</div>

	</div>

</div>
