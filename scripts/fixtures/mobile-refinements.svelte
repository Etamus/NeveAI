<script>
	import { onMount, tick } from 'svelte';
	import Modal from '$lib/components/common/Modal.svelte';
	import FileItemModal from '$lib/components/common/FileItemModal.svelte';
	import FolderModal from '$lib/components/layout/Sidebar/Folders/FolderModal.svelte';
	import Profile from '$lib/components/layout/Sidebar/EditProfileModal.svelte';
	import Memory from '$lib/components/chat/Settings/Personalization/AddMemoryModal.svelte';
	import Variables from '$lib/components/chat/MessageInput/InputVariablesModal.svelte';
	import ToolServers from '$lib/components/chat/ToolServersModal.svelte';
	import CodeExecution from '$lib/components/chat/Messages/CodeExecutionModal.svelte';
	import ConfirmDialog from '$lib/components/common/ConfirmDialog.svelte';
	import ModelEditor from '$lib/components/workspace/Models/ModelEditor.svelte';
	import ImageEditor from '$lib/components/chat/MessageInput/ImageModeEditor.svelte';
	import Settings from '$lib/components/chat/SettingsModal.svelte';
	import Search from '$lib/components/layout/SearchModal.svelte';
	import UnifiedModels from '$lib/components/chat/UnifiedModels.svelte';
	import Download from '$lib/components/chat/DownloadNeveModelsModal.svelte';
	import VideoPreview from '$lib/components/chat/Messages/GeneratedVideoPreview.svelte';
	import ModelSettingsSheet from '$lib/components/chat/ModelSettingsSheet.svelte';
	import { imageModeDefaults } from '$lib/utils/imageModes';
	import { theme, showModelSettings } from '$lib/stores';
	let kind='',show=false,item=null,options=imageModeDefaults();
	let model={id:'local/test-model',name:'Example model',meta:{description:'A description aligned with the model name.',default_feature_ids:['web_search']},params:{temperature:0.7}};
	onMount(()=>{
		const unsubscribe=showModelSettings.subscribe(value=>{if(kind==='parameters')show=value;});
		window.__mobileRefinements={async open(value,dark){show=false;kind='';await tick();kind=value;theme.set(dark?'dark':'light');document.documentElement.classList.toggle('dark',dark);options=imageModeDefaults(value==='outpaint'?'outpaint':'inpaint');if(value.startsWith('file-')){const extension=value.slice(5);item={id:'fixture-'+extension,type:'file',name:'Example.'+extension,size:123456,meta:{content_type:{png:'image/png',mp4:'video/mp4',wav:'audio/wav',pdf:'application/pdf',txt:'text/plain'}[extension]}};}await tick();show=true;},state:()=>({show,kind})};
		window.__mobileParameters=()=>showModelSettings.set(true);
		return()=>{unsubscribe();delete window.__mobileRefinements;delete window.__mobileParameters;};
	});
</script>
{#if kind.startsWith('file-')}<FileItemModal bind:show {item} />
{:else if kind==='project'}<FolderModal bind:show />
{:else if kind==='profile'}<Profile bind:show />
{:else if kind==='memory'}<Memory bind:show />
{:else if kind==='variables'||kind==='variables-populated'}<Variables bind:show variables={kind==='variables-populated'?{name:{type:'text',default:'Example'}}:{}} />
{:else if kind==='tools'}<ToolServers bind:show />
{:else if kind==='code'}<CodeExecution bind:show codeExecution={{name:'Example',code:'print(1)',result:{output:'1'}}} />
{:else if kind==='confirm'}<ConfirmDialog bind:show title="Confirmation" message="No action will be executed." />
{:else if kind==='model'}<Modal bind:show mobileFullscreen><div style="height:100%;min-height:0"><ModelEditor {model} edit preset={false} onSubmit={()=>{}} onBack={()=>show=false} /></div></Modal>
{:else if kind==='inpaint'||kind==='outpaint'}<ImageEditor bind:show bind:options files={[{id:'fixture-png',type:'image',url:'/api/v1/files/fixture-png/content',status:'uploaded'}]} />
{:else if kind==='settings'}<Settings bind:show />
{:else if kind==='search'}<Search bind:show />
{:else if kind==='unified'}<Modal bind:show mobileFullscreen><UnifiedModels {show} /></Modal>
{:else if kind==='download'}<Download bind:show />
{:else if kind==='video-preview'}<VideoPreview bind:show src="/api/v1/files/fixture-mp4/content" />
{:else if kind==='parameters'}<ModelSettingsSheet selectedModelName="Example model" params={{temperature:0.7}} />
{/if}
