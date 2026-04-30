<script lang="ts">
	import { toast } from 'svelte-sonner';
	import dayjs from 'dayjs';
	import { getContext, createEventDispatcher } from 'svelte';

	const dispatch = createEventDispatcher();

	import Modal from '$lib/components/common/Modal.svelte';
	import AddMemoryModal from './AddMemoryModal.svelte';
	import { deleteMemoriesByUserId, deleteMemoryById, getMemories } from '$lib/apis/memories';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import { error } from '@sveltejs/kit';
	import EditMemoryModal from './EditMemoryModal.svelte';
	import localizedFormat from 'dayjs/plugin/localizedFormat';
	import ConfirmDialog from '$lib/components/common/ConfirmDialog.svelte';

	const i18n = getContext('i18n');
	dayjs.extend(localizedFormat);

	export let show = false;

	let memories = [];
	let loading = true;

	let showAddMemoryModal = false;
	let showEditMemoryModal = false;

	let selectedMemory = null;

	let showClearConfirmDialog = false;

	let onClearConfirmed = async () => {
		const res = await deleteMemoriesByUserId(localStorage.token).catch((error) => {
			toast.error(`${error}`);
			return null;
		});

		if (res && memories.length > 0) {
			toast.success($i18n.t('Memory cleared successfully'));
			memories = [];
		}
		showClearConfirmDialog = false;
	};

	$: if (show && memories.length === 0 && loading) {
		(async () => {
			memories = await getMemories(localStorage.token);
			loading = false;
		})();
	}
</script>

<Modal size="md" bind:show>
	<div>
		<div class=" flex justify-between dark:text-gray-300 px-5 pt-4 pb-1">
			<div class=" text-lg font-medium self-center">{$i18n.t('Memory')}</div>
			<div class="flex items-center gap-1.5">
				<button
					class="px-3 py-1 text-xs font-medium bg-black text-white dark:bg-white dark:text-black hover:opacity-90 transition rounded-lg"
					on:click={() => {
						showAddMemoryModal = true;
					}}>{$i18n.t('Adicionar')}</button
				>
				<button
					class="px-3 py-1 text-xs font-medium bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 transition rounded-lg"
					on:click={() => {
						if (memories.length > 0) {
							showClearConfirmDialog = true;
						} else {
							toast.error($i18n.t('No memories to clear'));
						}
					}}>{$i18n.t('Limpar')}</button
				>
			</div>
		</div>

		<div class="flex flex-col w-full px-5 pb-5 dark:text-gray-200">
			<div
				class=" flex flex-col w-full sm:flex-row sm:justify-center sm:space-x-6 h-[20rem] max-h-screen rounded-xl mb-2 mt-1"
			>
				{#if memories.length > 0}
					<div class="text-left text-sm w-full mb-4 overflow-y-scroll">
						<div class="relative overflow-x-auto">
							<table class="w-full text-sm text-left text-gray-600 dark:text-gray-400 table-auto">
								<thead
									class="text-xs text-gray-700 bg-transparent dark:text-gray-200 border-b-2 border-gray-50 dark:border-gray-850/30"
								>
									<tr>
										<th scope="col" class="px-3 py-2"> {$i18n.t('Name')} </th>
										<th scope="col" class="px-3 py-2 hidden md:flex">
											{$i18n.t('Last Modified')}
										</th>
										<th scope="col" class="px-3 py-2 text-right" />
									</tr>
								</thead>
								<tbody>
									{#each memories as memory}
										<tr class="border-b border-gray-50 dark:border-gray-850/30 items-center">
											<td class="px-3 py-1">
												<div class="line-clamp-1">
													{memory.content}
												</div>
											</td>
											<td class=" px-3 py-1 hidden md:flex h-[2.5rem]">
												<div class="my-auto whitespace-nowrap">
													{dayjs(memory.updated_at * 1000).format('LLL')}
												</div>
											</td>
											<td class="px-3 py-1">
												<div class="flex justify-end w-full">
													<Tooltip content="Editar">
														<button
															class="self-center w-fit text-sm px-2 py-2 hover:bg-black/5 dark:hover:bg-white/5 rounded-xl"
															on:click={() => {
																selectedMemory = memory;
																showEditMemoryModal = true;
															}}
														>
															<svg
																xmlns="http://www.w3.org/2000/svg"
																fill="none"
																viewBox="0 0 24 24"
																stroke-width="2"
																stroke="currentColor"
																aria-hidden="true"
																class="w-4 h-4"
																><path
																	stroke-linecap="round"
																	stroke-linejoin="round"
																	d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"
																/><path
																	stroke-linecap="round"
																	stroke-linejoin="round"
																	d="m15 5 4 4"
																/></svg
															>
														</button>
													</Tooltip>

													<Tooltip content="Deletar">
														<button
															class="self-center w-fit text-sm px-2 py-2 hover:bg-black/5 dark:hover:bg-white/5 rounded-xl"
															on:click={async () => {
																const res = await deleteMemoryById(
																	localStorage.token,
																	memory.id
																).catch((error) => {
																	toast.error(`${error}`);
																	return null;
																});

																if (res) {
																	toast.success($i18n.t('Memory deleted successfully'));
																	memories = await getMemories(localStorage.token);
																}
															}}
														>
															<svg
																xmlns="http://www.w3.org/2000/svg"
																fill="none"
																viewBox="0 0 24 24"
																stroke-width="1.5"
																stroke="currentColor"
																class="w-4 h-4"
															>
																<path
																	stroke-linecap="round"
																	stroke-linejoin="round"
																	d="m14.74 9-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 0 1-2.244 2.077H8.084a2.25 2.25 0 0 1-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 0 0-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 0 1 3.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 0 0-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 0 0-7.5 0"
																/>
															</svg>
														</button>
													</Tooltip>
												</div>
											</td>
										</tr>
									{/each}
								</tbody>
							</table>
						</div>
					</div>
				{:else}
					<div class="text-center flex h-full text-sm w-full">
						<div class=" my-auto pb-10 px-4 w-full text-gray-500">
							{$i18n.t('Memories accessible by LLMs will be shown here.')}
						</div>
					</div>
				{/if}
			</div>
		</div>
	</div>
</Modal>

<ConfirmDialog
	title={$i18n.t('Limpar memória')}
	message={$i18n.t('Are you sure you want to clear all memories? This action cannot be undone.')}
	bind:show={showClearConfirmDialog}
	on:confirm={onClearConfirmed}
	on:cancel={() => {
		showClearConfirmDialog = false;
	}}
/>

<AddMemoryModal
	bind:show={showAddMemoryModal}
	on:save={async () => {
		memories = await getMemories(localStorage.token);
	}}
/>

<EditMemoryModal
	bind:show={showEditMemoryModal}
	memory={selectedMemory}
	on:save={async () => {
		memories = await getMemories(localStorage.token);
	}}
/>
