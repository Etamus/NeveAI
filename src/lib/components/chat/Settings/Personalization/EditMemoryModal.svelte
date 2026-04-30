<script>
	import { createEventDispatcher, getContext } from 'svelte';
	import { toast } from 'svelte-sonner';

	import { updateMemoryById } from '$lib/apis/memories';

	import Spinner from '$lib/components/common/Spinner.svelte';
	import Modal from '$lib/components/common/Modal.svelte';
	import XMark from '$lib/components/icons/XMark.svelte';

	const dispatch = createEventDispatcher();

	export let show;
	export let memory = {};

	const i18n = getContext('i18n');

	let loading = false;
	let content = '';

	$: if (show) {
		setContent();
	}

	const setContent = () => {
		content = memory.content;
	};

	const submitHandler = async () => {
		loading = true;

		const res = await updateMemoryById(localStorage.token, memory.id, content).catch((error) => {
			toast.error(`${error}`);

			return null;
		});

		if (res) {
			console.log(res);
			toast.success($i18n.t('Memory updated successfully'));
			dispatch('save');
			show = false;
		}

		loading = false;
	};
</script>

<Modal bind:show size="sm">
	<div>
		<div class=" flex justify-between dark:text-gray-300 px-5 pt-4 pb-3 border-b border-gray-200/30 dark:border-gray-700/20">
			<div class=" text-lg font-medium self-center">
				{$i18n.t('Editar memória')}
			</div>
			<button
				class="self-center"
				on:click={() => {
					show = false;
				}}
			>
				<XMark className={'size-5'} />
			</button>
		</div>

		<div class="flex flex-col md:flex-row w-full px-5 pb-4 pt-4 md:space-x-4 dark:text-gray-200">
			<div class=" flex flex-col w-full sm:flex-row sm:justify-center sm:space-x-6">
				<form
					class="flex flex-col w-full"
					on:submit|preventDefault={() => {
						submitHandler();
					}}
				>
					<div class="">
						<textarea
							bind:value={content}
							class=" bg-transparent w-full text-sm rounded-xl p-3 outline outline-1 outline-gray-100 dark:outline-gray-800 placeholder:text-gray-300 dark:placeholder:text-gray-700"
							rows="3"
							style="resize: vertical;"
							placeholder={$i18n.t('Enter a detail about yourself for your LLMs to recall')}
						/>
					</div>

					<div class="flex justify-end pt-5 text-sm font-medium">
						<button
							class="px-4 py-1.5 text-xs font-medium bg-black text-white dark:bg-white dark:text-black hover:opacity-90 transition rounded-lg flex items-center gap-2 whitespace-nowrap {loading
								? ' cursor-not-allowed'
								: ''}"
							type="submit"
							disabled={loading}
						>
							{$i18n.t('Update')}

							{#if loading}
								<span class="shrink-0">
									<Spinner />
								</span>
							{/if}
						</button>
					</div>
				</form>
			</div>
		</div>
	</div>
</Modal>
