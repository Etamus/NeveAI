<script lang="ts">
	import { onMount, setContext } from 'svelte';
	import { writable } from 'svelte/store';
	import Library from '../../src/routes/(app)/library/+page.svelte';
	import { excelToTable } from '../../src/lib/utils/excelToTable';
	import { pptxToImages } from '../../src/lib/utils/pptxToHtml';
	setContext('i18n', writable({language:'en-US', t:(text:string) => text}));
	onMount(() => {
		(window as any).__auditConverters = {excelToTable, pptxToImages};
		return () => { delete (window as any).__auditConverters; };
	});
</script>
<div style="height:100dvh"><Library /></div>
