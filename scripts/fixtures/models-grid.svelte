<script lang="ts">
	import { onMount, setContext, tick } from 'svelte';
	import { get, writable } from 'svelte/store';
	import UnifiedModels from '$lib/components/chat/UnifiedModels.svelte';
	import Modal from '$lib/components/common/Modal.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import DownloadProgressToast from '$lib/components/chat/DownloadNeveModelsProgressToast.svelte';
	import { applyModelAvailability } from '$lib/stores/modelAvailability';
	import { models, mobile, neveDownloadToast } from '$lib/stores';
	setContext('i18n', writable({ language:'en-US', t:(text:string)=>text }));
	let show=false;
	const local=Array.from({length:14},(_,i)=>({id:`local/Model${i}`,filename:`Model${i}.gguf`,file_size:11000000000,file_size_human:'11.1 GB',is_loaded:i===0,loaded_at:100,n_ctx:8192,n_gpu_layers:-1,cache_type:'q8_0',mmproj_filename:'',speculative_decoding:'off',token_prediction:'off',context_shift:'off'}));
	const admin=local.map((model,i)=>({id:model.id,name:i===1?'Very long model name with quantization and many characters':`Neve model ${i}`,base_model_id:null,is_active:i!==2,meta:{}}));
	const preload={loaded:true,runtimeUpdatedAt:1,localModels:local,mmProjFiles:[],adminModels:admin,workspaceModels:admin,baseModels:admin,vramInfo:{available:true,total:17179869184,used:4294967296,free:12884901888,total_human:'16 GB',used_human:'4 GB',free_human:'12 GB',gpus:[],storage:{available:true,total:1000000000000,used:600000000000,free:400000000000}}};
	onMount(()=>{
		models.set(admin as any);mobile.set(innerWidth<768);
		(window as any).__gridFixture={local,admin,downloadToast:()=>get(neveDownloadToast),async open(){show=true;await tick();},async close(){show=false;await tick();},async state(value:any){applyModelAvailability(value);await tick();}};
		return()=>delete (window as any).__gridFixture;
	});
</script>
<button on:click={()=>show=true}>Open models</button>
<Tooltip content="Reference tooltip"><button type="button" id="reference-tooltip-button">Tooltip reference</button></Tooltip>
<Modal bind:show keepMounted animated={false} size="md" mobileFullscreen className="bg-white dark:bg-gray-900 rounded-xl w-[44rem]!">
	<UnifiedModels {show} {preload} />
</Modal>
{#if !show && $neveDownloadToast}
	<div class="fixed right-4 top-16 z-[1000000000]"><DownloadProgressToast {...$neveDownloadToast} /></div>
{/if}
