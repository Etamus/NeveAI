<script>
    import StatusItem from '$lib/components/chat/Messages/ResponseMessage/StatusHistory/StatusItem.svelte';
    const url = 'O que esse link fala? https://www.reddit.com/r/ECE/comments/1rphq0l/free_stuff_you_can_claim_with_your_student_email/?solution=' + 'abc123'.repeat(90);
</script>

<div class="min-h-screen bg-white p-4 dark:bg-black">
    <main style="max-width:660px;margin:50px auto">
        <section id="long"><StatusItem status={{action:'web_search_queries_generated',queries:[url]}} /></section>
        <section id="short"><StatusItem status={{action:'web_search_queries_generated',queries:['clima hoje']}} /></section>
        <section id="unbroken"><StatusItem status={{action:'web_search_queries_generated',queries:['a'.repeat(5000)]}} /></section>
        <section id="deep"><StatusItem status={{action:'web_search_queries_generated',deep_search:true,queries:[url,'fontes oficiais','b'.repeat(2000)]}} /></section>
        <section id="retrieval"><StatusItem status={{action:'queries_generated',queries:[url]}} /></section>
    </main>
</div>
