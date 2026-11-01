<script lang="ts">
	import { onMount, setContext } from 'svelte';
	import { writable } from 'svelte/store';
	import FileItemModal from '../../src/lib/components/common/FileItemModal.svelte';
	import FilePreview from '../../src/lib/components/chat/FileNav/FilePreview.svelte';
	setContext('i18n', writable({ language: 'en-US', t: (text: string) => text }));
	let item: any;
	let show = false;
	let sideKind = '';
	let names = Array.from({ length: 24 }, (_, i) => `Sheet ${i + 1}`);
	let selected = names[0];
	let slides: string[] = [];
	const open = (kind: string) => {
		item = { id: kind, type: 'file', name: kind === 'xlsx' ? 'Many sheets.xlsx' : 'Wide slides.pptx', size: 1000, file: { data: {} } };
		show = true;
	};
	onMount(() => {
		(window as any).__officeFixture = { side: (kind: string, images: string[]) => { sideKind = kind; slides = images; } };
		return () => { delete (window as any).__officeFixture; };
	});
</script>
<main class="h-[100dvh] p-4">
	<button id="open-xlsx" on:click={() => open('xlsx')}>Spreadsheet</button>
	<button id="open-pptx" on:click={() => open('pptx')}>Presentation</button>
	{#if sideKind}
		<div id="side-preview" class="mt-3 flex h-[65dvh] min-h-0 w-full flex-col overflow-hidden">
			<FilePreview selectedFile={sideKind === 'xlsx' ? 'sheets.xlsx' : 'slides.pptx'}
				fileOfficeHtml={sideKind === 'xlsx' ? `<table><tr><td>${selected}</td></tr></table>` : null}
				fileOfficeSlides={sideKind === 'pptx' ? slides : null}
				excelSheetNames={names} selectedExcelSheet={selected} onSheetChange={(value) => selected = value} />
		</div>
	{/if}
	{#if item}{#key item.id}<FileItemModal bind:show {item} animated={false} />{/key}{/if}
</main>
