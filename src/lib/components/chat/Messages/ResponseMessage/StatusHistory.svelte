<script>
	import { getContext } from 'svelte';
	const i18n = getContext('i18n');

	import StatusItem from './StatusHistory/StatusItem.svelte';
	export let statusHistory = [];
	export let expand = false;

	let showHistory = true;

	$: if (expand) {
		showHistory = true;
	} else {
		showHistory = false;
	}

	let history = [];
	let status = null;
	let visibleHistory = [];

	const isQueryingStatus = (item) => {
		const action = String(item?.action ?? '')
			.trim()
			.toLowerCase();
		const description = String(item?.description ?? '')
			.trim()
			.toLowerCase();

		return (
			action === 'queries_generated' || description === 'querying' || description === 'consultando'
		);
	};

	$: visibleHistory = (history ?? []).filter(
		(item) => item?.hidden !== true && !isQueryingStatus(item)
	);
	$: status = visibleHistory.at(-1) ?? null;
	$: isCompletedVisualStatus =
		status?.done === true &&
		['stable_diffusion', 'video_generation', 'music_generation'].includes(
			String(status?.action ?? '').toLowerCase()
		);

	$: if (isCompletedVisualStatus) {
		showHistory = false;
	}

	$: if (
		statusHistory.length !== history.length ||
		JSON.stringify(statusHistory) !== JSON.stringify(history)
	) {
		history = statusHistory;
	}
</script>

{#if visibleHistory.length > 0 && status}
	{#if status?.hidden !== true}
		<div class="flex flex-col w-full">
			<button
				class="w-full {isCompletedVisualStatus ? 'cursor-default' : ''}"
				aria-label={$i18n.t('Toggle status history')}
				aria-expanded={isCompletedVisualStatus ? false : showHistory}
				disabled={isCompletedVisualStatus}
				on:click={() => {
					if (!isCompletedVisualStatus) showHistory = !showHistory;
				}}
			>
				<div class="flex items-start gap-2">
					<StatusItem {status} />
				</div>
			</button>

			{#if showHistory && !isCompletedVisualStatus}
				<div class="flex flex-row">
					{#if visibleHistory.length > 1}
						<div class="w-full">
							{#each visibleHistory as status, idx}
								<div class="flex items-stretch gap-2 mb-1">
									<div class="relative w-3 shrink-0">
										<span
											class="absolute left-1/2 top-[17px] flex size-1.5 -translate-x-1/2 items-center justify-center rounded-full bg-gray-500 dark:bg-gray-400"
										></span>
										{#if idx !== visibleHistory.length - 1}
											<div
												class="absolute bottom-[-20px] left-1/2 top-[24px] w-px -translate-x-1/2 bg-gray-300 dark:bg-gray-700"
											></div>
										{/if}
									</div>

									<StatusItem {status} done={true} />
								</div>
							{/each}
						</div>
					{/if}
				</div>
			{/if}
		</div>
	{/if}
{/if}
