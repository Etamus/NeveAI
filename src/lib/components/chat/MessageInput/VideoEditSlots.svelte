<script lang="ts">
	import { getContext } from 'svelte';
	import AttachmentRemoveButton from '$lib/components/common/AttachmentRemoveButton.svelte';
	import OrbitingSpheres from '$lib/components/common/OrbitingSpheres.svelte';
	import Settings from '$lib/components/icons/Settings.svelte';
	import Upload from '$lib/components/icons/Upload.svelte';
	import { videoEditMediaUrl, type EditAsset } from '$lib/utils/videoEdit';
	import type { I18nStore } from '$lib/i18n';
	import { attachmentScroller } from '$lib/utils/attachmentScroll';

	const i18n = getContext<I18nStore>('i18n');
	export let asset: EditAsset | undefined;
	export let busy = false;
	export let onImport: (files: File[]) => Promise<void>;
	export let onEdit: () => void;
	export let onRemove: () => void;
	let input: HTMLInputElement;

	async function choose() {
		const files = Array.from(input.files ?? []);
		input.value = '';
		await onImport(files);
	}
</script>

<input bind:this={input} type="file" accept="video/*,.mkv,.avi,.mov,.webm,.mts,.m2ts" aria-label={$i18n.t('Import video')} hidden on:change={choose} />
<div data-video-edit-slots class="image-swap-slots composer-attachment-strip image-role-attachments single-image-attachment mx-2 mt-2.5 mb-1 flex min-w-0 max-w-full items-start gap-2 overflow-x-auto overflow-y-hidden px-1 pt-1 pb-1" use:attachmentScroller>
	<div class="group group/attachment relative h-[62px] w-[146px] shrink-0 rounded-md border border-dashed border-gray-300 dark:border-gray-700">
		<button type="button" class="flex size-full items-center gap-2 rounded-md px-2 text-left hover:bg-gray-100 dark:hover:bg-gray-800"
			disabled={busy} on:click={() => input.click()} aria-label={$i18n.t('Import video')}>
			<span class="grid size-10 shrink-0 place-items-center overflow-hidden rounded text-gray-400">
				{#if busy}<OrbitingSpheres className="size-4" />
				{:else if asset}<img class="size-full object-cover" src={videoEditMediaUrl(asset.id) + '/thumbnail'} alt="" />
				{:else}<Upload className="size-4" />{/if}
			</span>
			<span class="min-w-0 truncate text-xs text-gray-600 dark:text-gray-300">{asset?.name ?? $i18n.t('Adicionar')}</span>
		</button>
		{#if asset}<AttachmentRemoveButton framed={true} topOffset="-top-0.5" disabled={busy} label={$i18n.t('Remove')} on:click={onRemove} />{/if}
	</div>
	<button type="button" data-video-mode-edit disabled={busy} aria-label={$i18n.t('Open Neve Studio')} on:click={onEdit}
		class="grid h-[62px] w-[62px] shrink-0 place-items-center rounded-md border border-dashed border-gray-300 text-gray-500 hover:bg-gray-100 dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-800">
		<Settings className="size-4.5" />
	</button>
</div>
