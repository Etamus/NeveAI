<script>
	import { getContext } from 'svelte';

	import XMark from '$lib/components/icons/XMark.svelte';
	import Modal from '$lib/components/common/Modal.svelte';

	const i18n = getContext('i18n');

	export let show = false;
</script>

<Modal size="sm" bind:show>
	<div>
		<div class="flex justify-between items-center dark:text-gray-100 px-5 pt-4 pb-3 border-b border-gray-100 dark:border-gray-800">
			<div class="text-lg font-semibold font-primary">
				{$i18n.t('Manage Models')}
			</div>
			<button
				class="text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 transition"
				on:click={() => {
					show = false;
				}}
			>
				<XMark className={'size-5'} />
			</button>
		</div>

		<div class="flex flex-col w-full px-4 py-3 dark:text-gray-200">
			<div class="py-5 text-gray-400 text-xs">
				{$i18n.t('No model manager available')}
			</div>
		</div>
	</div>
</Modal>
