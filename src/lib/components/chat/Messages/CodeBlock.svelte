<script lang="ts">
	import hljs from 'highlight.js';
	import { toast } from 'svelte-sonner';
	import { getContext, onMount, tick, onDestroy } from 'svelte';
	import { config } from '$lib/stores';

	import PyodideWorker from '$lib/workers/pyodide.worker?worker';
	import { executeCode } from '$lib/apis/utils';
	import {
		copyToClipboard,
		initMermaid,
		renderMermaidDiagram,
		renderVegaVisualization
	} from '$lib/utils';

	import 'highlight.js/styles/github-dark.min.css';

	import CodeEditor from '$lib/components/common/CodeEditor.svelte';
	import SvgPanZoom from '$lib/components/common/SVGPanZoom.svelte';

	import ChevronUp from '$lib/components/icons/ChevronUp.svelte';
	import ChevronUpDown from '$lib/components/icons/ChevronUpDown.svelte';
	import CommandLine from '$lib/components/icons/CommandLine.svelte';
	import Cube from '$lib/components/icons/Cube.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';

	const i18n = getContext('i18n');

	export let id = '';
	export let edit = true;

	export let onSave = (e) => {};
	export let onUpdate = (e) => {};
	export let onPreview = (e) => {};

	export let save = false;
	export let run = true;
	export let preview = false;
	export let collapsed = false;
	export let hideToolbar = false;

	export let token;
	export let lang = '';
	export let code = '';
	export let attributes = {};

	export let className = '';
	export let editorClassName = '';
	export let stickyButtonsClassName = 'top-0';

	$: isReasoningCodeBlock = hideToolbar || attributes?.type === 'reasoning';

	let pyodideWorker = null;

	let _code = '';
	$: if (code) {
		updateCode();
	}

	const updateCode = () => {
		_code = code;
	};

	let _token = null;

	let renderHTML = null;
	let renderError = null;

	let highlightedCode = null;
	let executing = false;

	let stdout = null;
	let stderr = null;
	let result = null;
	let files = null;

	let copied = false;
	let saved = false;

	const collapseCodeBlock = () => {
		collapsed = !collapsed;
	};

	const saveCode = () => {
		saved = true;

		code = _code;
		onSave(code);

		setTimeout(() => {
			saved = false;
		}, 1000);
	};

	const copyCode = async () => {
		copied = true;
		await copyToClipboard(_code);

		setTimeout(() => {
			copied = false;
		}, 1000);
	};

	const previewCode = () => {
		onPreview(code);
	};

	const checkPythonCode = (str) => {
		// Check if the string contains typical Python syntax characters
		const pythonSyntax = [
			'def ',
			'else:',
			'elif ',
			'try:',
			'except:',
			'finally:',
			'yield ',
			'lambda ',
			'assert ',
			'nonlocal ',
			'del ',
			'True',
			'False',
			'None',
			' and ',
			' or ',
			' not ',
			' in ',
			' is ',
			' with '
		];

		for (let syntax of pythonSyntax) {
			if (str.includes(syntax)) {
				return true;
			}
		}

		// If none of the above conditions met, it's probably not Python code
		return false;
	};

	const executePython = async (code) => {
		result = null;
		stdout = null;
		stderr = null;

		executing = true;

		if ($config?.code?.engine === 'jupyter') {
			const output = await executeCode(localStorage.token, code).catch((error) => {
				toast.error(`${error}`);
				return null;
			});

			if (output) {
				if (output['stdout']) {
					stdout = output['stdout'];
					const stdoutLines = stdout.split('\n');

					for (const [idx, line] of stdoutLines.entries()) {
						if (line.startsWith('data:image/png;base64')) {
							if (files) {
								files.push({
									type: 'image/png',
									data: line
								});
							} else {
								files = [
									{
										type: 'image/png',
										data: line
									}
								];
							}

							if (stdout.includes(`${line}\n`)) {
								stdout = stdout.replace(`${line}\n`, ``);
							} else if (stdout.includes(`${line}`)) {
								stdout = stdout.replace(`${line}`, ``);
							}
						}
					}
				}

				if (output['result']) {
					result = output['result'];
					const resultLines = result.split('\n');

					for (const [idx, line] of resultLines.entries()) {
						if (line.startsWith('data:image/png;base64')) {
							if (files) {
								files.push({
									type: 'image/png',
									data: line
								});
							} else {
								files = [
									{
										type: 'image/png',
										data: line
									}
								];
							}

							if (result.includes(`${line}\n`)) {
								result = result.replace(`${line}\n`, ``);
							} else if (result.includes(`${line}`)) {
								result = result.replace(`${line}`, ``);
							}
						}
					}
				}

				output['stderr'] && (stderr = output['stderr']);
			}

			executing = false;
		} else {
			executePythonAsWorker(code);
		}
	};

	const executePythonAsWorker = async (code) => {
		let packages = [
			/\bimport\s+requests\b|\bfrom\s+requests\b/.test(code) ? 'requests' : null,
			/\bimport\s+bs4\b|\bfrom\s+bs4\b/.test(code) ? 'beautifulsoup4' : null,
			/\bimport\s+numpy\b|\bfrom\s+numpy\b/.test(code) ? 'numpy' : null,
			/\bimport\s+pandas\b|\bfrom\s+pandas\b/.test(code) ? 'pandas' : null,
			/\bimport\s+matplotlib\b|\bfrom\s+matplotlib\b/.test(code) ? 'matplotlib' : null,
			/\bimport\s+seaborn\b|\bfrom\s+seaborn\b/.test(code) ? 'seaborn' : null,
			/\bimport\s+sklearn\b|\bfrom\s+sklearn\b/.test(code) ? 'scikit-learn' : null,
			/\bimport\s+scipy\b|\bfrom\s+scipy\b/.test(code) ? 'scipy' : null,
			/\bimport\s+re\b|\bfrom\s+re\b/.test(code) ? 'regex' : null,
			/\bimport\s+seaborn\b|\bfrom\s+seaborn\b/.test(code) ? 'seaborn' : null,
			/\bimport\s+sympy\b|\bfrom\s+sympy\b/.test(code) ? 'sympy' : null,
			/\bimport\s+tiktoken\b|\bfrom\s+tiktoken\b/.test(code) ? 'tiktoken' : null,
			/\bimport\s+pytz\b|\bfrom\s+pytz\b/.test(code) ? 'pytz' : null
		].filter(Boolean);

		console.log(packages);

		pyodideWorker = new PyodideWorker();

		pyodideWorker.postMessage({
			id: id,
			code: code,
			packages: packages
		});

		setTimeout(() => {
			if (executing) {
				executing = false;
				stderr = 'Execution Time Limit Exceeded';
				pyodideWorker.terminate();
			}
		}, 60000);

		pyodideWorker.onmessage = (event) => {
			console.log('pyodideWorker.onmessage', event);
			const { id, ...data } = event.data;

			console.log(id, data);

			if (data['stdout']) {
				stdout = data['stdout'];
				const stdoutLines = stdout.split('\n');

				for (const [idx, line] of stdoutLines.entries()) {
					if (line.startsWith('data:image/png;base64')) {
						if (files) {
							files.push({
								type: 'image/png',
								data: line
							});
						} else {
							files = [
								{
									type: 'image/png',
									data: line
								}
							];
						}

						if (stdout.includes(`${line}\n`)) {
							stdout = stdout.replace(`${line}\n`, ``);
						} else if (stdout.includes(`${line}`)) {
							stdout = stdout.replace(`${line}`, ``);
						}
					}
				}
			}

			if (data['result']) {
				result = data['result'];
				const resultLines = result.split('\n');

				for (const [idx, line] of resultLines.entries()) {
					if (line.startsWith('data:image/png;base64')) {
						if (files) {
							files.push({
								type: 'image/png',
								data: line
							});
						} else {
							files = [
								{
									type: 'image/png',
									data: line
								}
							];
						}

						if (result.startsWith(`${line}\n`)) {
							result = result.replace(`${line}\n`, ``);
						} else if (result.startsWith(`${line}`)) {
							result = result.replace(`${line}`, ``);
						}
					}
				}
			}

			data['stderr'] && (stderr = data['stderr']);
			data['result'] && (result = data['result']);

			executing = false;
		};

		pyodideWorker.onerror = (event) => {
			console.log('pyodideWorker.onerror', event);
			executing = false;
		};
	};

	let mermaid = null;
	const renderMermaid = async (code) => {
		if (!mermaid) {
			mermaid = await initMermaid();
		}
		return await renderMermaidDiagram(mermaid, code);
	};

	const render = async () => {
		onUpdate(token);
		if (lang === 'mermaid' && (token?.raw ?? '').slice(-4).includes('```')) {
			try {
				renderHTML = await renderMermaid(code);
			} catch (error) {
				console.error('Failed to render mermaid diagram:', error);
				const errorMsg = error instanceof Error ? error.message : String(error);
				renderError = $i18n.t('Failed to render diagram') + `: ${errorMsg}`;
				renderHTML = null;
			}
		} else if (
			(lang === 'vega' || lang === 'vega-lite') &&
			(token?.raw ?? '').slice(-4).includes('```')
		) {
			try {
				renderHTML = await renderVegaVisualization(code);
			} catch (error) {
				console.error('Failed to render Vega visualization:', error);
				const errorMsg = error instanceof Error ? error.message : String(error);
				renderError = $i18n.t('Failed to render visualization') + `: ${errorMsg}`;
				renderHTML = null;
			}
		}
	};

	$: if (token) {
		if (token.text !== _token?.text || token.raw !== _token?.raw) {
			_token = token;
		} else if (JSON.stringify(token) !== JSON.stringify(_token)) {
			_token = token;
		}
	}

	$: if (_token) {
		render();
	}

	$: if (attributes) {
		onAttributesUpdate();
	}

	const onAttributesUpdate = () => {
		if (attributes?.output) {
			// Create a helper function to unescape HTML entities
			const unescapeHtml = (html) => {
				const textArea = document.createElement('textarea');
				textArea.innerHTML = html;
				return textArea.value;
			};

			try {
				// Unescape the HTML-encoded string
				const unescapedOutput = unescapeHtml(attributes.output);

				// Parse the unescaped string into JSON
				const output = JSON.parse(unescapedOutput);

				// Assign the parsed values to variables
				stdout = output.stdout;
				stderr = output.stderr;
				result = output.result;
			} catch (error) {
				console.error('Error:', error);
			}
		}
	};

	onMount(async () => {
		if (token) {
			onUpdate(token);
		}
	});

	onDestroy(() => {
		if (pyodideWorker) {
			pyodideWorker.terminate();
		}
	});
</script>

<div>
	<div
		class="relative {className} flex flex-col rounded-lg border border-gray-200/50 dark:border-gray-700/40 my-0.5"
		dir="ltr"
	>
		{#if ['mermaid', 'vega', 'vega-lite'].includes(lang)}
			{#if renderHTML}
				<SvgPanZoom
					className=" rounded-lg max-h-fit overflow-hidden"
					svg={renderHTML}
					content={_token.text}
				/>
			{:else}
				<div class="p-3">
					{#if renderError}
						<div
							class="flex gap-2.5 border px-4 py-3 border-red-600/10 bg-red-600/10 rounded-lg mb-2"
						>
							{renderError}
						</div>
					{/if}
					<pre>{code}</pre>
				</div>
			{/if}
		{:else}
			{#if !isReasoningCodeBlock}
			<div
				class="sticky {stickyButtonsClassName} left-0 right-0 py-1.5 px-3 gap-2 flex items-center justify-end w-full z-10 text-xs text-gray-500 dark:text-gray-400 bg-gray-50 dark:bg-[#2a2a2a] rounded-t-lg border-b border-gray-200/50 dark:border-gray-700/40"
			>
				<div class="flex-1 truncate">
					<Tooltip content={lang} placement="top-start">
						<span class=" truncate text-ellipsis">
							{lang}
						</span>
					</Tooltip>
				</div>

				<div class="flex items-center gap-0.5 shrink-0">
					{#if ($config?.features?.enable_code_execution ?? true) && (lang.toLowerCase() === 'python' || lang.toLowerCase() === 'py' || (lang === '' && checkPythonCode(code)))}
						{#if executing}
							<div
								class="run-code-button bg-none border-none p-1 cursor-not-allowed"
							>
								<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="size-4 animate-spin"><path fill-rule="evenodd" d="M15.312 11.424a5.5 5.5 0 01-9.201 2.466l-.312-.311h2.433a.75.75 0 000-1.5H4.598a.75.75 0 00-.75.75v3.634a.75.75 0 001.5 0v-2.033l.312.311a7 7 0 0011.712-3.138.75.75 0 00-1.449-.389zm-11.023-3.848a.75.75 0 00.726.947h.008a.75.75 0 00.722-.953 5.5 5.5 0 019.2-2.467l.312.311H12.82a.75.75 0 000 1.5h3.634a.75.75 0 00.75-.75V2.53a.75.75 0 00-1.5 0v2.034l-.312-.312A7 7 0 003.68 7.387a.75.75 0 00.609.189z" clip-rule="evenodd" /></svg>
							</div>
						{:else if run}
							<Tooltip content={$i18n.t('Run')} placement="top">
								<button
									class="flex items-center justify-center run-code-button bg-none border-none transition rounded-md p-1 hover:bg-gray-200 dark:hover:bg-gray-700"
									on:click={async () => {
										code = _code;
										await tick();
										executePython(code);
									}}
								>
								<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" class="size-4"><path stroke-linecap="round" stroke-linejoin="round" d="M5.25 5.653c0-.856.917-1.398 1.667-.986l11.54 6.347a1.125 1.125 0 0 1 0 1.972l-11.54 6.347a1.125 1.125 0 0 1-1.667-.986V5.653Z" /></svg>
								</button>
							</Tooltip>
						{/if}
					{/if}

					<Tooltip content={copied ? $i18n.t('Copied') : $i18n.t('Copy')} placement="top">
						<button
							class="copy-code-button flex items-center justify-center bg-none border-none transition rounded-md p-1 hover:bg-gray-200 dark:hover:bg-gray-700"
							on:click={copyCode}
						>
							{#if copied}
								<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" class="size-4"><path stroke-linecap="round" stroke-linejoin="round" d="M4.5 12.75l6 6 9-13.5" /></svg>
							{:else}
								<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" class="size-4"><path stroke-linecap="round" stroke-linejoin="round" d="M15.666 3.888A2.25 2.25 0 0 0 13.5 2.25h-3c-1.03 0-1.9.693-2.166 1.638m7.332 0c.055.194.084.4.084.612v0a.75.75 0 0 1-.75.75H9.75a.75.75 0 0 1-.75-.75v0c0-.212.03-.418.084-.612m7.332 0c.646.049 1.288.11 1.927.184 1.1.128 1.907 1.077 1.907 2.185V19.5a2.25 2.25 0 0 1-2.25 2.25H6.75A2.25 2.25 0 0 1 4.5 19.5V6.257c0-1.108.806-2.057 1.907-2.185a48.208 48.208 0 0 1 1.927-.184" /></svg>
							{/if}
						</button>
					</Tooltip>

					<Tooltip content={$i18n.t('Download')} placement="top">
						<button
							class="flex items-center justify-center bg-none border-none transition rounded-md p-1 hover:bg-gray-200 dark:hover:bg-gray-700"
							on:click={() => {
								const ext = lang || 'txt';
								const blob = new Blob([code], { type: 'text/plain' });
								const url = URL.createObjectURL(blob);
								const a = document.createElement('a');
								a.href = url;
								a.download = `code.${ext}`;
								a.click();
								URL.revokeObjectURL(url);
							}}
						>
							<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" class="size-4"><path stroke-linecap="round" stroke-linejoin="round" d="M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2M7 11l5 5 5-5M12 4v12"/></svg>
						</button>
					</Tooltip>

					{#if preview && ['html', 'svg'].includes(lang)}
						<Tooltip content={$i18n.t('Preview')} placement="top">
							<button
								class="flex items-center justify-center run-code-button bg-none border-none transition rounded-md p-1 hover:bg-gray-200 dark:hover:bg-gray-700"
								on:click={previewCode}
							>
								<Cube className="size-4" />
							</button>
						</Tooltip>
					{/if}
				</div>
			</div>
			{/if}

			<div
				class="language-{lang} {editorClassName
					? editorClassName
					: executing || stdout || stderr || result
						? ''
						: 'rounded-b-lg'} overflow-hidden"
			>
				<div class="bg-gray-50 dark:bg-[#1a1a1a]"></div>

				{#if !collapsed}
					{#if edit}
						<CodeEditor
							value={code}
							{id}
							{lang}
							onSave={() => {
								saveCode();
							}}
							onChange={(value) => {
								_code = value;
							}}
						/>
					{:else}
						<pre
							class=" hljs p-4 px-5 overflow-x-auto"
					style="{!isReasoningCodeBlock
						? 'border-top-left-radius: 0px; border-top-right-radius: 0px;'
						: ''} {(executing ||
						stdout ||
						stderr ||
						result) &&
						'border-bottom-left-radius: 0px; border-bottom-right-radius: 0px;'}"><code
						class="language-{lang} rounded-t-none whitespace-pre text-sm"
								>{@html hljs.highlightAuto(code, hljs.getLanguage(lang)?.aliases).value ||
									code}</code
							></pre>
					{/if}
				{:else}
					<div
						class="bg-gray-50 dark:bg-[#1a1a1a] dark:text-white rounded-b-lg! pt-0.5 pb-2 px-4 flex flex-col gap-2 text-xs"
					>
						<span class="text-gray-500 italic">
							{$i18n.t('{{COUNT}} hidden lines', {
								COUNT: code.split('\n').length
							})}
						</span>
					</div>
				{/if}
			</div>

			{#if !collapsed}
				<div
					id="plt-canvas-{id}"
					class="bg-gray-50 dark:bg-[#1a1a1a] dark:text-white max-w-full overflow-x-auto scrollbar-hidden"
				/>

				{#if executing || stdout || stderr || result || files}
					<div
						class="bg-gray-50 dark:bg-[#1a1a1a] dark:text-white rounded-b-lg! py-4 px-4 flex flex-col gap-2"
					>
						{#if executing}
							<div class=" ">
								<div class=" text-gray-500 text-sm mb-1">{$i18n.t('STDOUT/STDERR')}</div>
								<div class="text-sm">{$i18n.t('Running...')}</div>
							</div>
						{:else}
							{#if stdout || stderr}
								<div class=" ">
									<div class=" text-gray-500 text-sm mb-1">{$i18n.t('STDOUT/STDERR')}</div>
									<div
										class="text-sm font-mono whitespace-pre-wrap {stdout?.split('\n')?.length > 100
											? `max-h-96`
											: ''}  overflow-y-auto"
									>
										{stdout || stderr}
									</div>
								</div>
							{/if}
							{#if result || files}
								<div class=" ">
									<div class=" text-gray-500 text-sm mb-1">{$i18n.t('RESULT')}</div>
									{#if result}
										<div class="text-sm">{`${JSON.stringify(result)}`}</div>
									{/if}
									{#if files}
										<div class="flex flex-col gap-2">
											{#each files as file}
												{#if file.type.startsWith('image')}
													<img src={file.data} alt="Output" class=" w-full max-w-[36rem]" />
												{/if}
											{/each}
										</div>
									{/if}
								</div>
							{/if}
						{/if}
					</div>
				{/if}
			{/if}
		{/if}
	</div>
</div>
