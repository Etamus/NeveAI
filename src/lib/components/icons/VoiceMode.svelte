<script lang="ts">
	export let className = 'composer-submit-glyph size-5';
	export let levels: number[] | null = null;
	const bars = ['M4 10v4', 'M8 7v10', 'M12 4v16', 'M16 7v10', 'M20 10v4'];
</script>

<!-- Voice waveform adapted from SVG Repo (431376, CC0). -->
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor"
	stroke-width="2" stroke-linecap="round" class={className} class:speaking={levels !== null} aria-hidden="true">
	{#each bars as d, index}
		<path {d} style:transform={levels ? `scaleY(${levels[index]})` : undefined} />
	{/each}
</svg>

<style>
	path { transform-origin: 12px 12px; transition: transform 65ms linear; }
	@media (prefers-reduced-motion: reduce) { path { transition: none; } }
</style>
