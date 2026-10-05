<script lang="ts">
	import { toast } from 'svelte-sonner';

	import { getContext } from 'svelte';

	import { settings } from '$lib/stores';
	import { NEVEAI_API_BASE_URL } from '$lib/constants';

	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import { copyToClipboard } from '$lib/utils';
	import CheckCircle from '$lib/components/icons/CheckCircle.svelte';
	import Bookmark from '$lib/components/icons/Bookmark.svelte';
	import Tag from '$lib/components/icons/Tag.svelte';
	import Label from '$lib/components/icons/Label.svelte';

	const i18n = getContext('i18n');

	export let selectedModelIdx: number = -1;
	export let keyboardNavigation = false;
	export let item: any = {};
	export let index: number = -1;
	export let value: string = '';
	export let profileImageUrl: string = '';

	export let favoriteModelHandler: (modelId: string) => void = () => {};
	export let reorderEnabled = false;

	export let onClick: () => void = () => {};

	$: modelDescription =
		typeof item?.model?.info?.meta?.description === 'string'
			? item.model.info.meta.description.trim()
			: '';
	$: modelDescriptionPreview = modelDescription.length > 35
		? `${modelDescription.slice(0, 34).trimEnd()}\u2026`
		: modelDescription;

	const getModelImageVersion = (model: any) =>
		model?.updated_at ?? model?.info?.updated_at ?? model?.meta?.updated_at ?? '';
	const getModelProfileImageUrl = (model: any, lang = '') => {
		const params = new URLSearchParams({ id: model?.id ?? '' });
		if (lang) params.set('lang', lang);
		const version = getModelImageVersion(model);
		if (version) params.set('v', `${version}`);
		return `${NEVEAI_API_BASE_URL}/models/model/profile/image?${params.toString()}`;
	};

	const copyLinkHandler = async (model) => {
		const baseUrl = window.location.origin;
		const res = await copyToClipboard(`${baseUrl}/?model=${encodeURIComponent(model.id)}`);

		if (res) {
			toast.success($i18n.t('Copied link to clipboard'));
		} else {
			toast.error($i18n.t('Failed to copy link'));
		}
	};
</script>

<button
	role="option"
	aria-selected={value === item.value}
	aria-label={$i18n.t('Select {{modelName}} model', { modelName: item.label })}
	class="flex group/item h-14 shrink-0 w-full text-left font-normal select-none items-center rounded-lg py-2 pl-3 pr-1.5 text-sm text-gray-700 dark:text-gray-100 outline-hidden transition-all duration-75 hover:bg-gray-100 dark:hover:bg-gray-800 cursor-pointer data-highlighted:bg-muted {value === item.value
		? 'bg-gray-100 dark:bg-gray-700/60'
		: ''} {keyboardNavigation && index === selectedModelIdx && value !== item.value ? 'ring-1 ring-inset ring-gray-300 dark:ring-gray-600' : ''} {reorderEnabled ? 'cursor-grab active:cursor-grabbing' : ''}"
	data-model-selector-row="true"
	data-arrow-selected={index === selectedModelIdx}
	data-value={item.value}
	on:click={() => {
		onClick();
	}}
>
	<div class="flex min-w-0 flex-col flex-1 gap-1.5">
		<!-- {#if (item?.model?.tags ?? []).length > 0}
			<div
				class="flex gap-0.5 self-center items-start h-full w-full translate-y-[0.5px] overflow-x-auto scrollbar-none"
			>
				{#each item.model?.tags.sort((a, b) => a.name.localeCompare(b.name)) as tag}
					<Tooltip content={tag.name} className="flex-shrink-0">
						<div
							class=" text-xs font-semibold px-1 rounded-sm uppercase bg-gray-500/20 text-gray-700 dark:text-gray-200"
						>
							{tag.name}
						</div>
					</Tooltip>
				{/each}
			</div>
		{/if} -->

		<div class="flex min-w-0 items-center gap-3">
			<div class="flex items-center min-w-fit relative group/favorite">
				<img
					src={profileImageUrl || getModelProfileImageUrl(item.model, $i18n.language)}
					alt={$i18n.t('{{modelName}} profile image', { modelName: item.label })}
					class="rounded-full size-7 flex items-center group-hover/favorite:opacity-0 transition-opacity"
					loading="eager"
					decoding="async"
				/>
				<div
					role="button"
					tabindex="0"
					aria-label={$i18n.t(($settings?.favoriteModels ?? []).includes(item.model.id) ? 'Remove from favorites' : 'Add to favorites')}
					title={$i18n.t(($settings?.favoriteModels ?? []).includes(item.model.id) ? 'Remove from favorites' : 'Add to favorites')}
					aria-pressed={($settings?.favoriteModels ?? []).includes(item.model.id)}
					class="absolute inset-0 size-7 rounded-full flex items-center justify-center opacity-0 group-hover/favorite:opacity-100 focus-visible:opacity-100 focus-visible:bg-gray-100 dark:focus-visible:bg-gray-800 transition-opacity text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 cursor-pointer"
					on:pointerdown|stopPropagation
					on:keydown|stopPropagation={(event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); favoriteModelHandler(item.model.id); } }}
					on:click|stopPropagation|preventDefault={() => favoriteModelHandler(item.model.id)}
				>
					<Bookmark className="size-3.5 {($settings?.favoriteModels ?? []).includes(item.model.id) ? 'fill-current' : ''}" />
				</div>
			</div>

			<div class="min-w-0 flex-1">
				<div class="truncate dark:text-white dark:font-medium">{item.label}</div>
				{#if modelDescription}
					<div class="mt-0.5 max-w-[32ch] truncate text-xs font-normal text-gray-500 dark:text-gray-400" title={modelDescription}>
						{modelDescriptionPreview}
					</div>
				{/if}
			</div>

			<div class=" shrink-0 flex items-center gap-2">
				<!-- {JSON.stringify(item.info)} -->

				{#if (item?.model?.tags ?? []).length > 0}
					{#key item.model.id}
						<Tooltip elementId="tags-{item.model.id}">
							<div slot="tooltip" id="tags-{item.model.id}">
								{#each item.model?.tags.sort((a, b) => a.name.localeCompare(b.name)) as tag}
									<Tooltip content={tag.name} className="flex-shrink-0">
										<div class=" text-xs font-medium rounded-sm uppercase text-white">
											{tag.name}
										</div>
									</Tooltip>
								{/each}
							</div>

							<div class="translate-y-[1px]">
								<Tag />
							</div>
						</Tooltip>
					{/key}
				{/if}

				{#if item.model?.direct}
					<Tooltip content={`${$i18n.t('Direct')}`}>
						<div class="translate-y-[1px]">
							<svg
								xmlns="http://www.w3.org/2000/svg"
								viewBox="0 0 16 16"
								fill="currentColor"
								class="size-3"
							>
								<path
									fill-rule="evenodd"
									d="M2 2.75A.75.75 0 0 1 2.75 2C8.963 2 14 7.037 14 13.25a.75.75 0 0 1-1.5 0c0-5.385-4.365-9.75-9.75-9.75A.75.75 0 0 1 2 2.75Zm0 4.5a.75.75 0 0 1 .75-.75 6.75 6.75 0 0 1 6.75 6.75.75.75 0 0 1-1.5 0C8 10.35 5.65 8 2.75 8A.75.75 0 0 1 2 7.25ZM3.5 11a1.5 1.5 0 1 0 0 3 1.5 1.5 0 0 0 0-3Z"
									clip-rule="evenodd"
								/>
							</svg>
						</div>
					</Tooltip>
				{:else if item.model.connection_type === 'external'}
					<Tooltip content={`${$i18n.t('External')}`}>
						<div class="translate-y-[1px]">
							<svg
								xmlns="http://www.w3.org/2000/svg"
								viewBox="0 0 16 16"
								fill="currentColor"
								class="size-3"
							>
								<path
									fill-rule="evenodd"
									d="M8.914 6.025a.75.75 0 0 1 1.06 0 3.5 3.5 0 0 1 0 4.95l-2 2a3.5 3.5 0 0 1-5.396-4.402.75.75 0 0 1 1.251.827 2 2 0 0 0 3.085 2.514l2-2a2 2 0 0 0 0-2.828.75.75 0 0 1 0-1.06Z"
									clip-rule="evenodd"
								/>
								<path
									fill-rule="evenodd"
									d="M7.086 9.975a.75.75 0 0 1-1.06 0 3.5 3.5 0 0 1 0-4.95l2-2a3.5 3.5 0 0 1 5.396 4.402.75.75 0 0 1-1.251-.827 2 2 0 0 0-3.085-2.514l-2 2a2 2 0 0 0 0 2.828.75.75 0 0 1 0 1.06Z"
									clip-rule="evenodd"
								/>
							</svg>
						</div>
					</Tooltip>
				{/if}

			</div>
		</div>
	</div>

	<div class="ml-auto w-7 pl-2 pr-1 flex justify-end items-center gap-1.5 shrink-0">
		{#if value === item.value}
			<div>
				<CheckCircle className="size-4" strokeWidth="1.7" />
			</div>
		{/if}
	</div>
</button>
