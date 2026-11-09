<script lang="ts">
    import { onMount, setContext, tick } from 'svelte';
    import { writable, get } from 'svelte/store';
    import { page } from '$app/stores';
    import Navbar from '$lib/components/chat/Navbar.svelte';
    import { user, models, mobile, showLocalModelsModal } from '$lib/stores';
    setContext('i18n', writable({language:'en-US',t:(text:string)=>text}));
    onMount(() => {
        user.set({id:'catalog-test',name:'Test',role:'admin'} as any);
        mobile.set(innerWidth<768);
        (window as any).__catalogFixture = {
            async open() { showLocalModelsModal.set(true); await tick(); },
            async close() { showLocalModelsModal.set(false); await tick(); },
            dialogOpen: () => Boolean(get(page).state.neveMobileDialog),
        };
        return () => { delete (window as any).__catalogFixture; showLocalModelsModal.set(false); };
    });
</script>
<Navbar initNewChat={()=>{}} history={{messages:{},currentId:null}} selectedModels={[]} showModelSelector={false} />
