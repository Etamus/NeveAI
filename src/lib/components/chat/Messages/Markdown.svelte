<script>
	import { onDestroy, setContext } from 'svelte';
	import { replaceTokens, processResponseContent } from '$lib/utils';
	import { user } from '$lib/stores';

	import { createChatMarkdownParser } from '$lib/utils/marked/chat-lexer';
	import { createStreamingMarkdownScheduler } from '$lib/utils/marked/streaming-parser';
	import { prepareStreamingMarkdown, stabilizeStreamingBlocks } from '$lib/utils/marked/streaming-display';
	import { changesVisibleStructure } from '$lib/utils/marked/streaming-structure';

	import MarkdownTokens from './Markdown/MarkdownTokens.svelte';

	export let id = '';
	export let content;
	export let done = true;
	export let streaming = null;
	export let model = null;
	export let save = false;
	export let preview = false;

	export let paragraphTag = 'p';
	export let editCodeBlock = false;
	export let topPadding = false;

	export let sourceIds = [];

	export let onSave = () => {};
	export let onUpdate = () => {};

	export let onPreview = () => {};

	export let onSourceClick = () => {};
	export let onTaskClick = () => {};

	let tokens = [];
	let parse = createChatMarkdownParser();
	let context = [];
	let snapshot = '';
	let modelName;
	let userName;
	let streamActive = false;
	let completedSnapshot = null;
	let repairActive = false;
	const paintContext = { suppress: false };
	setContext('streaming-text-paint', paintContext);
	const scheduler = createStreamingMarkdownScheduler(() => {
		const processed = replaceTokens(processResponseContent(snapshot), modelName, userName);
		const parsed = parse(repairActive ? prepareStreamingMarkdown(processed) : processed);
		const next = repairActive ? stabilizeStreamingBlocks(parsed) : parsed;
		paintContext.suppress = repairActive && changesVisibleStructure(tokens, next);
		tokens = next;
	});

	const updateHandler = (value, isDone, isStreaming, messageId, nextModelName, nextUserName) => {
		const changedId = context[0] !== messageId;
		const changedContext = changedId || context[1] !== nextModelName || context[2] !== nextUserName;
		if (changedId) {
			parse = createChatMarkdownParser();
			completedSnapshot = null;
		}
		context = [messageId, nextModelName, nextUserName];
		snapshot = value ?? '';
		modelName = nextModelName;
		userName = nextUserName;
		const finished = streamActive && !isStreaming;
		streamActive = isStreaming;
		if (!isStreaming) completedSnapshot = snapshot;
		// Continuing has not produced a new snapshot yet; keep the completed Markdown intact.
		const waitingForContinuation = isStreaming && snapshot === completedSnapshot;
		if (isStreaming && !waitingForContinuation) completedSnapshot = null;
		repairActive = isStreaming && !waitingForContinuation;
		scheduler.update(!isStreaming || finished || changedContext || snapshot.length === 0, snapshot.length > 0);
	};

	$: updateHandler(content, done, streaming ?? !done, id, model?.name, $user?.name);
	onDestroy(() => scheduler.destroy());
</script>

{#key id}
	<MarkdownTokens
		{tokens}
		{id}
		{done}
		{save}
		{preview}
		{paragraphTag}
		{editCodeBlock}
		{sourceIds}
		{topPadding}
		{onTaskClick}
		{onSourceClick}
		{onSave}
		{onUpdate}
		{onPreview}
	/>
{/key}
