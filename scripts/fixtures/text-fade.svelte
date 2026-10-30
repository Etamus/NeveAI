<script>
	import { onMount } from 'svelte';
	import TextToken from '$lib/components/chat/Messages/Markdown/MarkdownInlineTokens/TextToken.svelte';
	let text = '';
	let done = false;
	let mounted = true;
	onMount(()=>{
		window.__fadeProbe=(next,finished=false,show=true)=>{text=next;done=finished;mounted=show;};
		return()=>delete window.__fadeProbe;
	});
</script>
<div id="probe" style="margin:30px;background:black;color:rgb(240,240,240);font:24px sans-serif;padding:20px;width:300px;height:100px">
	{#if mounted}<TextToken token={{raw:text}} {done} />{/if}
</div>
