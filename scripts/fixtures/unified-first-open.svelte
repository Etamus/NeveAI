<script lang="ts">
    import { onMount, setContext, tick } from 'svelte';
    import { get, writable } from 'svelte/store';
    import { page } from '$app/stores';
    import UnifiedModels from '$lib/components/chat/UnifiedModels.svelte';
    import Modal from '$lib/components/common/Modal.svelte';
    import { models, mobile } from '$lib/stores';
    import { applyModelAvailability } from '$lib/stores/modelAvailability';
    setContext('i18n', writable({language:'en-US',t:(text:string)=>text}));
    let mounted = false;
    let show = false;
    let preload = null;
    const local = [{id:'local/Alpha',filename:'Alpha.gguf',file_size:1000000000,
        file_size_human:'1 GB',is_loaded:false,n_ctx:8192,n_gpu_layers:-1}];
    const admin = [{id:'local/Alpha',name:'Alpha custom name',owned_by:'llamacpp',is_active:true,meta:{}}];
    onMount(() => {
        mobile.set(innerWidth<768);
        models.set(admin as any);
        applyModelAvailability({epoch:'first-open-test',revision:0,busy:false,loaded_models:[]});
        (window as any).__firstOpen = {
            async open(ready:boolean, empty=false) {
                mounted=false; show=false; await tick();
                models.set(empty ? [] : admin as any);
                preload=ready ? {loaded:true,runtimeUpdatedAt:Date.now(),localModels:local,mmProjFiles:[],
                    adminModels:admin,workspaceModels:admin,baseModels:admin,vramInfo:null} : null;
                mounted=true; show=true; await tick();
            },
            async close() { mounted=false; show=false; await tick(); },
            dialogOpen: () => Boolean(get(page).state.neveMobileDialog),
            local,admin
        };
        return () => { delete (window as any).__firstOpen; };
    });
</script>
<Modal bind:show mobileFullscreen keepMounted animated={false} size="md">
    {#if mounted}
        <UnifiedModels {preload} {show} />
    {/if}
</Modal>
