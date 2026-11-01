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

	$: isPreparingFile = status?.action === 'file_generation' && !status?.done;
	$: if (isMediaStatus || isPreparingFile) {
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
			{#if isMediaStatus || isPreparingFile}
				<div class="w-full cursor-default select-none">
					<div class="flex items-start gap-2">
						<StatusItem {status} />
					</div>
				</div>
			{:else}
				<button
					class="w-full select-none text-left"
					aria-label={$i18n.t('Toggle status history')}
					aria-expanded={showHistory}
					on:click={(event) => {
						notifyChatLayout(event.currentTarget, 200, !showHistory);
						showHistory = !showHistory;
					}}
				>
					<div class="flex min-w-0 w-full items-start gap-2">
						<StatusItem {status} expanded={showHistory} />
					</div>
				</button>
			{/if}

			{#if showHistory && !isMediaStatus && !isPreparingFile}
				<div class="flex flex-row select-text" transition:slide={{ duration: 200, easing: quintOut }}>
					{#if visibleHistory.length > 1}
						<div class="ml-[7px] min-w-0 w-full border-l border-[#dedede] dark:border-[#292929] px-4">
							{#each visibleHistory as status}
								<div class="flex min-w-0 items-stretch mb-1">
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
