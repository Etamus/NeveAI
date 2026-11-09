<script lang="ts">
 import {setContext,onMount} from 'svelte';
 import {writable} from 'svelte/store';
 import {page} from '$app/stores';
 import {showArtifacts,mobile,user,tools} from '$lib/stores';
 import ArtifactCards from '$lib/components/chat/Messages/ArtifactCards.svelte';
 import Artifacts from '$lib/components/chat/Artifacts.svelte';
 import ContentRenderer from '$lib/components/chat/Messages/ContentRenderer.svelte';
 import InputMenu from '$lib/components/chat/MessageInput/InputMenu.svelte';
 import DefaultFeatures from '$lib/components/workspace/Models/DefaultFeatures.svelte';
 import ptBR from '$lib/i18n/locales/pt-BR/translation.json';
 import enUS from '$lib/i18n/locales/en-US/translation.json';
 const language = $page.url.searchParams.get('lang') ?? 'en-US';
 const translations = language === 'pt-BR' ? ptBR : enUS;
 setContext('i18n',writable({language,t:(text:string)=>translations[text] || text}));
 let done=false;
 let learningEnabled=false;
 let fileGenerationEnabled=false;
 let featureIds=['web_search','guided_learning'];
 const content='```html\n<h1 id="demo">First artifact</h1>\n```\n```css\nh1 { color: red; }\n```';
 const second='<html lang="en"><head></head><body><h1>Second artifact</h1></body></html>';
 $: history={currentId:'b',messages:{a:{id:'a',role:'assistant',parentId:null,content,done},b:{id:'b',role:'assistant',parentId:'a',content:second,done:true}}};
 onMount(()=>{showArtifacts.set(false);mobile.set(innerWidth<768);tools.set([]);user.set({id:'fixture',role:'admin',name:'Test'} as any);});
</script>
<main class="bg-white dark:bg-black min-h-screen p-4 text-gray-900 dark:text-white">
 <button id="finish" on:click={()=>done=true}>Finish</button>
 <span id="learning">{learningEnabled}</span>
 <span id="file-generation">{fileGenerationEnabled}</span>
 <button id="restore-conflict" on:click={()=>{learningEnabled=true;fileGenerationEnabled=true;}}>Restore conflict</button>
 <section id="defaults"><DefaultFeatures bind:featureIds tooltipsEnabled={false}/></section>
 <span id="default-feature-ids">{featureIds.join(',')}</span>
 <section style="max-width:650px">
  <ContentRenderer id="learn-artifact" messageId="a" {content} {history} messageDone={done} preview />
  <div id="first-card"><ArtifactCards {content} messageId="a" {done} {history}/></div>
  <div id="second-card"><ArtifactCards content={second} messageId="b" done {history}/></div>
 </section>
 {#if $showArtifacts}<aside style="height:480px;width:100%;max-width:650px"><Artifacts /></aside>{/if}
 <div style="position:fixed;bottom:20px;left:20px">
  <InputMenu above showWebSearchButton showLearningButton bind:learningEnabled bind:fileGenerationEnabled selectedModels={[]} fileUploadCapableModels={[]} uploadFilesHandler={()=>{}} onUpload={()=>{}} onClose={()=>{}}>
   <button id="open-menu">More</button>
  </InputMenu>
 </div>
</main>
