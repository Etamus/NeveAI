<script>
 import StatusHistory from '$lib/components/chat/Messages/ResponseMessage/StatusHistory.svelte';
 let finished = false;
</script>
<main style="padding:80px 24px">
 <div id="document-status"><StatusHistory statusHistory={[
  {action:'file_generation',description:'Preparando arquivo...',done:false},
  ...(finished ? [{action:'file_generation',description:'Arquivo pronto',done:true}] : [])
 ]} /></div>
 <button id="complete-document" on:click={() => finished = true}>Complete fixture</button>
</main>
