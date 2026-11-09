<script lang="ts">
    import { onMount, setContext, tick } from 'svelte';
    import { writable } from 'svelte/store';
    import { mobile, user, models, pinnedChats } from '$lib/stores';
    import Markdown from '$lib/components/chat/Messages/Markdown.svelte';
    import MessageInput from '$lib/components/chat/MessageInput.svelte';
    import ChatItem from '$lib/components/layout/Sidebar/ChatItem.svelte';
    import RecursiveFolder from '$lib/components/layout/Sidebar/RecursiveFolder.svelte';
    setContext('i18n', writable({language:'pt-BR',t:(text:string)=>text}));
    let history:any = {currentId:'active', messages:{
        old:{role:'assistant',done:true,usage:{total_tokens:120,tokens_per_second:50}},
        active:{role:'assistant',done:false,parentId:'old',context_window:8192}
    }};
    let stableDiffusionEnabled=false, videoGenerationEnabled=false, musicGenerationEnabled=false;
    const folders = {project:{id:'project',name:'Projeto de exemplo',items:[],children:[],meta:{}}};
    onMount(() => {
        mobile.set(innerWidth<768);
        user.set({id:'layout',name:'Test',role:'admin'} as any);
        models.set([{id:'local/test',name:'Test'}] as any);
        pinnedChats.set([{id:'pinned',title:'Conversa fixada'}] as any);
        (window as any).__metrics = {
            async update(usage:any,done=false) {history={...history,messages:{...history.messages,active:{...history.messages.active,usage,done}}};await tick();},
            async setHistory(value:any) {history=value;await tick();},
            async integration(kind:string) {stableDiffusionEnabled=kind==='image';videoGenerationEnabled=kind==='video';musicGenerationEnabled=kind==='music';await tick();},
        };
        return () => {delete (window as any).__metrics;};
    });
</script>
<div class="bg-white dark:bg-black" style="min-height:100vh;padding:24px">
    <div id="sidebar" style="width:276px" class="text-sm">
        <ChatItem id="regular" title="Conversa de exemplo" />
        <ChatItem id="pinned" title="Conversa fixada" />
        <RecursiveFolder {folders} folderId="project" />
    </div>
    <div class="markdown-prose" style="margin:32px 0;max-width:750px" id="fixture-markdown">
        <Markdown id="metrics-heading" content={'# LÉXIS — Landing Page\n\nTexto normal, **negrito**, *itálico*.\n\n## Segundo título\n\n### Terceiro título'} />
    </div>
    <MessageInput {history} bind:stableDiffusionEnabled bind:videoGenerationEnabled bind:musicGenerationEnabled selectedModels={['local/test']} />
</div>
