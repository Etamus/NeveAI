<script lang="ts">
    import { onMount, setContext, tick } from 'svelte';
    import { writable, get } from 'svelte/store';
    import { page } from '$app/stores';
    import { user, models, mobile } from '$lib/stores';
    import LoadSettings from '$lib/components/chat/ModelSelector/LocalModelLoadSettings.svelte';
    import UnifiedModels from '$lib/components/chat/UnifiedModels.svelte';
    import Modal from '$lib/components/common/Modal.svelte';
    setContext('i18n',writable({language:'pt-BR',t:(text:string)=>text}));
    let show=false;
    onMount(()=>{
        mobile.set(innerWidth<768);user.set({id:'gpu-test',role:'admin',name:'Test'} as any);
        models.set([{id:'local/Alpha',name:'Alpha',owned_by:'llamacpp'}] as any);
        (window as any).__gpuFixture={close:async()=>{show=false;await tick();},closed:()=>!get(page).state.neveMobileDialog};
        return ()=>{delete (window as any).__gpuFixture;};
    });
</script>
<main class="bg-white dark:bg-black min-h-screen p-4">
    <div class="max-w-sm rounded-lg bg-white dark:bg-gray-850 border border-gray-200 dark:border-gray-700">
        <LoadSettings />
    </div>
    <button id="open-models" on:click={()=>show=true}>Models</button>
    <Modal bind:show keepMounted animated={false} size="md"><UnifiedModels {show} /></Modal>
</main>
