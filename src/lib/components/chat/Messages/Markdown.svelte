<script>
	import { onDestroy } from 'svelte';
	import { replaceTokens, processResponseContent } from '$lib/utils';
	import { user } from '$lib/stores';

	import { createChatMarkdownParser } from '$lib/utils/marked/chat-lexer';
	import { createStreamingMarkdownScheduler } from '$lib/utils/marked/streaming-parser';

	import MarkdownTokens from './Markdown/MarkdownTokens.svelte';

	export let id = '';
	export let content;
	export let done = true;
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
	const scheduler = createStreamingMarkdownScheduler(() => {
		const processed = replaceTokens(processResponseContent(snapshot), modelName, userName);
		tokens = parse(processed);
	});

	const updateHandler = (value, isDone, messageId, nextModelName, nextUserName) => {
		const changedId = context[0] !== messageId;
		const changedContext = changedId || context[1] !== nextModelName || context[2] !== nextUserName;
		if (changedId) parse = createChatMarkdownParser();
		context = [messageId, nextModelName, nextUserName];
		snapshot = value ?? '';
		modelName = nextModelName;
		userName = nextUserName;
		scheduler.update(isDone || changedContext || snapshot.length === 0, snapshot.length > 0);
	};

	$: updateHandler(content, done, id, model?.name, $user?.name);
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
