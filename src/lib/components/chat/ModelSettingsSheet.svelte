<script lang="ts">
	import { fly } from 'svelte/transition';
	import { getContext } from 'svelte';
	import { showModelSettings, user } from '$lib/stores';
	import AdvancedParams from '$lib/components/chat/Settings/Advanced/AdvancedParams.svelte';
	import Sidebar from '$lib/components/icons/Sidebar.svelte';

	const i18n = getContext('i18n');

	export let params: Record<string, any> = {};
	export let selectedModelName = '';

	let showSystemPromptField = false;
	$: if ((params?.system ?? '') !== '') showSystemPromptField = true;

	const close = () => showModelSettings.set(false);
	const handleKeyDown = (event: KeyboardEvent) => {
		if (!$showModelSettings || event.key !== 'Escape' || event.isComposing || document.querySelector('.modal[aria-hidden="false"], [role="menu"][data-state="open"], [role="dialog"][data-state="open"]')) return;
		event.preventDefault();
		event.stopPropagation();
		close();
		document.getElementById('chat-parameters-button')?.focus({ preventScroll: true });
	};
</script>

<svelte:window on:keydown|capture={handleKeyDown} />

{#if $showModelSettings}
	<!-- Backdrop -->
	<button
		class="fixed inset-0 z-40 cursor-default bg-black/20 dark:bg-black/30"
		on:click={close}
		aria-label="Close settings"
		type="button"
		tabindex="-1"
	/>

	<!-- Sheet panel -->
	<div
		class="fixed top-0 right-0 bottom-0 z-50 flex flex-col bg-white dark:bg-gray-850 shadow-2xl overflow-hidden"
		style="width: min(360px, 100vw)"
		transition:fly={{ x: 360, duration: 220, opacity: 1 }}
	>
		<!-- Header — Jan-style -->
		<div
			class="relative flex items-start justify-between pl-5 pr-12 pt-5 pb-4 border-b border-gray-200/30 dark:border-gray-700/15 shrink-0"
		>
			<div class="min-w-0 flex-1">
				<h2 class="text-sm font-semibold text-gray-900 dark:text-white truncate leading-snug">
					{selectedModelName || $i18n.t('Controles')}
				</h2>
				<p class="text-xs text-gray-400 dark:text-gray-500 mt-0.5 leading-normal">
					{$i18n.t('Ajuste os parâmetros para esta conversa')}
				</p>
			</div>

			<button
				id="close-chat-parameters-button"
				class="absolute top-1 right-[calc(0.5rem+1px)] max-md:right-1.5 flex cursor-pointer px-2 py-2 rounded-xl hover:bg-gray-50 dark:hover:bg-gray-800 transition text-gray-600 dark:text-gray-400"
				on:click={close}
				aria-label={$i18n.t('Close')}
				type="button"
			>
				<Sidebar className="size-5 -scale-x-100" />
			</button>
		</div>

		<!-- Content -->
		<div id="model-settings-content" class="flex-1 overflow-y-auto px-4 py-3 scrollbar-hidden">
			{#if $user?.role === 'admin' || ($user?.permissions?.chat?.controls ?? true)}
				<div class="text-sm text-gray-700 dark:text-gray-300">
					{#if $user?.role === 'admin' || ($user?.permissions?.chat?.params ?? true)}
						<div class="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3 mt-4">
							{$i18n.t('Par\u00e2metros avan\u00e7ados')}
						</div>
						<div class="mt-3">
							<AdvancedParams
								admin={$user?.role === 'admin'}
								custom={true}
								separators={true}
								janStyle={true}
								fixedJanRows={true}
								tooltipsEnabled={false}
								bind:params
							>
								<div
									slot="janFooter"
									hidden={!(
										$user?.role === 'admin' ||
										($user?.permissions?.chat?.system_prompt ?? true)
									)}
								>
									<div class="flex h-[34px] w-full items-center justify-between py-0">
										{#if showSystemPromptField}
											<button
												type="button"
												class="text-xs text-gray-700 dark:text-gray-300 underline decoration-dotted cursor-pointer hover:text-gray-500 dark:hover:text-gray-400 transition"
												on:click={() => {
													params.system = '';
													showSystemPromptField = false;
												}}>{$i18n.t('Prompt do sistema')}</button
											>
										{:else}
											<div class="text-xs text-gray-700 dark:text-gray-300">
												{$i18n.t('Prompt do sistema')}
											</div>
										{/if}
										{#if !showSystemPromptField}
											<button
												type="button"
												class="text-xs text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300 transition px-2 py-0.5 rounded-md border border-gray-200 dark:border-gray-700"
												on:click={() => {
													showSystemPromptField = true;
												}}>{$i18n.t('Default')}</button
											>
										{/if}
									</div>
									{#if showSystemPromptField}
										<div class="pt-1">
											<textarea
												bind:value={params.system}
												class="w-full text-xs border border-gray-200/40 dark:border-gray-700/30 rounded-lg px-3 py-2 outline-hidden resize-none overflow-y-auto focus:border-gray-300 dark:focus:border-gray-600 transition min-h-[5rem] outline-none resize-vertical bg-transparent py-1.5"
												rows="4"
												placeholder={$i18n.t('Enter system prompt')}
											/>
										</div>
									{/if}
								</div>
							</AdvancedParams>
						</div>
					{/if}
				</div>
			{/if}
		</div>
	</div>
{/if}
