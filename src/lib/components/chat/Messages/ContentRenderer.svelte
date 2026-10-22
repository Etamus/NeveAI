<script>
	import { onDestroy, onMount, tick, getContext } from 'svelte';
	import { autoUpdate, computePosition, flip, offset, shift } from '@floating-ui/dom';
	const i18n = getContext('i18n');

	import Markdown from './Markdown.svelte';
	import {
		artifactCode,
		chatCodeExecutionEnabled,
		chatId,
		mobile,
		settings,
		showArtifacts,
		showControls,
		showEmbeds
	} from '$lib/stores';
	import FloatingButtons from '../ContentRenderer/FloatingButtons.svelte';
	import { createMessagesList } from '$lib/utils';

	export let id;
	export let content;

	export let history;
	export let messageId;

	export let selectedModels = [];

	export let done = true;
	export let messageDone = done;
	export let model = null;
	export let sources = null;

	export let save = false;
	export let preview = false;
	export let floatingButtons = true;

	export let editCodeBlock = false;
	export let topPadding = false;

	$: artifactsPreviewEnabled = preview && $chatCodeExecutionEnabled;

	export let onSave = (e) => {};
	export let onSourceClick = (e) => {};
	export let onTaskClick = (e) => {};

	let hasStreamingMessage = false;
	$: hasStreamingMessage = Object.values(history?.messages ?? {}).some(
		(message) => message?.role !== 'user' && message?.done === false
	);
	export let onAddMessages = (e) => {};

	let contentContainerElement;
	let floatingButtonsElement;
	let stopFloatingPosition;

	let sourceIds = [];
	$: getSourceIds(sources);

	const getSourceIds = (sources) => {
		const result = [];
		for (const source of sources ?? []) {
			for (let index = 0; index < (source.document ?? []).length; index++) {
				if (model?.info?.meta?.capabilities?.citations == false) {
					result.push('N/A');
					continue;
				}
				const metadata = source.metadata?.[index];
				const id = metadata?.source ?? 'N/A';
				if (metadata?.name) {
					result.push(metadata.name);
				} else if (id.startsWith('http://') || id.startsWith('https://')) {
					result.push(id);
				} else {
					result.push(source?.source?.name ?? id);
				}
			}
		}
		sourceIds = [...new Set(result)];
	};

	const updateButtonPosition = (event) => {
		const buttonsContainerElement = document.getElementById(`floating-buttons-${id}`);
		if (
			!contentContainerElement?.contains(event.target) &&
			!buttonsContainerElement?.contains(event.target)
		) {
			closeFloatingButtons();
			return;
		}

		setTimeout(async () => {
			await tick();

			if (!contentContainerElement?.contains(event.target)) return;

			let selection = window.getSelection();

			if (selection.toString().trim().length > 0) {
				const range = selection.getRangeAt(0).cloneRange();

				if (buttonsContainerElement) {
					buttonsContainerElement.style.display = 'block';

					stopFloatingPosition?.();
					const reference = {
						getBoundingClientRect: () => range.getBoundingClientRect(),
						contextElement: contentContainerElement
					};
					stopFloatingPosition = autoUpdate(reference, buttonsContainerElement, async () => {
						const { x, y } = await computePosition(reference, buttonsContainerElement, {
							strategy: 'fixed', placement: 'bottom-start',
							middleware: [offset(8), flip(), shift({ padding: 8 })]
						});
						if (!buttonsContainerElement.isConnected) return;
						Object.assign(buttonsContainerElement.style, { left: `${x}px`, top: `${y}px`, right: 'auto' });
					});
				}
			} else {
				closeFloatingButtons();
			}
		}, 0);
	};

	const closeFloatingButtons = () => {
		stopFloatingPosition?.();
		stopFloatingPosition = null;
		const buttonsContainerElement = document.getElementById(`floating-buttons-${id}`);
		if (buttonsContainerElement) {
			buttonsContainerElement.style.display = 'none';
		}

		if (floatingButtonsElement) {
			// check if closeHandler is defined

			if (typeof floatingButtonsElement?.closeHandler === 'function') {
				// call the closeHandler function
				floatingButtonsElement?.closeHandler();
			}
		}
	};

	const keydownHandler = (e) => {
		if (e.key === 'Escape') {
			closeFloatingButtons();
		}
	};

	onMount(() => {
		if (floatingButtons) {
			document.addEventListener('mouseup', updateButtonPosition);
			document.addEventListener('keydown', keydownHandler);
		}
	});

	onDestroy(() => {
		stopFloatingPosition?.();
		if (floatingButtons) {
			document.removeEventListener('mouseup', updateButtonPosition);
			document.removeEventListener('keydown', keydownHandler);
		}
	});
</script>

<div bind:this={contentContainerElement}>
	<Markdown
		{id}
		{content}
		{model}
		{save}
		preview={artifactsPreviewEnabled}
		{done}
		{editCodeBlock}
		{topPadding}
		{sourceIds}
		{onSourceClick}
		{onTaskClick}
		{onSave}
		onUpdate={async (token) => {
			const { lang: rawLang, text: code } = token;
			const lang = rawLang?.match(/^[\w+#.-]+/)?.[0] ?? rawLang;

			if (
				!hasStreamingMessage &&
				messageDone &&
				$chatCodeExecutionEnabled &&
				($settings?.detectArtifacts ?? true) &&
				(['html', 'svg'].includes(lang) || (lang === 'xml' && code.includes('svg'))) &&
				!$mobile &&
				$chatId
			) {
				await tick();
				showArtifacts.set(true);
				showControls.set(true);
			}
		}}
		onPreview={async (value) => {
			if (!$chatCodeExecutionEnabled) return;

			await artifactCode.set(value);
			await showControls.set(true);
			await showArtifacts.set(true);
			await showEmbeds.set(false);
		}}
	/>
</div>

{#if floatingButtons}
	<FloatingButtons
		bind:this={floatingButtonsElement}
		{id}
		{messageId}
		actions={$settings?.floatingActionButtons ?? []}
		model={(selectedModels ?? []).includes(model?.id)
			? model?.id
			: (selectedModels ?? []).length > 0
				? selectedModels.at(0)
				: (model?.id ?? null)}
		messages={createMessagesList(history, messageId)}
		onAdd={({ modelId, parentId, messages }) => {
			console.log(modelId, parentId, messages);
			onAddMessages({ modelId, parentId, messages });
			closeFloatingButtons();
		}}
	/>
{/if}
