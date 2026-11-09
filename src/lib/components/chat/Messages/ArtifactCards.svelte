<script lang="ts">
	import { getContext } from 'svelte';
	import { extractArtifactResults } from '$lib/utils/artifactResults';
	import { openArtifactPreview, downloadArtifact } from '$lib/utils/artifactPreview';
	import CodeBracket from '$lib/components/icons/CodeBracket.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	const i18n = getContext<any>('i18n');
	export let content = '';
	export let messageId = '';
	export let done = false;
	export let history: any;
	$: artifacts = done ? extractArtifactResults(content, messageId) : [];
</script>

{#if artifacts.length}
	<div class="mt-3 mb-5 flex w-full flex-col gap-2" data-artifact-results>
		{#each artifacts as artifact (artifact.id)}
			<div class="relative group w-full max-w-[30rem]">
				<button
					type="button"
					class="flex h-12 w-full items-center gap-2.5 rounded-lg bg-gray-100 px-3 pr-44 text-left text-gray-800 transition hover:bg-gray-200/80 dark:bg-gray-800 dark:text-gray-100 dark:hover:bg-gray-700"
					on:click={() => openArtifactPreview(artifact, history)}
					aria-label={`${$i18n.t('Artifact preview')}: ${artifact.filename}`}
				>
					<div class="flex size-7 shrink-0 items-center justify-center">
						<CodeBracket className="size-4.5" />
					</div>
					<div class="min-w-0 flex-1 truncate text-sm font-normal">{artifact.filename}</div>
				</button>
				<div class="absolute right-3 top-1/2 flex -translate-y-1/2 items-center gap-1">
					<button
						type="button"
						class="flex h-7 items-center justify-center rounded-md px-2 text-xs text-gray-600 transition hover:bg-black/5 hover:text-gray-900 dark:text-gray-300 dark:hover:bg-white/10 dark:hover:text-white"
						on:click={() => openArtifactPreview(artifact, history)}>{$i18n.t('Artifact preview')}</button
					>
					<Tooltip content={$i18n.t('Download')}
						><button
							type="button"
							aria-label={`${$i18n.t('Download')}: ${artifact.filename}`}
							class="flex size-7 items-center justify-center rounded-md text-gray-600 transition hover:bg-black/5 hover:text-gray-900 dark:text-gray-300 dark:hover:bg-white/10 dark:hover:text-white"
							on:click={() => downloadArtifact(artifact)}><svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" class="size-[18px]"><path stroke-linecap="round" stroke-linejoin="round" d="M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2M7 11l5 5 5-5M12 4v12"/></svg></button
						></Tooltip
					>
				</div>
			</div>
		{/each}
	</div>
{/if}
