<script lang="ts">
	import { DropdownMenu } from 'bits-ui';
	import { getContext, onMount } from 'svelte';
	import ArrowUpDown from '$lib/components/icons/ArrowUpDown.svelte';
	import CheckCircle from '$lib/components/icons/CheckCircle.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import { onChatDropdownDismiss } from '$lib/utils/chatDropdownDismissal';
	import type { SidebarChatSort } from '$lib/utils/sidebarChatSort';
	export let value: SidebarChatSort = 'recent';
	export let onChange: (value: SidebarChatSort) => void;
	const i18n = getContext('i18n');
	let open = false;
	function stopHeaderToggle(node: HTMLElement) {
		const stop = (event: Event) => event.stopPropagation();
		node.addEventListener('pointerup', stop);
		return { destroy() { node.removeEventListener('pointerup', stop); } };
	}
	onMount(() => onChatDropdownDismiss(() => { open = false; }));
</script>

<DropdownMenu.Root bind:open>
	<div use:stopHeaderToggle>
	<Tooltip content={$i18n.t('Sort conversations')}>
		<DropdownMenu.Trigger aria-label={$i18n.t('Sort conversations')} class="size-6 flex items-center justify-center rounded-md text-gray-500 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-800 {open ? 'bg-gray-200 dark:bg-gray-800' : ''}" on:click={event => event.stopPropagation()}>
			<ArrowUpDown className="size-3.5" />
		</DropdownMenu.Trigger>
	</Tooltip>
	</div>
	<DropdownMenu.Content side="right" align="start" sideOffset={6} avoidCollisions={true} fitViewport={true} class="z-50 w-44 max-w-[calc(100vw-16px)] rounded-md border border-gray-100 dark:border-gray-800 bg-white dark:bg-gray-850 p-1 shadow-md text-sm text-gray-700 dark:text-gray-200">
		{#each [{ id: 'recent', label: 'Most recent' }, { id: 'name', label: 'Name' }] as option}
			<DropdownMenu.Item role="menuitemradio" aria-checked={value === option.id} class="flex items-center justify-between gap-4 rounded-sm px-3 py-1.5 cursor-pointer select-none hover:bg-gray-100 dark:hover:bg-gray-800" on:click={() => { open = false; onChange(option.id as SidebarChatSort); }}>
				<span>{$i18n.t(option.label)}</span>
				<span class="size-4 shrink-0">{#if value === option.id}<CheckCircle strokeWidth="1.7" />{/if}</span>
			</DropdownMenu.Item>
		{/each}
	</DropdownMenu.Content>
</DropdownMenu.Root>
