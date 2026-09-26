<script lang="ts">
	import '$lib/utils/codemirror';
	import { basicSetup, EditorView } from 'codemirror';
	import { EditorState, Compartment } from '@codemirror/state';
	import { keymap } from '@codemirror/view';
	import { indentWithTab } from '@codemirror/commands';
	import { html as htmlLang } from '@codemirror/lang-html';
	import { oneDark } from '@codemirror/theme-one-dark';
	import { indentUnit } from '@codemirror/language';
	import { toast } from 'svelte-sonner';
	import { onMount, getContext, createEventDispatcher } from 'svelte';
	import type { I18nStore } from '$lib/i18n';
	const i18n = getContext<I18nStore>('i18n');
	const dispatch = createEventDispatcher();

	import {
		artifactCode,
		chatId,
		settings,
		showArtifacts,
		showControls,
		artifactContents
	} from '$lib/stores';
	import { copyToClipboard, createMessagesList } from '$lib/utils';

	import XMark from '../icons/XMark.svelte';
	import ArrowsPointingOut from '../icons/ArrowsPointingOut.svelte';
	import Tooltip from '../common/Tooltip.svelte';
	import SvgPanZoom from '../common/SVGPanZoom.svelte';
	import Download from '../icons/Download.svelte';
	import CodeBracket from '../icons/CodeBracket.svelte';
	import Cube from '../icons/Cube.svelte';
	import Code from '../icons/Code.svelte';
	export let overlay = false;

	let contents: Array<{ type: string; content: string; rawHtml?: string; rawCss?: string; rawJs?: string }> = [];
	let selectedContentIdx = 0;
	let activeTab: 'preview' | 'code' = 'preview';

	let copied = false;
	let iframeElement: HTMLIFrameElement;

	// Extract <title> tag from HTML content
	function extractTitle(content: string): string {
		const match = content.match(/<title[^>]*>([^<]+)<\/title>/i);
		return match ? match[1].trim() : '';
	}

	$: currentContent = contents[selectedContentIdx];
	$: artifactTitle = currentContent ? extractTitle(currentContent.content) : '';
	$: artifactType = currentContent?.type === 'svg' ? 'SVG' : 'HTML';

	// Build the raw code shown in the editor from the separate parts
	function getRawCode(item: typeof currentContent): string {
		if (!item) return '';
		if (item.type === 'svg') return item.content;
		if (item.rawHtml !== undefined) {
			let parts: string[] = [];
			if (item.rawHtml) parts.push(item.rawHtml);
			if (item.rawCss) parts.push(`${'<'}style>\n${item.rawCss}\n${'<'}/style>`);
			if (item.rawJs) parts.push(`${'<'}script>\n${item.rawJs}\n${'<'}/script>`);
			return parts.join('\n\n');
		}
		return item.content;
	}

	// Rebuild the full wrapped HTML from raw parts
	function buildWrappedContent(rawHtml: string, rawCss: string, rawJs: string): string {
		return `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    ${'<'}style>
        body { background-color: white; }
        ${rawCss}
    ${'<'}/style>
</head>
<body>
    ${rawHtml}
    ${'<'}script>
        ${rawJs}
    ${'<'}/script>
</body>
</html>`;
	}

	// Parse raw editor code back into html/css/js parts
	function parseRawCode(code: string): { html: string; css: string; js: string } {
		let css = '';
		let js = '';
		let html = code;
		// Extract <style> blocks
		html = html.replace(new RegExp('<style[^>]*>([\\s\\S]*?)<\\/style>', 'gi'), (_, content) => {
			css += content.trim() + '\n';
			return '';
		});
		// Extract <script> blocks
		html = html.replace(new RegExp('<script[^>]*>([\\s\\S]*?)<\\/script>', 'gi'), (_, content) => {
			js += content.trim() + '\n';
			return '';
		});
		return { html: html.trim(), css: css.trim(), js: js.trim() };
	}

	// CodeMirror editor state
	let codeEditor: EditorView | null = null;
	let editorTheme = new Compartment();
	let editorIsSource = false;

	// Sync editor content when currentContent changes externally (new version from AI, index switch)
	$: if (codeEditor && currentContent) {
		if (editorIsSource) {
			editorIsSource = false;
		} else {
			const incoming = getRawCode(currentContent);
			const curr = codeEditor.state.doc.toString();
			if (curr !== incoming) {
				codeEditor.dispatch({ changes: { from: 0, to: curr.length, insert: incoming } });
			}
		}
	}

	// Svelte action: mount CodeMirror into the given div
	function initEditor(node: HTMLElement) {
		const isDark = document.documentElement.classList.contains('dark');

		codeEditor = new EditorView({
			state: EditorState.create({
				doc: getRawCode(contents[selectedContentIdx]),
				extensions: [
					basicSetup,
					keymap.of([indentWithTab]),
					indentUnit.of('\t'),
					htmlLang(),
					editorTheme.of(isDark ? oneDark : []),
					EditorView.theme({
						'&': { height: '100%', fontSize: '13px' },
						'.cm-scroller': {
							overflow: 'auto',
							fontFamily: 'ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,"Liberation Mono","Courier New",monospace'
						},
						'.cm-content': { minHeight: '100%' },
					}),
					EditorView.updateListener.of((update) => {
						if (update.docChanged) {
							editorIsSource = true;
							const newRawCode = update.state.doc.toString();
							const item = contents[selectedContentIdx];
							if (item.type === 'svg') {
								contents[selectedContentIdx] = { ...item, content: newRawCode };
							} else {
								const parsed = parseRawCode(newRawCode);
								contents[selectedContentIdx] = {
									...item,
									rawHtml: parsed.html,
									rawCss: parsed.css,
									rawJs: parsed.js,
									content: buildWrappedContent(parsed.html, parsed.css, parsed.js)
								};
							}
							contents = contents;
						}
					}),
				]
			}),
			parent: node
		});

		// Keep in sync with dark mode toggle
		const observer = new MutationObserver(() => {
			const dark = document.documentElement.classList.contains('dark');
			codeEditor?.dispatch({ effects: editorTheme.reconfigure(dark ? oneDark : []) });
		});
		observer.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] });

		return {
			destroy() {
				observer.disconnect();
				codeEditor?.destroy();
				codeEditor = null;
			}
		};
	}

	const iframeLoadHandler = () => {
		iframeElement.contentWindow.addEventListener(
			'click',
			function (e) {
				const target = e.target.closest('a');
				if (target && target.href) {
					e.preventDefault();
					const url = new URL(target.href, iframeElement.baseURI);
					if (url.origin === window.location.origin) {
						iframeElement.contentWindow.history.pushState(
							null,
							'',
							url.pathname + url.search + url.hash
						);
					} else {
						console.info('External navigation blocked:', url.href);
					}
				}
			},
			true
		);

		// Cancel drag when hovering over iframe
		iframeElement.contentWindow.addEventListener('mouseenter', function (e) {
			e.preventDefault();
			iframeElement.contentWindow.addEventListener('dragstart', (event) => {
				event.preventDefault();
			});
		});
	};

	const showFullScreen = () => {
		if (iframeElement.requestFullscreen) {
			iframeElement.requestFullscreen();
		} else if ((iframeElement as any).webkitRequestFullscreen) {
			(iframeElement as any).webkitRequestFullscreen();
		} else if ((iframeElement as any).msRequestFullscreen) {
			(iframeElement as any).msRequestFullscreen();
		}
	};

	const downloadArtifact = () => {
		const blob = new Blob([contents[selectedContentIdx].content], { type: 'text/html' });
		const url = URL.createObjectURL(blob);
		const a = document.createElement('a');
		a.href = url;
		a.download = `artifact-${$chatId}-${selectedContentIdx}.html`;
		document.body.appendChild(a);
		a.click();
		document.body.removeChild(a);
		URL.revokeObjectURL(url);
	};

	onMount(() => {
		const unsubscribeArtifactCode = artifactCode.subscribe((value) => {
			if (contents) {
				const codeIdx = contents.findIndex((content) => content.content.includes(value));
				selectedContentIdx = codeIdx !== -1 ? codeIdx : 0;
			}
		});

		const unsubscribeArtifactContents = artifactContents.subscribe((value) => {
			const newContents = value ?? [];

			if (newContents.length === 0) {
				showControls.set(false);
				showArtifacts.set(false);
				selectedContentIdx = 0;
			} else if (newContents.length > contents.length) {
				selectedContentIdx = newContents.length - 1;
			} else {
				// Clamp index when switching to a chat with fewer versions
				selectedContentIdx = Math.min(selectedContentIdx, newContents.length - 1);
			}

			contents = newContents;
		});

		return () => {
			unsubscribeArtifactCode();
			unsubscribeArtifactContents();
		};
	});
</script>

<div
	class="w-full h-full relative flex flex-col bg-white dark:bg-gray-850 overflow-hidden"
	id="artifacts-container"
>
	{#if contents.length > 0}
		<!-- ── Toolbar: tabs + actions + close ──────────────────── -->
		<div
			class="shrink-0 flex flex-nowrap items-center justify-between gap-2 px-3 py-2
			       bg-gray-50 dark:bg-gray-900
			       border-b border-gray-200/80 dark:border-gray-700/60
			       min-h-[46px] max-h-[46px] overflow-hidden"
		>
			<!-- Preview / Code tab switcher (Arena.ai style) -->
			<div class="relative flex shrink-0 items-center p-[3px] rounded-lg bg-gray-100 dark:bg-gray-800/80">
				<!-- sliding indicator: w = calc(50% of container - 3px) = exactly one button wide; translate-x-full = own width -->
				<div
					class="absolute top-[3px] bottom-[3px] left-[3px] w-[calc(50%-3px)] rounded-md bg-white dark:bg-gray-700 shadow-sm transition-transform duration-200 ease-in-out pointer-events-none
					       {activeTab === 'code' ? 'translate-x-full' : 'translate-x-0'}"
				></div>
				<!-- Preview button -->
				<button
					class="relative z-10 flex items-center justify-center w-7 h-[26px] rounded-md transition-colors duration-200
					       {activeTab === 'preview'
						? 'text-gray-900 dark:text-white'
						: 'text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300'}"
					on:click={() => { activeTab = 'preview'; }}
					title={$i18n.t('Preview')}
				>
					<!-- arc + circle: single arc above a small ball -->
					<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" class="size-[17px]">
						<path d="M4 11 Q10 4.5 16 11"/>
						<circle cx="10" cy="13" r="2.2" fill="currentColor" stroke="none"/>
					</svg>
				</button>
				<!-- Code button -->
				<button
					class="relative z-10 flex items-center justify-center w-7 h-[26px] rounded-md transition-colors duration-200
					       {activeTab === 'code'
						? 'text-gray-900 dark:text-white'
						: 'text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300'}"
					on:click={() => { activeTab = 'code'; }}
					title={$i18n.t('Code')}
				>
					<!-- </> code icon -->
					<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" class="size-[17px]">
						<path d="M7 7l-4 3 4 3"/>
						<path d="M13 7l4 3-4 3"/>
						<path d="M11.5 5l-3 10"/>
					</svg>
				</button>
			</div>

			<!-- Right side: action buttons + close -->
			<div class="flex shrink-0 items-center gap-1">
				<!-- Download -->
				<Tooltip content={$i18n.t('Download')}>
					<button
						class="p-2 rounded-lg transition
						       text-gray-500 dark:text-gray-400
						       hover:bg-gray-200/70 dark:hover:bg-gray-700/70
						       hover:text-gray-900 dark:hover:text-gray-100"
						on:click={downloadArtifact}
					>
						<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" class="size-[18px]"><path stroke-linecap="round" stroke-linejoin="round" d="M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2M7 11l5 5 5-5M12 4v12"/></svg>
					</button>
				</Tooltip>

				<!-- Copy (icon only, somente na aba código) -->
				{#if activeTab === 'code'}
				<Tooltip content={copied ? $i18n.t('Copiado!') : $i18n.t('Copiar código')}>
					<button
						class="p-2 rounded-lg transition
						       text-gray-500 dark:text-gray-400
						       hover:bg-gray-200/70 dark:hover:bg-gray-700/70
						       hover:text-gray-900 dark:hover:text-gray-100"
						on:click={() => {
							copyToClipboard(contents[selectedContentIdx].content);
							copied = true;
							setTimeout(() => { copied = false; }, 2000);
						}}
					>
						{#if copied}
							<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" class="size-[18px]"><path stroke-linecap="round" stroke-linejoin="round" d="M4.5 12.75l6 6 9-13.5" /></svg>
						{:else}
							<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" class="size-[18px]"><path stroke-linecap="round" stroke-linejoin="round" d="M15.666 3.888A2.25 2.25 0 0 0 13.5 2.25h-3c-1.03 0-1.9.693-2.166 1.638m7.332 0c.055.194.084.4.084.612v0a.75.75 0 0 1-.75.75H9.75a.75.75 0 0 1-.75-.75v0c0-.212.03-.418.084-.612m7.332 0c.646.049 1.288.11 1.927.184 1.1.128 1.907 1.077 1.907 2.185V19.5a2.25 2.25 0 0 1-2.25 2.25H6.75A2.25 2.25 0 0 1 4.5 19.5V6.257c0-1.108.806-2.057 1.907-2.185a48.208 48.208 0 0 1 1.927-.184" /></svg>
						{/if}
					</button>
				</Tooltip>
				{/if}

				<!-- Fullscreen (iframe only, somente na aba preview) -->
				{#if currentContent?.type === 'iframe' && activeTab === 'preview'}
					<Tooltip content={$i18n.t('Open in full screen')}>
						<button
							class="p-2 rounded-lg transition
							       text-gray-500 dark:text-gray-400
							       hover:bg-gray-200/70 dark:hover:bg-gray-700/70
							       hover:text-gray-900 dark:hover:text-gray-100"
							on:click={showFullScreen}
						>
							<ArrowsPointingOut className="size-[18px]" />
						</button>
					</Tooltip>
				{/if}

				<!-- Separator before close -->
				<div class="w-px h-5 bg-gray-200 dark:bg-gray-700 mx-0.5"></div>

				<!-- Close -->
				<Tooltip content={$i18n.t('Close')}>
					<button
						class="p-2 rounded-lg transition
						       text-gray-500 dark:text-gray-400
						       hover:bg-gray-200/70 dark:hover:bg-gray-700/70
						       hover:text-gray-900 dark:hover:text-gray-100"
						on:click={() => {
							dispatch('close');
							showControls.set(false);
							showArtifacts.set(false);
						}}
					>
						<XMark className="size-[18px]" />
					</button>
				</Tooltip>
			</div>
		</div>
	{/if}

	<!-- ── Content area ────────────────────────────────────────── -->
	<div class="flex-1 w-full min-h-0 overflow-hidden relative">
		{#if overlay}
			<div class="absolute inset-0 z-10"></div>
		{/if}
		{#if contents.length > 0}
			{#if activeTab === 'preview'}
				<!-- Preview tab -->
				{#if currentContent?.type === 'iframe'}
					<iframe
						bind:this={iframeElement}
						title="Content"
						srcdoc={currentContent.content}
						class="w-full border-0 h-full rounded-none"
						sandbox="allow-scripts allow-downloads{($settings?.iframeSandboxAllowForms ?? false)
							? ' allow-forms'
							: ''}{($settings?.iframeSandboxAllowSameOrigin ?? false)
							? ' allow-same-origin'
							: ''}"
						on:load={iframeLoadHandler}
					></iframe>
				{:else if currentContent?.type === 'svg'}
					<SvgPanZoom
						className="w-full h-full max-h-full overflow-hidden"
						svg={currentContent.content}
					/>
				{/if}
			{:else}
				<!-- Code tab: CodeMirror editor (line numbers, editable, live preview) -->
				<div class="w-full h-full overflow-hidden" use:initEditor></div>
			{/if}
		{:else}
			<div class="flex items-center justify-center h-full">
				<div class="flex flex-col items-center gap-2 text-gray-400 dark:text-gray-600">
					<CodeBracket className="size-10 opacity-40" />
					<span class="text-sm font-medium">{$i18n.t('No HTML, CSS, or JavaScript content found.')}</span>
				</div>
			</div>
		{/if}
	</div>
</div>
