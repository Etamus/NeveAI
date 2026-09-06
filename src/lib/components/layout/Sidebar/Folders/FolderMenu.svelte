<script lang="ts">
	import { DropdownMenu } from 'bits-ui';
	import { fade } from 'svelte/transition';
	import { getContext, createEventDispatcher } from 'svelte';

	const i18n = getContext('i18n');
	const dispatch = createEventDispatcher();

	import Dropdown from '$lib/components/common/Dropdown.svelte';
	import GarbageBin from '$lib/components/icons/GarbageBin.svelte';
	import Pencil from '$lib/components/icons/Pencil.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import Download from '$lib/components/icons/Download.svelte';
	import Folder from '$lib/components/icons/Folder.svelte';

	export let align: 'start' | 'end' = 'start';
	export let onEdit = () => {};
	export let onExport = () => {};
	export let onDelete = () => {};
	export let onCreateSub = () => {};

	let show = false;
</script>

<Dropdown
	bind:show
	on:change={(e) => {
		if (e.detail === false) {
			dispatch('close');
		}
	}}
>
	<Tooltip content={$i18n.t('More')}>
		<button
			on:click={(e) => {
				e.stopPropagation();
				show = !show;
			}}
		>
			<slot />
		</button>
	</Tooltip>

	<div slot="content">
		<DropdownMenu.Content
			class="select-none w-full max-w-[200px] rounded-md px-1 py-1 border border-gray-100 dark:border-gray-800 z-50 bg-white dark:bg-gray-850 dark:text-white shadow-md"
			sideOffset={-2}
			side="bottom"
			{align}
			transition={(node) => fade(node, { duration: 100 })}
		>
			<DropdownMenu.Item
				draggable="false"
				class="flex gap-2 items-center px-3 py-1.5 text-sm select-none cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800 rounded-sm"
				on:click={() => {
					onEdit();
				}}
			>
				<Pencil strokeWidth="1.5" />
				<div class="flex items-center">{$i18n.t('Edit')}</div>
			</DropdownMenu.Item>

			<DropdownMenu.Item
				draggable="false"
				class="flex gap-2 items-center px-3 py-1.5 text-sm select-none cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800 rounded-sm"
				on:click={() => {
					onDelete();
				}}
			>
				<GarbageBin strokeWidth="1.5" />
				<div class="flex items-center">{$i18n.t('Delete')}</div>
			</DropdownMenu.Item>
		</DropdownMenu.Content>
	</div>
</Dropdown>
