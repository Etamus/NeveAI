<script lang="ts">
	import { decode } from 'html-entities';
	import { v4 as uuidv4 } from 'uuid';

	import { getContext, tick, onDestroy } from 'svelte';
	const i18n = getContext('i18n');

	import dayjs from '$lib/dayjs';
	import duration from 'dayjs/plugin/duration';
	import relativeTime from 'dayjs/plugin/relativeTime';

	dayjs.extend(duration);
	dayjs.extend(relativeTime);

	async function loadLocale(locales) {
		if (!locales || !Array.isArray(locales)) {
			return;
		}
		for (const locale of locales) {
			try {
				dayjs.locale(locale);
				break; // Stop after successfully loading the first available locale
			} catch (error) {
				console.error(`Could not load locale '${locale}':`, error);
			}
		}
	}

	// Assuming $i18n.languages is an array of language codes
	$: loadLocale($i18n.languages);

	import { slide } from 'svelte/transition';
	import { quintOut } from 'svelte/easing';

	import ChevronUp from '../icons/ChevronUp.svelte';
	import ChevronDown from '../icons/ChevronDown.svelte';
	import Lightbulb from '../icons/Lightbulb.svelte';
	import Terminal from '../icons/Terminal.svelte';
	import Spinner from './Spinner.svelte';

	import { copyToClipboard } from '$lib/utils';

	export let open = false;

	export let className = '';
	export let buttonClassName =
		'w-fit text-gray-500 hover:text-gray-700 dark:hover:text-gray-300 transition';

	export let id = '';
	export let title = null;
	export let attributes = null;

	export let chevron = false;
	export let grow = false;

	export let disabled = false;
	export let hide = false;

	export let onChange: Function = () => {};

	$: onChange(open);

	const collapsibleId = uuidv4();

	// Reasoning-specific state
	$: isReasoning = attributes?.type === 'reasoning';
	$: isCodeInterpreter = attributes?.type === 'code_interpreter';
	$: isActivityBlock = isReasoning || isCodeInterpreter;
	$: reasoningDoneValue = attributes?.done == null ? '' : String(attributes.done);
	$: isDone = isReasoning && reasoningDoneValue === 'true';
	$: isStreaming = isReasoning && !isDone;
	$: isCodeInterpreterRunning = isCodeInterpreter && attributes?.done !== 'true';
	$: showReasoningContent = isReasoning && !hide && (open || isStreaming);
	$: showActivityChrome = isReasoning ? showReasoningContent : isCodeInterpreter && open && !hide;
	$: reasoningPreviewMode = isReasoning && isStreaming && !open;

	let wasStreamingReasoning = false;
	$: if (isReasoning) {
		if (isStreaming) {
			wasStreamingReasoning = true;
		} else if (isDone && wasStreamingReasoning) {
			open = false;
			wasStreamingReasoning = false;
		}
	}

	let copied = false;
	let copyTimeout: ReturnType<typeof setTimeout>;

	function handleCopy(event: MouseEvent) {
		event.stopPropagation();
		const contentEl = document.getElementById(`reasoning-content-${collapsibleId}`);
		if (contentEl) {
			copyToClipboard(contentEl.innerText);
			copied = true;
			clearTimeout(copyTimeout);
			copyTimeout = setTimeout(() => (copied = false), 2000);
		}
	}

	// Auto-scroll for reasoning content during streaming
	let reasoningScrollEl: HTMLDivElement;
	let shouldAutoScroll = true;
	let mutationObserver: MutationObserver | null = null;

	function handleReasoningScroll() {
		if (!reasoningScrollEl) return;
		const { scrollTop, scrollHeight, clientHeight } = reasoningScrollEl;
		shouldAutoScroll = scrollHeight - scrollTop - clientHeight < 24;
	}

	function scrollToBottom() {
		if (reasoningScrollEl && shouldAutoScroll) {
			reasoningScrollEl.scrollTop = reasoningScrollEl.scrollHeight;
		}
	}

	function startObserving() {
		stopObserving();
		if (reasoningScrollEl) {
			mutationObserver = new MutationObserver(() => {
				scrollToBottom();
			});
			mutationObserver.observe(reasoningScrollEl, {
				childList: true,
				subtree: true,
				characterData: true
			});
		}
	}

	function stopObserving() {
		if (mutationObserver) {
			mutationObserver.disconnect();
			mutationObserver = null;
		}
	}

	$: if (isStreaming && showReasoningContent && reasoningScrollEl) {
		startObserving();
	} else {
		stopObserving();
	}

	onDestroy(() => {
		stopObserving();
	});
</script>

{#if isActivityBlock}
	<!-- LM Studio-inspired reasoning block -->
	<div
		{id}
		class="reasoning-block mb-4 w-full overflow-hidden rounded-xl transition-all duration-200 {showActivityChrome
			? 'border border-gray-200/80 bg-gray-50/70 shadow-[0_1px_2px_rgba(15,23,42,0.04)] dark:border-white/10 dark:bg-white/[0.035] dark:shadow-none'
			: ''} {className}"
	>
		<!-- svelte-ignore a11y-no-static-element-interactions -->
		<!-- svelte-ignore a11y-click-events-have-key-events -->
		<div
			class="flex items-center justify-between gap-3 px-3 py-2 {disabled ? '' : 'cursor-pointer'}"
			on:pointerup={() => {
				if (!disabled) {
					open = !open;
				}
			}}
		>
			<div
				class="flex min-w-0 flex-1 items-center gap-2 text-sm font-medium text-gray-600 transition-colors hover:text-gray-800 dark:text-gray-300 dark:hover:text-gray-100"
			>
				<span
					class="flex size-5 shrink-0 items-center justify-center rounded-full bg-white text-gray-500 ring-1 ring-gray-200 dark:bg-white/5 dark:text-gray-300 dark:ring-white/10"
				>
					{#if isReasoning}
						<Lightbulb className="size-3.5" strokeWidth="1.6" />
					{:else}
						<Terminal className="size-3.5" strokeWidth="1.7" />
					{/if}
				</span>

				<span class="relative min-w-0 truncate leading-5">
					{#if isReasoning}
						{#if isStreaming}
							<span class="shimmer text-sm leading-5">{$i18n.t('Thinking...')}</span>
						{:else if isDone && attributes?.duration}
							{#if attributes.duration < 1}
								{$i18n.t('Thought for less than a second')}
							{:else if attributes.duration < 60}
								{$i18n.t('Thought for {{DURATION}} seconds', {
									DURATION: attributes.duration
								})}
							{:else}
								{$i18n.t('Thought for {{DURATION}}', {
									DURATION: dayjs.duration(attributes.duration, 'seconds').humanize()
								})}
							{/if}
						{:else}
							{$i18n.t('Thinking...')}
						{/if}
					{:else}
						<span class="{isCodeInterpreterRunning ? 'shimmer' : ''} text-sm leading-5">
							{#if attributes?.done === 'true'}
								{$i18n.t('Analyzed')}
							{:else}
								{$i18n.t('Analyzing...')}
							{/if}
						</span>
					{/if}
				</span>

				{#if !disabled}
					<ChevronDown
						strokeWidth="2.4"
						className="size-3.5 shrink-0 translate-y-px text-gray-400 transition-transform duration-200 dark:text-gray-500 {open
							? 'rotate-0'
							: '-rotate-90'}"
					/>
				{/if}
			</div>

			<!-- Copy button - only show when open and done -->
			{#if isReasoning && open && isDone}
				<button
					class="inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-xs text-gray-500 transition-colors hover:bg-gray-200/70 hover:text-gray-800 dark:text-gray-400 dark:hover:bg-white/10 dark:hover:text-gray-100"
					on:pointerup|stopPropagation={handleCopy}
					aria-label="Copy reasoning"
				>
					{#if copied}
						<svg
							xmlns="http://www.w3.org/2000/svg"
							fill="none"
							viewBox="0 0 24 24"
							stroke-width="2"
							stroke="currentColor"
							class="size-3"
							aria-hidden="true"
						>
							<path
								stroke-linecap="round"
								stroke-linejoin="round"
								d="m4.5 12.75 6 6 9-13.5"
							/>
						</svg>
						{$i18n.t('Copied')}
					{:else}
						<svg
							xmlns="http://www.w3.org/2000/svg"
							fill="none"
							viewBox="0 0 24 24"
							stroke-width="2"
							stroke="currentColor"
							class="size-3"
							aria-hidden="true"
						>
							<path
								stroke-linecap="round"
								stroke-linejoin="round"
								d="M15.666 3.888A2.25 2.25 0 0 0 13.5 2.25h-3c-1.03 0-1.9.693-2.166 1.638m7.332 0c.055.194.084.4.084.612v0a.75.75 0 0 1-.75.75H9.75a.75.75 0 0 1-.75-.75v0c0-.212.03-.418.084-.612m7.332 0c.646.049 1.288.11 1.927.184 1.1.128 1.907 1.077 1.907 2.185V19.5a2.25 2.25 0 0 1-2.25 2.25H6.75A2.25 2.25 0 0 1 4.5 19.5V6.257c0-1.108.806-2.057 1.907-2.185a48.208 48.208 0 0 1 1.927-.184"
							/>
						</svg>
						{$i18n.t('Copy')}
					{/if}
				</button>
			{/if}
		</div>

		<!-- Reasoning content -->
		{#if isReasoning && showReasoningContent}
			<div
				class="reasoning-content relative border-t border-gray-200/70 bg-white/55 text-sm text-gray-600 dark:border-white/10 dark:bg-black/10 dark:text-gray-300"
				transition:slide={{ duration: 200, easing: quintOut, axis: 'y' }}
			>
				{#if isStreaming}
					<div
						class="reasoning-fade-top pointer-events-none absolute inset-x-0 top-0 z-10 h-5 bg-gradient-to-b from-white/90 to-transparent dark:from-gray-950/70"
					></div>
				{/if}

				<div
					id="reasoning-content-{collapsibleId}"
					bind:this={reasoningScrollEl}
					on:scroll={handleReasoningScroll}
					class="reasoning-text relative z-0 overflow-y-auto px-3 py-2.5 leading-relaxed text-gray-600 dark:text-gray-300 {reasoningPreviewMode
						? 'max-h-24'
						: isStreaming
							? 'max-h-40'
							: 'max-h-72'}"
				>
					<slot name="content" />
				</div>

				<div
					class="reasoning-fade pointer-events-none absolute inset-x-0 bottom-0 z-10 h-7 bg-gradient-to-t from-white/95 to-transparent dark:from-gray-950/80"
				></div>
			</div>
		{:else if isCodeInterpreter && open && !hide}
			<div
				class="border-t border-gray-200/70 bg-white/55 text-sm text-gray-600 dark:border-white/10 dark:bg-black/10 dark:text-gray-300"
				transition:slide={{ duration: 200, easing: quintOut, axis: 'y' }}
			>
				<div class="px-3 py-2.5 leading-relaxed">
					<slot name="content" />
				</div>
			</div>
		{/if}
	</div>
{:else}
	<!-- Original non-reasoning collapsible -->
	<div {id} class={className}>
		{#if title !== null}
			<!-- svelte-ignore a11y-no-static-element-interactions -->
			<!-- svelte-ignore a11y-click-events-have-key-events -->
			<div
				class="{buttonClassName} {disabled ? '' : 'cursor-pointer'}"
				on:pointerup={() => {
					if (!disabled) {
						open = !open;
					}
				}}
			>
				<div
					class=" w-full flex items-center justify-between gap-2 {attributes?.done &&
					attributes?.done !== 'true'
						? 'shimmer'
						: ''}
				"
				>
					{#if attributes?.done && attributes?.done !== 'true'}
						<div>
							<Spinner className="size-4" />
						</div>
					{/if}

					<div class="">
						{#if attributes?.type === 'code_interpreter'}
							{#if attributes?.done === 'true'}
								{$i18n.t('Analyzed')}
							{:else}
								{$i18n.t('Analyzing...')}
							{/if}
						{:else}
							{title}
						{/if}
					</div>

					{#if !disabled}
						<div class="flex self-center translate-y-[1px]">
							{#if open}
								<ChevronUp strokeWidth="2" className="size-3" />
							{:else}
								<ChevronDown strokeWidth="2" className="size-3" />
							{/if}
						</div>
					{/if}
				</div>
			</div>
		{:else}
			<!-- svelte-ignore a11y-no-static-element-interactions -->
			<!-- svelte-ignore a11y-click-events-have-key-events -->
			<div
				class="{buttonClassName} cursor-pointer"
				on:click={(e) => {
					e.stopPropagation();
				}}
				on:pointerup={(e) => {
					if (!disabled) {
						open = !open;
					}
				}}
			>
				<div>
					<div class="flex items-start justify-between">
						<slot />

						{#if chevron}
							<div class="flex self-start translate-y-1">
								{#if open}
									<ChevronUp strokeWidth="3.5" className="size-3.5" />
								{:else}
									<ChevronDown strokeWidth="3.5" className="size-3.5" />
								{/if}
							</div>
						{/if}
					</div>

					{#if grow}
						{#if open && !hide}
							<div
								transition:slide={{ duration: 300, easing: quintOut, axis: 'y' }}
								on:pointerup={(e) => {
									e.stopPropagation();
								}}
							>
								<slot name="content" />
							</div>
						{/if}
					{/if}
				</div>
			</div>
		{/if}

		{#if !grow}
			{#if open && !hide}
				<div
					class="overflow-hidden"
					transition:slide={{ duration: 100, easing: quintOut, axis: 'y' }}
				>
					<slot name="content" />
				</div>
			{/if}
		{/if}
	</div>
{/if}
