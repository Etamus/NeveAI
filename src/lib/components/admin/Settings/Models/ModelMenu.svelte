<script lang="ts">
	import { DropdownMenu } from 'bits-ui';
	import { flyAndScale } from '$lib/utils/transitions';
	import { getContext } from 'svelte';

	import Dropdown from '$lib/components/common/Dropdown.svelte';
	import GarbageBin from '$lib/components/icons/GarbageBin.svelte';
	import Pencil from '$lib/components/icons/Pencil.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import Tags from '$lib/components/chat/Tags.svelte';
	import Share from '$lib/components/icons/Share.svelte';
	import ArchiveBox from '$lib/components/icons/ArchiveBox.svelte';
	import DocumentDuplicate from '$lib/components/icons/DocumentDuplicate.svelte';
	import Download from '$lib/components/icons/Download.svelte';
	import ArrowUpCircle from '$lib/components/icons/ArrowUpCircle.svelte';
	import Pin from '$lib/components/icons/Pin.svelte';
	import PinSlash from '$lib/components/icons/PinSlash.svelte';

	import { config, settings } from '$lib/stores';
	import Link from '$lib/components/icons/Link.svelte';

	const i18n = getContext('i18n');

	export let user;
	export let model;

	export let exportHandler: Function;
	export let pinModelHandler: Function;

	export let onClose: Function;

	let show = false;
</script>

<Dropdown
	bind:show
	on:change={(e) => {
		if (e.detail === false) {
			onClose();
		}
	}}
>
	<Tooltip content={$i18n.t('More')}>
		<slot />
	</Tooltip>

	<div slot="content">
		<DropdownMenu.Content
			class="w-full max-w-[170px] rounded-xl p-1 border border-gray-100  dark:border-gray-800 z-[10000] bg-white dark:bg-gray-850 dark:text-white shadow-sm"
			sideOffset={-2}
			side="bottom"
			align="start"
			transition={flyAndScale}
		>
			<DropdownMenu.Item
				class="select-none flex  gap-2  items-center px-3 py-1.5 text-sm  font-medium cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800 rounded-md"
				on:click={() => {
					pinModelHandler(model?.id);
				}}
			>
				{#if ($settings?.pinnedModels ?? []).includes(model?.id)}
					<PinSlash />
				{:else}
					<Pin />
				{/if}

				<div class="flex items-center">
					{#if ($settings?.pinnedModels ?? []).includes(model?.id)}
							Desfixar
						{:else}
							Fixar
					{/if}
				</div>
			</DropdownMenu.Item>

			<DropdownMenu.Item
				class="select-none flex gap-2 items-center px-3 py-1.5 text-sm  font-medium cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800 rounded-md"
				on:click={() => {
					exportHandler();
				}}
			>
				<Download />

				<div class="flex items-center">{$i18n.t('Export')}</div>
			</DropdownMenu.Item>
		</DropdownMenu.Content>
	</div>
</Dropdown>
