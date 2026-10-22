<script lang="ts">
	import { settings } from '$lib/stores';
	export let label: string;
	export let disabled = false;
	export let topOffset = '-top-0.5';
	export let framed = false;
</script>

<button type="button" {disabled} aria-label={label} data-attachment-remove
	class="absolute {topOffset} -right-1 z-10 grid size-4 min-h-0 min-w-0 shrink-0 place-items-center p-0 leading-none border border-gray-700 bg-gray-700 text-white dark:border-white dark:bg-white dark:text-black outline-hidden focus-visible:ring-2 focus-visible:ring-gray-400 {($settings?.highContrastMode ?? false) ? '' : 'invisible group-hover/attachment:visible focus-visible:visible'}"
	style="aspect-ratio: 1; border-radius: 50%; box-sizing: border-box;"
	style:margin-top={framed ? undefined : '1px'}
	style:margin-right={framed ? undefined : '1px'}
	on:click|stopPropagation>
	<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true" class="block size-3.5 shrink-0">
		<path d="M6.28 5.22a.75.75 0 00-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 101.06 1.06L10 11.06l3.72 3.72a.75.75 0 101.06-1.06L11.06 10l3.72-3.72a.75.75 0 00-1.06-1.06L10 8.94 6.28 5.22z" />
	</svg>
</button>
