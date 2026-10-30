<script>
	import Skeleton from '$lib/components/chat/Messages/Skeleton.svelte';
</script>

<main class="bg-white dark:bg-black" style="min-height:100vh;padding:80px">
	<div id="orbit-normal"><Skeleton size="sm" /></div>
	<div id="orbit-compact" style="margin-top:32px"><Skeleton size="xs" /></div>
</main>
