<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';

	onMount(async () => {
		const redirectPath = $page.url.searchParams.get('redirect') || '/';
		await goto(redirectPath.startsWith('/') ? redirectPath : '/', { replaceState: true });
	});
</script>