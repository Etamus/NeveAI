<script lang="ts">
	import { getContext } from 'svelte';
	import { mobile } from '$lib/stores';
	import ChevronLeft from '$lib/components/icons/ChevronLeft.svelte';
	const i18n = getContext('i18n');
	export let onBack: (() => void) | undefined = getContext('mobile-modal-back');
	export let contentClass = '';
</script>

{#if $mobile}
	<span class="mobile-modal-title">
		<button type="button" class="mobile-modal-back" aria-label={$i18n.t('Back')} on:click={() => onBack?.()}>
			<ChevronLeft className="size-5" />
		</button>
		<span class="mobile-modal-title-content {contentClass}"><slot /></span>
	</span>
{:else}
	<slot />
{/if}

<style>
	.mobile-modal-title { display: flex; min-width: 0; align-items: center; gap: 8px; }
	.mobile-modal-back { display: inline-flex; width: 36px; height: 36px; padding: 0; flex: 0 0 36px; align-items: center; justify-content: center; border-radius: 6px; }
	.mobile-modal-back:hover { background: rgb(128 128 128 / 12%); }
	.mobile-modal-title-content { min-width: 0; flex: 1; }
</style>
