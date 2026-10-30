<script>
	import { onMount } from 'svelte';
	import Markdown from '$lib/components/chat/Messages/Markdown.svelte';
	import StatusItem from '$lib/components/chat/Messages/ResponseMessage/StatusHistory/StatusItem.svelte';
	import StatusHistory from '$lib/components/chat/Messages/ResponseMessage/StatusHistory.svelte';
	import ToolCallDisplay from '$lib/components/common/ToolCallDisplay.svelte';
	import Collapsible from '$lib/components/common/Collapsible.svelte';
	let content='Stable introduction.\n\n';
	let done=false;
	onMount(()=>{
		window.__streamingToolsReady=true;
		const listener=event=>{content=event.detail.content;done=event.detail.done??false;};
		window.addEventListener('neve-test-stream',listener);
		return()=>{window.removeEventListener('neve-test-stream',listener);delete window.__streamingToolsReady;};
	});
	const sources=Array.from({length:11},(_,i)=>({link:`https://example.com/${i}`,title:`Source ${i}`}));
	const statuses=[
		{action:'sources_retrieved',description:'Retrieved 2 sources',count:2,source_type:'file',done:true},
		{action:'web_search',description:'Searched 11 sites',items:sources,done:true},
		{action:'web_search',description:'Deep research',items:sources,deep_search:true,done:true},
		{action:'file_generation',description:'Creating document',done:true},
		{action:'stable_diffusion',description:'Editing image',done:false},
		{action:'video_generation',description:'Creating video',done:false},
		{action:'music_generation',description:'Creating music',done:false}
	];
</script>
<div id="tools-fixture" class="bg-white dark:bg-black text-gray-900 dark:text-gray-100" style="height:100vh;overflow:auto;scrollbar-gutter:stable both-edges;padding:30px 20px">
	<main class="markdown-prose" style="max-width:720px;margin:auto">
		<div id="stream"><Markdown id="stable-stream" {content} {done} /></div>
		{#each statuses as status,i}
			<div id={`status-${i}`} style="margin-top:12px"><StatusHistory statusHistory={[status]} /></div>
		{/each}
		<div id="history"><StatusHistory statusHistory={[{action:'web_search_queries_generated',queries:['first','second'],description:'Searching',done:true},statuses[0]]} /></div>
		<div id="tool"><ToolCallDisplay attributes={{name:'Document tool',arguments:'{"text":"sample"}',result:'{"result":"Verified output"}',done:'true'}} /></div>
		<div id="tool-running"><ToolCallDisplay attributes={{name:'Running tool',arguments:'{"text":"sample"}',done:'false'}} /></div>
		<div id="tool-embed"><ToolCallDisplay attributes={{name:'Embedded tool',embeds:'["http://localhost:5188/__tool_embed"]',done:'true'}} /></div>
		<div id="interpreter"><Collapsible attributes={{type:'code_interpreter',done:'true'}} open><div slot="content">Interpreter result</div></Collapsible></div>
		<div id="reasoning"><Collapsible attributes={{type:'reasoning',done:'true',duration:5}} open><div slot="content">Reasoning result</div></Collapsible></div>
	</main>
</div>
