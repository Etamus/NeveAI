<script>
	import { onMount, tick } from 'svelte';
	import Markdown from '$lib/components/chat/Messages/Markdown.svelte';
	import StatusHistory from '$lib/components/chat/Messages/ResponseMessage/StatusHistory.svelte';
	import CitationModal from '$lib/components/chat/Messages/Citations/CitationModal.svelte';
	let content = 'Intro.';
	let done = false;
	let history = [{ action: 'sources_retrieved', count: 1, done: true }];
	let showCitation = false;
	const defaultCitation = () => ({ source: { name: 'Texto colado.txt' }, document: ['Conteudo da fonte.\n\n'.repeat(150)] });
	let citation = defaultCitation();
	onMount(() => {
		window.sourceStreamTest = {
			async text(value, complete = false) { content = value; done = complete; await tick(); },
			async status(value) { history = value; await tick(); },
			async citation(value) { citation = value ?? defaultCitation(); showCitation = true; await tick(); }
		};
		return () => { delete window.sourceStreamTest; };
	});
</script>

<main class="bg-white dark:bg-black min-h-screen p-6 text-gray-900 dark:text-gray-100">
	<div style="max-width:700px;margin:auto">
		<div id="status"><StatusHistory statusHistory={history} /></div>
		<div id="answer" class="markdown-prose"><Markdown id="source-stream" {content} {done} /></div>
		<div id="inline" class="markdown-prose"><Markdown id="inline-code" content={'Use `CASE WHEN ... ELSE 0 END` na consulta.'} /></div>
		<div id="scroll-reference" style="height:30px;overflow:auto"><div style="height:100px">Reference</div></div>
	</div>
</main>
<CitationModal bind:show={showCitation} {citation} />
