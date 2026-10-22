<script lang="ts">
	import { toast } from 'svelte-sonner';

	import { getContext, tick, onDestroy } from 'svelte';
	const i18n = getContext('i18n');
	const prepareModel = getContext<((modelId: string) => Promise<{params: Record<string, unknown>} | null>) | undefined>('prepare-text-model');

	import { chatCompletion } from '$lib/apis/openai';
	import { createOpenAITextStream } from '$lib/apis/streaming';
	import { getSelectionActionLabel } from '$lib/utils/selectionActions';
	import { removeReasoningControlTokens } from '$lib/utils';

	import ChatBubble from '$lib/components/icons/ChatBubble.svelte';
	import LightBulb from '$lib/components/icons/LightBulb.svelte';
	import Markdown from '../Messages/Markdown.svelte';
	import Skeleton from '../Messages/Skeleton.svelte';
	import { chatId, models, socket } from '$lib/stores';

	export let id = '';
	export let messageId = '';

	export let model = null;
	export let messages = [];
	export let actions = [];
	export let onAdd = (e) => {};

	let floatingInput = false;
	let selectedAction = null;

	let selectedText = '';
	let floatingInputValue = '';

	let content = '';
	let responseContent = null;
	let responseDone = false;
	let controller = null;
	let requestVersion = 0;
	let responseError = '';
	let responseModel = null;
	let responseContainer: HTMLDivElement;
	const portal = (node: HTMLElement) => {
		document.body.appendChild(node);
		return { destroy: () => node.remove() };
	};

	$: if (actions.length === 0) {
		actions = DEFAULT_ACTIONS;
	}

	const DEFAULT_ACTIONS = [
		{
			id: 'ask',
			label: $i18n.t('Ask'),
			icon: ChatBubble,
			input: true,
			prompt: `{{SELECTED_CONTENT}}\n\n\n{{INPUT_CONTENT}}`
		},
		{
			id: 'explain',
			label: $i18n.t('Explain'),
			icon: LightBulb,
			prompt: `{{SELECTED_CONTENT}}\n\n\n${$i18n.t('Explain')}`
		}
	];

	const autoScroll = async () => {
		if (responseContainer) {
			responseContainer.scrollTop = responseContainer.scrollHeight;
		}
	};

	const actionHandler = async (actionId) => {
		if (controller && !responseDone) return;
		if (!model) {
			toast.error($i18n.t('Model not selected'));
			return;
		}

		let selectedContent = selectedText
			.split('\n')
			.map((line) => `> ${line}`)
			.join('\n');

		let selectedAction = actions.find((action) => action.id === actionId);
		if (!selectedAction) {
			toast.error($i18n.t('Action not found'));
			return;
		}
		if (selectedAction.prompt?.includes('{{INPUT_CONTENT}}') && !floatingInputValue.trim()) return;

		let prompt = selectedAction?.prompt ?? '';
		let toolIds = [];

		// Handle: {{variableId|tool:id="toolId"}} pattern
		// This regex captures variableId and toolId from {{variableId|tool:id="toolId"}}
		const varToolPattern = /\{\{(.*?)\|tool:id="([^"]+)"\}\}/g;
		prompt = prompt.replace(varToolPattern, (match, variableId, toolId) => {
			toolIds.push(toolId);
			return variableId; // Replace with just variableId
		});

		// legacy {{TOOL:toolId}} pattern (for backward compatibility)
		let toolIdPattern = /\{\{TOOL:([^\}]+)\}\}/g;
		let match;
		while ((match = toolIdPattern.exec(prompt)) !== null) {
			toolIds.push(match[1]);
		}

		// Remove all TOOL placeholders from the prompt
		prompt = prompt.replace(toolIdPattern, '');

		if (prompt.includes('{{INPUT_CONTENT}}') && floatingInput) {
			prompt = prompt.replace('{{INPUT_CONTENT}}', floatingInputValue);
			floatingInputValue = '';
		}

		prompt = prompt.replace('{{CONTENT}}', selectedText);
		prompt = prompt.replace('{{SELECTED_CONTENT}}', selectedContent);

		content = prompt;
		responseContent = '';
		responseDone = false;
		responseError = '';
		const requestModel = model;
		responseModel = requestModel;
		const version = ++requestVersion;
		const requestController = new AbortController();
		controller = requestController;
		try {
			const prepared = prepareModel ? await prepareModel(requestModel) : {};
			if (!prepared) {
				if (version === requestVersion) responseError = $i18n.t('Could not load the selected model.');
				return;
			}
			if (version !== requestVersion || requestController.signal.aborted) return;
			const [res] = await chatCompletion(localStorage.token, {
			...prepared,
			model: requestModel,
			model_item: $models.find((m) => m.id === requestModel),
			session_id: $socket?.id,
			chat_id: $chatId,
			messages: [
				...messages,
				{
					role: 'user',
					content: content
				}
			].map((message) => ({
				role: message.role,
				content: message.content
			})),
			...(toolIds.length > 0
				? {
						tool_ids: toolIds
						// params: {
						// 	function_calling: 'native'
						// }
					}
				: {}),

			stream: true
		}, undefined, requestController);
			if (!res?.ok || !res.body) throw new Error($i18n.t('An error occurred while fetching the explanation'));
			const stream = await createOpenAITextStream(res.body, false);
			for await (const update of stream) {
				if (version !== requestVersion || requestController.signal.aborted) break;
				if (update.error) throw new Error(update.error.message ?? String(update.error));
				const follow = !responseContainer || responseContainer.scrollHeight - responseContainer.clientHeight <= responseContainer.scrollTop + 50;
				responseContent += update.value;
				await tick();
				if (follow) await autoScroll();
				if (update.done) break;
			}
			if (version === requestVersion && !requestController.signal.aborted) {
				if (!removeReasoningControlTokens(responseContent).trim()) throw new Error($i18n.t('An error occurred while fetching the explanation'));
				const follow = !responseContainer || responseContainer.scrollHeight - responseContainer.clientHeight <= responseContainer.scrollTop + 50;
				responseDone = true;
				await tick();
				if (follow) await autoScroll();
			}
		} catch (error) {
			if (version === requestVersion && !requestController.signal.aborted) {
				responseError = error?.message ?? $i18n.t('An error occurred while fetching the explanation');
				toast.error(responseError);
			}
		} finally {
			if (version === requestVersion) controller = null;
		}
	};

	const addHandler = async () => {
		const messages = [
			{
				role: 'user',
				content: content
			},
			{
				role: 'assistant',
				content: responseContent
			}
		];

		onAdd({
			modelId: responseModel,
			parentId: messageId,
			messages: messages
		});
	};

	export const closeHandler = () => {
		requestVersion += 1;
		if (controller) {
			controller.abort();
		}

		selectedAction = null;
		selectedText = '';
		responseContent = null;
		responseDone = false;
		responseError = '';
		controller = null;
		floatingInput = false;
		floatingInputValue = '';
	};

	onDestroy(() => {
		requestVersion += 1;
		if (controller) {
			controller.abort();
		}
	});
</script>

<div
	id={`floating-buttons-${id}`}
	class="fixed text-xs z-9999 max-w-[calc(100vw-16px)]"
	style="display: none"
	use:portal
	on:wheel|stopPropagation
	on:touchmove|stopPropagation
>
	{#if responseContent === null}
		{#if !floatingInput}
			<div
				class="flex flex-row shrink-0 p-0.5 bg-white dark:bg-gray-850 dark:text-gray-100 text-medium rounded-lg shadow-xl border border-gray-100 dark:border-gray-800"
			>
				{#each actions as action}
					<button
						aria-label={getSelectionActionLabel(action, (key) => $i18n.t(key))}
						class="px-1.5 py-[1px] hover:bg-gray-50 dark:hover:bg-gray-800 rounded-md flex items-center gap-1 min-w-fit transition"
						on:click={async () => {
							selectedText = window.getSelection().toString();
							selectedAction = action;

							if (action.prompt.includes('{{INPUT_CONTENT}}')) {
								floatingInput = true;
								floatingInputValue = '';

								await tick();
								setTimeout(() => {
									const input = document.getElementById('floating-message-input');
									if (input) {
										input.focus();
									}
								}, 0);
							} else {
								actionHandler(action.id);
							}
						}}
					>
						{#if action.icon}
							<svelte:component this={action.icon} className="size-3 shrink-0" />
						{/if}
						<div class="shrink-0">{getSelectionActionLabel(action, (key) => $i18n.t(key))}</div>
					</button>
				{/each}
			</div>
		{:else}
			<div
				class="py-1 flex dark:text-gray-100 bg-white dark:bg-gray-850 border border-gray-100 dark:border-gray-800 w-72 max-w-full rounded-xl shadow-xl"
			>
				<input
					type="text"
					id="floating-message-input"
					autocomplete="off"
					class="ml-5 bg-transparent outline-hidden w-full flex-1 text-sm"
					placeholder={$i18n.t('Ask a question')}
					aria-label={$i18n.t('Ask a question')}
					bind:value={floatingInputValue}
					on:keydown={(e) => {
						if (e.key === 'Enter' && !e.isComposing) {
							actionHandler(selectedAction?.id);
						}
					}}
				/>

				<div class="ml-1 mr-1">
					<button
						aria-label={$i18n.t('Submit question')}
						disabled={!floatingInputValue.trim()}
						class="{floatingInputValue !== ''
							? 'bg-black text-white hover:bg-gray-900 dark:bg-white dark:text-black dark:hover:bg-gray-100 '
							: 'text-white bg-gray-200 dark:text-gray-900 dark:bg-gray-700 disabled'} transition rounded-full p-1.5 m-0.5 self-center"
						on:click={() => {
							actionHandler(selectedAction?.id);
						}}
					>
						<svg
							xmlns="http://www.w3.org/2000/svg"
							viewBox="0 0 16 16"
							fill="currentColor"
							class="size-4"
						>
							<path
								fill-rule="evenodd"
								d="M8 14a.75.75 0 0 1-.75-.75V4.56L4.03 7.78a.75.75 0 0 1-1.06-1.06l4.5-4.5a.75.75 0 0 1 1.06 0l4.5 4.5a.75.75 0 0 1-1.06 1.06L8.75 4.56v8.69A.75.75 0 0 1 8 14Z"
								clip-rule="evenodd"
							/>
						</svg>
					</button>
				</div>
			</div>
		{/if}
	{:else}
		<div
			class="bg-white dark:bg-gray-850 dark:text-gray-100 rounded-2xl overflow-hidden p-1 shadow-xl w-80 max-w-full border border-gray-100 dark:border-gray-800"
		>
			<div
				class="text-medium max-h-28 overflow-y-auto overscroll-contain px-2.5 pt-2 w-full"
			>
				<div class="font-medium">
					<Markdown id={`${id}-float-prompt`} {content} />
				</div>
			</div>

			<div class="text-medium w-full min-h-0">
				<div
					class="max-h-[min(20rem,45dvh)] overflow-y-auto overscroll-contain w-full markdown-prose-xs px-2.5 py-3 rounded-xl"
					style="scrollbar-gutter: stable;"
					data-selection-response
					bind:this={responseContainer}
				>
					{#if responseError}
						<div role="alert">{responseError}</div>
					{:else if !responseContent || responseContent?.trim() === ''}
						<Skeleton size="sm" />
					{:else}
						<Markdown id={`${id}-float-response`} content={removeReasoningControlTokens(responseContent)} />
					{/if}

					{#if responseDone && !responseError && responseContent?.trim()}
						<div class="flex justify-end pt-3 text-sm font-medium">
							<button
								class="px-3.5 py-1.5 text-sm font-medium bg-black hover:bg-gray-900 text-white dark:bg-white dark:text-black dark:hover:bg-gray-100 transition rounded-lg"
								on:click={addHandler}
							>
								{$i18n.t('Add')}
							</button>
						</div>
					{/if}
				</div>
			</div>
		</div>
	{/if}
</div>
