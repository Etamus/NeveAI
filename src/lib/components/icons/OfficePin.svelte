<script lang="ts">
	export let className = 'size-4';
	export let filled = false;
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
	<g transform="rotate(45 12 12)">
		<path d="M9 3h6v5l3 3v3H6v-3l3-3V3Z" fill={filled ? 'currentColor' : 'none'} />
		<path d="M8 3h8M12 14v7" />
	</g>
</svg>
