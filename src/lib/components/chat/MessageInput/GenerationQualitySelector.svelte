<script lang="ts">
	import { getContext, tick } from 'svelte';
	import { fly } from 'svelte/transition';
	import type { I18nStore } from '$lib/i18n';
	import CheckCircle from '$lib/components/icons/CheckCircle.svelte';
	const i18n = getContext<I18nStore>('i18n');
	export let id: string;
	export let label: string;
	export let options: readonly { id: string; label: string }[];
	export let value: string;
	export let open = false;
	export let ongoing = false;
	export let position: (node: HTMLElement) => any;
	export let choose: (value: string) => void;
	export let closeOthers: () => void;
	let trigger: HTMLButtonElement;
	let menu: HTMLElement;
	function toggle() {
		const next = !open;
		closeOthers();
		open = next;
	}
	function close() { open = false; trigger?.focus({preventScroll:true}); }
	async function navigate(e: KeyboardEvent) {
		if (!['ArrowDown','ArrowUp','Escape'].includes(e.key)) return;
		e.preventDefault();
		if (e.key === 'Escape') { close(); return; }
		const opening = !open;
		if (opening) { toggle(); await tick(); }
		const buttons = Array.from(menu.querySelectorAll('button'));
		const i = buttons.indexOf(document.activeElement as HTMLButtonElement);
		buttons[opening || i < 0 ? Math.max(0, options.findIndex(o => o.id === value)) :
			(i + (e.key === 'ArrowUp' ? -1 : 1) + buttons.length) % buttons.length]?.focus();
	}
</script>

<svelte:window on:click={e => { if (open && !(e.target as Element)?.closest(`#${id},[data-composer-dropdown-anchor="${id}"]`)) open = false; }} />
<div {id} class="relative shrink-0">
	<button bind:this={trigger} type="button" aria-label={$i18n.t(label)} aria-expanded={open} aria-haspopup="menu"
		class="flex items-center gap-1 px-2 py-[7px] text-[0.8125rem] text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-full whitespace-nowrap"
		on:click|preventDefault={toggle} on:keydown={navigate}>
		<span>{$i18n.t(options.find(o => o.id === value)?.label ?? options[0].label)}</span>
		<svg viewBox="0 0 20 20" fill="currentColor" class="size-3.5 shrink-0 transition-transform duration-150 {open ? '' : 'rotate-180'}" aria-hidden="true">
			<path fill-rule="evenodd" clip-rule="evenodd" d="M14.78 12.78a.75.75 0 0 1-1.06 0L10 9.06l-3.72 3.72a.75.75 0 0 1-1.06-1.06l4.25-4.25a.75.75 0 0 1 1.06 0l4.25 4.25a.75.75 0 0 1 0 1.06Z"/>
		</svg>
	</button>
	{#if open}
		<div bind:this={menu} use:position role="menu" tabindex="-1" aria-label={$i18n.t(label)} on:keydown={navigate}
			class="fixed z-50 w-44 rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-850 shadow-md p-1 text-sm"
			in:fly={{ y: ongoing ? 5 : -5, duration: 150 }}>
			{#each options as option}
				<button type="button" role="menuitemradio" aria-checked={value === option.id}
					class="flex w-full items-center justify-between px-2 py-2 rounded-md text-left text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800"
					on:click={() => {choose(option.id); close();}}>
					<span>{$i18n.t(option.label)}</span>{#if value === option.id}<CheckCircle strokeWidth="1.7" />{/if}
				</button>
			{/each}
		</div>
	{/if}
</div>
