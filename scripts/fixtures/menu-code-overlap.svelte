<script lang="ts">
    import { setContext, onMount } from 'svelte';
    import { writable } from 'svelte/store';
    import { mobile, user, tools } from '$lib/stores';
    import InputMenu from '$lib/components/chat/MessageInput/InputMenu.svelte';
    import CodeBlock from '$lib/components/chat/Messages/CodeBlock.svelte';
    setContext('i18n',writable({language:'pt-BR',t:(text:string)=>text}));
    onMount(()=>{mobile.set(innerWidth<768);tools.set([]);user.set({id:'overlap',role:'admin',name:'Test'} as any);});
</script>
<div class="min-h-screen bg-white dark:bg-black" style="height:100vh;overflow:hidden">
    <div id="under-code" class="markdown-prose" style="position:absolute;left:24px;top:250px;width:42vw;height:85vh;overflow:hidden">
        <CodeBlock id="overlap-code" lang="python" code={'print("A stable code block")\n'.repeat(90)} edit={false} />
        <CodeBlock id="overlap-short" lang="javascript" code={'const value = 1;\n'.repeat(5)} edit={false} />
    </div>
    <div id="message-input-container" class="bg-gray-100 dark:bg-gray-850 rounded-3xl" style="position:absolute;left:24px;bottom:24px;width:calc(100% - 48px);height:60px;padding:12px">
        <InputMenu above showWebSearchButton showLearningButton showStableDiffusionButton showVideoGenerationButton showMusicGenerationButton showFileGenerationButton selectedModels={[]} fileUploadCapableModels={[]} uploadFilesHandler={()=>{}} onUpload={()=>{}} onClose={()=>{}}>
            <button id="open-menu" aria-label="More" style="width:36px;height:36px">+</button>
        </InputMenu>
    </div>
</div>
