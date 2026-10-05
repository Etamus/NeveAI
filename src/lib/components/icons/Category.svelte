<script lang="ts">
	export let className = 'size-4.5';
	export let strokeWidth = '1.5';
	export let squaresOnly = false;
</script>

<svg
	xmlns="http://www.w3.org/2000/svg"
	class={className}
	viewBox="0 0 24 24"
	fill="none"
	stroke="currentColor"
	stroke-width={strokeWidth}
	stroke-linecap="round"
	stroke-linejoin="round"
	aria-hidden="true"
>
	<rect x="3" y="3" width="7" height="7" rx="1" />
	<rect x="14" y="3" width="7" height="7" rx="1" />
	<rect x="3" y="14" width="7" height="7" rx="1" />
	{#if squaresOnly}<rect x="14" y="14" width="7" height="7" rx="1" />{:else}<circle
			cx="17.5"
			cy="17.5"
			r="3.5"
		/>{/if}
</svg>
