<script>
	import Modal from '$lib/components/common/Modal.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import SourceToken from '$lib/components/chat/Messages/Markdown/SourceToken.svelte';
	import ContentRenderer from '$lib/components/chat/Messages/ContentRenderer.svelte';
	let show = false;
</script>
<div id="messages-container" style="contain:paint;overflow:auto;position:relative;height:350px;margin:80px 24px;padding:20px">
	<ContentRenderer id="paint-selection" content="Select this sentence to open the selection menu." history={{messages:{}}} messageId="paint-message" />
	<button id="open-preview" on:click={() => show=true}>Preview</button>
	<Tooltip content="Paint test tooltip"><button id="test-tooltip">Tooltip</button></Tooltip>
	<div style="height:250px"></div>
	<SourceToken id="paint-sources" token={{ids:[1,2]}} sourceIds={['https://example.com/a','https://example.org/b']} />
	<div style="height:300px"></div>
	<Modal bind:show><div id="paint-dialog">Preview content<button on:click={() => show=false}>Close preview</button></div></Modal>
</div>
