<script>
	import { toast } from 'svelte-sonner';
	import { config } from '$lib/stores';
	import Markdown from '$lib/components/chat/Messages/Markdown.svelte';
	import CodeBlock from '$lib/components/chat/Messages/CodeBlock.svelte';
	import Collapsible from '$lib/components/common/Collapsible.svelte';
	import LocalModelRuntimeToast from '$lib/components/chat/LocalModelRuntimeToast.svelte';
	let content = '```python\n' + Array.from({length: 48}, (_, i) => `print("Line ${i + 1}")`).join('\n') + '\n```';
	let streaming = false;
	let reasoning = {type: 'reasoning', done: 'true', duration: 5};
	let clicks = 0;
	let previews = 0;
</script>
<div class="bg-white dark:bg-black" style="height:100vh;overflow:auto;padding:70px 24px" id="fixture-scroll">
	<button id="navbar-hit" style="position:fixed;top:30px;right:30px;width:90px;height:16px" on:click={() => clicks++}>Models {clicks}</button>
	<div data-neve-toast style="position:fixed;top:28px;right:9px;z-index:1000000000"><LocalModelRuntimeToast name="Test model" /></div>
	<main class="markdown-prose" style="max-width:660px;margin:auto">
		<Markdown id="fixture-code" {content} done={!streaming} />
		<Collapsible id="fixture-reasoning" attributes={reasoning} open>
			<div slot="content"><p>The deploy log has three phases. Install takes 38s and next build takes 52s, both normal for this repo.</p><p>Image optimization takes 3m 50s. It reruns on every deploy because its cache key includes the commit hash, so the cache never hits.</p></div>
		</Collapsible>
		<CodeBlock id="fixture-edit" code={'print("Editable")\n'.repeat(45)} lang="python" />
		<CodeBlock id="fixture-long-edit" code={Array.from({length:1200},(_,i) => `print("Long line ${i}")`).join('\n')} lang="python" />
		<CodeBlock id="fixture-short" code="const value = 1;" lang="javascript" edit={false} />
		<div id="fixture-preview"><CodeBlock id="fixture-html" code="<h1>Preview</h1>" lang="html" edit={false} preview onPreview={() => previews++} /></div>
		<CodeBlock id="fixture-diagram" token={{raw:'```mermaid\ngraph TD; A-->B;\n```',text:'graph TD; A-->B;'}} code="graph TD; A-->B;" lang="mermaid" edit={false} />
		<CodeBlock id="fixture-wide-short" code={'const value = "' + 'a'.repeat(250) + '";'} lang="javascript" edit={false} />
		<CodeBlock id="fixture-wide" code={Array.from({length:40},()=> 'const value = "' + 'a'.repeat(250) + '";').join('\n')} lang="javascript" edit={false} />
		<div id="fixture-parsed"><Markdown id="parsed-reasoning" content={'<details type="reasoning" done="true" duration="5">\n<summary>Thought</summary>\n&gt; First paragraph.\n&gt;\n&gt; Second paragraph.\n</details>'} /></div>
		<Collapsible id="fixture-interpreter" attributes={{type:'code_interpreter',done:'true'}} open><span slot="content">Interpreter content</span></Collapsible>
		<button id="append-code" on:click={() => {streaming = true; content = content.slice(0,-4) + '\nprint("New line")\n```';}}>Append</button>
		<button id="finish" on:click={() => {streaming = false; reasoning = {...reasoning, done:'true'};}}>Finish</button>
		<button id="stream-reasoning" on:click={() => reasoning = {...reasoning, done:'false'}}>Think</button>
		<button id="error-toast" on:click={() => toast.error('Test error', {duration:60000})}>Toast</button>
		<button id="mock-execution" on:click={() => config.update(c => ({...c,code:{...c?.code,engine:'jupyter'}}))}>Execution</button>
		<span id="preview-count">{previews}</span>
	</main>
</div>
