<script lang="ts">
	import { v4 as uuidv4 } from 'uuid';

	import { getContext, onDestroy } from 'svelte';
	const i18n = getContext('i18n');

	import dayjs from '$lib/dayjs';
	import duration from 'dayjs/plugin/duration';
	import relativeTime from 'dayjs/plugin/relativeTime';

	dayjs.extend(duration);
	dayjs.extend(relativeTime);

	import { slide } from 'svelte/transition';
	import { quintOut } from 'svelte/easing';

	import ChevronUp from '../icons/ChevronUp.svelte';
	import ChevronDown from '../icons/ChevronDown.svelte';
	import Spinner from './Spinner.svelte';

	import { notifyChatLayout } from '$lib/utils/notifyChatLayout';

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
	$: showReasoningContent = isReasoning && !hide && open;
	let activityElement: HTMLDivElement;
	function notifyReasoningLayout(automatic = false) {
		if (isReasoning) activityElement?.dispatchEvent(new CustomEvent('neve:reasoning-layout', {
			bubbles: true, detail: { opening: !open, automatic }
		}));
		else notifyChatLayout(activityElement, isCodeInterpreter ? 200 : grow ? 300 : 100, !open);
	}

	let wasStreamingReasoning = false;
	$: if (isReasoning) {
		if (isStreaming) {
			wasStreamingReasoning = true;
		} else if (isDone && wasStreamingReasoning) {
			if (open) notifyReasoningLayout(true);
			open = false;
			wasStreamingReasoning = false;
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

	function handleReasoningWheel(event: WheelEvent) {
		if (!showReasoningContent || !reasoningScrollEl) return;

		event.preventDefault();
		event.stopPropagation();

		const maxScrollTop = Math.max(
			0,
			reasoningScrollEl.scrollHeight - reasoningScrollEl.clientHeight
		);
		if (maxScrollTop <= 0) return;

		const delta =
			event.deltaMode === WheelEvent.DOM_DELTA_LINE
				? event.deltaY * 16
				: event.deltaMode === WheelEvent.DOM_DELTA_PAGE
					? event.deltaY * reasoningScrollEl.clientHeight
					: event.deltaY;
		const nextScrollTop = Math.max(
			0,
			Math.min(maxScrollTop, reasoningScrollEl.scrollTop + delta)
		);

		if (Math.abs(nextScrollTop - reasoningScrollEl.scrollTop) <= 0.5) return;

		reasoningScrollEl.scrollTop = nextScrollTop;
		shouldAutoScroll = maxScrollTop - nextScrollTop < 24;
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
	<div
		{id}
		bind:this={activityElement}
		data-message-expanded={open && !hide}
		class="reasoning-block mb-4 w-full overflow-hidden {isReasoning ? 'reasoning-minimal' : 'code-interpreter-minimal'} transition-colors duration-150 border-transparent {className}"
		on:wheel|nonpassive={handleReasoningWheel}
	>
		<!-- svelte-ignore a11y-no-static-element-interactions -->
		<!-- svelte-ignore a11y-click-events-have-key-events -->
		<div
			class="reasoning-header flex select-none items-center justify-between gap-3 px-3 py-2 {disabled ? '' : 'cursor-pointer'}"
			on:pointerup={() => {
				if (!disabled) {
					notifyReasoningLayout();
					open = !open;
				}
			}}
		>
			<div
				class="flex min-w-0 flex-1 items-center gap-2 text-sm font-medium text-gray-600 transition-colors hover:text-gray-800 dark:text-gray-300 dark:hover:text-gray-100"
			>
				<span class="relative min-w-0 truncate pr-1 leading-5">
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
						className="size-3.5 shrink-0 translate-y-px text-gray-400 transition-transform duration-200 dark:text-gray-500 {open ? 'rotate-180' : 'rotate-0'}"
					/>
				{/if}
			</div>

		</div>

		<!-- Reasoning content -->
		{#if isReasoning}
			<div
				class="grid transition-[grid-template-rows] duration-150 ease-out {showReasoningContent
					? 'grid-rows-[1fr]'
					: 'grid-rows-[0fr]'}"
				aria-hidden={!showReasoningContent}
				inert={!showReasoningContent}
			>
				<div class="min-h-0 overflow-hidden">
					<div
						class="reasoning-content relative text-sm text-gray-600 dark:text-gray-400"
						>
						<div
							id="reasoning-content-{collapsibleId}"
							bind:this={reasoningScrollEl}
							on:scroll={handleReasoningScroll}
							class="reasoning-text scrollbar-hidden relative z-0 overflow-y-auto leading-relaxed text-gray-600 dark:text-gray-400 {isStreaming
									? 'h-40'
									: 'max-h-72'}"
						>
							<slot name="content" />
						</div>
					</div>
				</div>
			</div>
		{:else if isCodeInterpreter && open && !hide}
			<div
				class="ml-[7px] border-l border-[#dedede] text-sm text-gray-600 dark:border-[#292929] dark:text-gray-400"
				transition:slide={{ duration: 200, easing: quintOut, axis: 'y' }}
			>
				<div class="px-4 leading-relaxed">
					<slot name="content" />
				</div>
			</div>
		{/if}
	</div>
{:else}
	<!-- Original non-reasoning collapsible -->
	<div {id} class={className} bind:this={activityElement} data-message-expanded={open && !hide}>
		{#if title !== null}
			<!-- svelte-ignore a11y-no-static-element-interactions -->
			<!-- svelte-ignore a11y-click-events-have-key-events -->
			<div
				class="{buttonClassName} {disabled ? '' : 'cursor-pointer'}"
				on:pointerup={() => {
					if (!disabled) {
						notifyReasoningLayout();
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
						notifyReasoningLayout();
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

<style>
	.code-interpreter-minimal { border: 0; background: transparent; box-shadow: none; }
	.code-interpreter-minimal .reasoning-header { padding: 4px 0 8px; }
	.code-interpreter-minimal .reasoning-header > div { font-weight: 400; }
	.reasoning-minimal { border: 0; background: transparent; box-shadow: none; }
	.reasoning-minimal .reasoning-header { padding: 4px 0 8px; }
	.reasoning-minimal .reasoning-header > div { font-weight: 400; }
	.reasoning-content { margin: 0 0 0 7px; border-left: 1px solid #dedede; }
	:global(.dark) .reasoning-content { border-color: #292929; }
	.reasoning-text { padding: 0 16px; }
	.reasoning-text :global(blockquote) { border: 0; padding: 0; margin: 0; color: inherit; }
	.reasoning-text {
		font-size: 0.875rem !important;
	}

	.reasoning-text :global(*) {
		font-size: inherit !important;
	}

	.reasoning-text :global(sup),
	.reasoning-text :global(sub) {
		font-size: 0.75em !important;
	}
</style>
