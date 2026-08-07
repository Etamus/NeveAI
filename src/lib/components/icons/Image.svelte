<script lang="ts">
	export let className = 'size-4';
	export let strokeWidth = '1.5';
</script>

<svg
	aria-hidden="true"
	xmlns="http://www.w3.org/2000/svg"
	fill="none"
	viewBox="0 0 24 24"
	stroke="currentColor"
	stroke-width={strokeWidth}
	class={className}
>
	<rect x="3" y="3" width="18" height="18" rx="2" stroke-linecap="round" stroke-linejoin="round" />
	<circle cx="8.5" cy="8.5" r="1.5" />
	<path
		d="m21 15-3.1-3.1a2 2 0 0 0-2.8 0L6 21"
		stroke-linecap="round"
		stroke-linejoin="round"
	/>
</svg>
