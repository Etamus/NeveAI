<script>
	import { slide } from 'svelte/transition';
	import { quintOut } from 'svelte/easing';
	import { notifyChatLayout } from '$lib/utils/notifyChatLayout';
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

	$: visibleHistory = (history ?? [])
		.filter((item) => item?.hidden !== true && !isQueryingStatus(item))
		.reduce((items, item) => {
			const previous = items.at(-1);
			if (
				previous?.action === item?.action &&
				previous?.description === item?.description
			) {
				items[items.length - 1] = item;
			} else {
				items.push(item);
			}
			return items;
		}, []);
	$: status = visibleHistory.at(-1) ?? null;
	$: isMediaStatus =
		['stable_diffusion', 'video_generation', 'music_generation'].includes(
			String(status?.action ?? '').trim().toLowerCase()
		);

	$: if (isMediaStatus) {
		showHistory = false;
	}

	$: if (
		(statusHistory?.length ?? 0) !== history.length ||
		JSON.stringify(statusHistory ?? []) !== JSON.stringify(history)
	) {
		history = statusHistory ?? [];
	}
</script>

{#if visibleHistory.length > 0 && status}
	{#if status?.hidden !== true}
		<div class="flex flex-col w-full">
			{#if isMediaStatus}
				<div class="w-full cursor-default select-none">
					<div class="flex items-start gap-2">
						<StatusItem {status} />
					</div>
				</div>
			{:else}
				<button
					class="w-full select-none"
					aria-label={$i18n.t('Toggle status history')}
					aria-expanded={showHistory}
					on:click={(event) => {
						notifyChatLayout(event.currentTarget, 200, !showHistory);
						showHistory = !showHistory;
					}}
				>
					<div class="flex items-start gap-2">
						<StatusItem {status} />
					</div>
				</button>
			{/if}

			{#if showHistory && !isMediaStatus}
				<div class="flex flex-row select-text" transition:slide={{ duration: 200, easing: quintOut }}>
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
