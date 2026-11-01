<script lang="ts">
	import { getContext, tick } from 'svelte';
	import ChevronLeft from '$lib/components/icons/ChevronLeft.svelte';
	import ChevronRight from '$lib/components/icons/ChevronRight.svelte';
	import Tooltip from './Tooltip.svelte';

	const i18n = getContext('i18n');
	export let sheets: string[] = [];
	export let selected = '';
	export let onSelect: (sheet: string) => void = () => {};
	let track: HTMLDivElement;
	let canGoBack = false;
	let canGoForward = false;

	const updateEdges = () => {
		if (!track) return;
		canGoBack = track.scrollLeft > 1;
		canGoForward = track.scrollLeft + track.clientWidth < track.scrollWidth - 1;
	};

	const revealSelected = async () => {
		await tick();
		const node = track;
		const tab = node?.querySelector<HTMLElement>('[aria-selected="true"]');
		if (!tab) return;
		const bounds = node.getBoundingClientRect();
		const rect = tab.getBoundingClientRect();
		if (rect.left < bounds.left) node.scrollLeft += rect.left - bounds.left;
		else if (rect.right > bounds.right) node.scrollLeft += rect.right - bounds.right;
		updateEdges();
	};

	const observeTrack = (node: HTMLDivElement) => {
		const observer = new ResizeObserver(() => { void revealSelected(); });
		observer.observe(node);
		return { destroy: () => observer.disconnect() };
	};

	const move = (direction: number) => {
		track.scrollBy({ left: direction * Math.max(80, track.clientWidth * 0.75), behavior: 'smooth' });
	};

	const navigate = async (event: KeyboardEvent, index: number) => {
		let next = index;
		if (event.key === 'ArrowLeft') next = Math.max(0, index - 1);
		else if (event.key === 'ArrowRight') next = Math.min(sheets.length - 1, index + 1);
		else if (event.key === 'Home') next = 0;
		else if (event.key === 'End') next = sheets.length - 1;
		else return;
		event.preventDefault();
		onSelect(sheets[next]);
		await tick();
		track.querySelectorAll<HTMLButtonElement>('[role="tab"]')[next]?.focus({ preventScroll: true });
	};

	$: if (track && sheets.length && selected) void revealSelected();
</script>

<div class="sheet-navigation flex min-w-0 shrink-0 items-center gap-1 border-b border-gray-100 dark:border-gray-800">
	<Tooltip content={$i18n.t('Previous')}>
		<button type="button" aria-label={$i18n.t('Previous')} disabled={!canGoBack}
			class="grid size-8 shrink-0 place-items-center rounded-md text-gray-500 hover:bg-gray-100 disabled:opacity-30 dark:hover:bg-gray-800"
			on:click={() => move(-1)}><ChevronLeft className="size-4" /></button>
	</Tooltip>
	<div bind:this={track} use:observeTrack role="tablist" aria-label={$i18n.t('Sheets')}
		class="sheet-tab-track scrollbar-none flex min-w-0 flex-1 overflow-x-auto text-sm" on:scroll={updateEdges}>
		{#each sheets as sheet, index}
			<button type="button" role="tab" aria-selected={selected === sheet} tabindex={selected === sheet ? 0 : -1}
				class="shrink-0 whitespace-nowrap border-b-2 px-3 py-2 transition-colors {selected === sheet
					? 'border-gray-600 text-gray-900 dark:border-gray-300 dark:text-gray-100'
					: 'border-transparent text-gray-500 hover:text-gray-900 dark:hover:text-gray-100'}"
				on:click={() => onSelect(sheet)} on:keydown={(event) => navigate(event, index)}>{sheet}</button>
		{/each}
	</div>
	<Tooltip content={$i18n.t('Next')}>
		<button type="button" aria-label={$i18n.t('Next')} disabled={!canGoForward}
			class="grid size-8 shrink-0 place-items-center rounded-md text-gray-500 hover:bg-gray-100 disabled:opacity-30 dark:hover:bg-gray-800"
			on:click={() => move(1)}><ChevronRight className="size-4" /></button>
	</Tooltip>
</div>
