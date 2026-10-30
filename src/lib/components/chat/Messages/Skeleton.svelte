<script lang="ts">
	import OrbitingSpheres from '$lib/components/common/OrbitingSpheres.svelte';
	export let size = 'md';
</script>

{#if size === 'md'}
	<div class="flex flex-col gap-2.5 my-2 mx-1">
		<div class="h-3 rounded-md shimmer-bar" style="width: 60%"></div>
		<div class="h-3 rounded-md shimmer-bar" style="width: 82%"></div>
		<div class="h-3 rounded-md shimmer-bar" style="width: 45%"></div>
	</div>
{:else}
	<OrbitingSpheres compact={size === 'xs'} />
{/if}

<style>
	@keyframes shimmer-slide {
		0% {
			background-position: 200% 0;
		}
		100% {
			background-position: -200% 0;
		}
	}

	.shimmer-bar {
		background: linear-gradient(90deg, #e5e5e5 25%, #d4d4d4 50%, #e5e5e5 75%);
		background-size: 200% 100%;
		animation: shimmer-slide 2s linear infinite;
	}

	:global(.dark) .shimmer-bar {
		background: linear-gradient(90deg, #2a2a2e 25%, #3a3a3e 50%, #2a2a2e 75%);
		background-size: 200% 100%;
		animation: shimmer-slide 2s linear infinite;
	}
</style>
