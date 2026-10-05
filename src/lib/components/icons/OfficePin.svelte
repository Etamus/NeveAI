<script lang="ts">
	export let className = 'size-4';
	export let slashed = false;
</script>

<svg
	xmlns="http://www.w3.org/2000/svg"
	class={className}
	viewBox="0 0 24 24"
	fill="none"
	stroke="currentColor"
	stroke-width="1.5"
	stroke-linecap="round"
	stroke-linejoin="round"
	aria-hidden="true"
>
	<path d="m16 3 5 5-3 1-4 4v4l-7-7h4l4-4 1-3ZM9 15l-6 6" />
	{#if slashed}<path d="m3 3 18 18" />{/if}
</svg>
