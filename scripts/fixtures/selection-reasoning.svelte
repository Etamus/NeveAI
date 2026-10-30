<script>
	import {setContext,onMount} from 'svelte';
	import {models, settings} from '$lib/stores';
	import ContentRenderer from '$lib/components/chat/Messages/ContentRenderer.svelte';
	let model={id:'local/selection-test',name:'Selection test'};
	let added=null;
	const params={temperature:0.7,reasoning_mode:'reasoning',reasoning_extended:true,reasoning_unlimited:true};
	setContext('prepare-text-model',async id=>{window.__selectionPrepared.push(id);return {params:structuredClone(params)};});
	onMount(()=>{
		window.__selectionPrepared=[];
		window.__selectionSetModel=next=>{model=next;models.set([next]);};
		models.set([model]);settings.update(s=>({...s,expandDetails:false,floatingActionButtons:[]}));
		return()=>{delete window.__selectionPrepared;delete window.__selectionSetModel;};
	});
</script>

<main class="bg-white dark:bg-black" style="height:100vh;padding:80px 24px">
	<ContentRenderer id="selection-reasoning" content="Select this sentence to ask or explain." history={{messages:{}}} messageId="selection-parent" {model} selectedModels={[model.id]} onAddMessages={value=>added=value} />
	<pre id="selection-added">{JSON.stringify(added)}</pre>
</main>
