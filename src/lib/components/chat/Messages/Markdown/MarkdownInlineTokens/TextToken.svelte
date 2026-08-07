<script lang="ts">
	import { fade } from 'svelte/transition';

	export let token;
	export let done = true;

	let texts = [];
	$: texts = (token?.raw ?? '').split(' ');
</script>

{#if done}
	{token?.raw}
{:else}
	{#each texts as text, index}
		<span class="" in:fade={{ duration: 100 }}>
			{text}{index < texts.length - 1 ? ' ' : ''}
		</span>
	{/each}
{/if}
