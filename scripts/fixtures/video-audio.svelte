<script>
	import { onMount } from 'svelte';
	import GeneratedVideoPlayer from '$lib/components/chat/Messages/GeneratedVideoPlayer.svelte';
	let src = '';
	onMount(() => {
		const params = new URLSearchParams(location.search);
		document.documentElement.classList.toggle('dark', params.get('dark') === 'true');
		src = `${location.origin}/__audio_media/${params.get('case')}.mp4`;
	});
</script>

<div class="p-4 w-full max-w-3xl">
	{#if src}<GeneratedVideoPlayer {src} name="native-audio.mp4" />{/if}
</div>
