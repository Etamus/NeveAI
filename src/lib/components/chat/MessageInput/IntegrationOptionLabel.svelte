<script lang="ts">
	import { getContext } from 'svelte';
	import type { I18nStore } from '$lib/i18n';

	const i18n = getContext<I18nStore>('i18n');
	export let label: string;
	export let description: string;
</script>

<div class="integration-option-copy">
	<span class="integration-option-label">{$i18n.t(label)}</span>
	<span class="integration-option-description text-gray-500 dark:text-gray-400/85">{$i18n.t(description)}</span>
</div>

<style>
	.integration-option-copy {
		display: flex;
		flex: 1;
		min-width: 0;
		align-items: baseline;
		gap: 0.625rem;
		text-align: start;
	}
	.integration-option-label {
		flex-shrink: 0;
		white-space: nowrap;
	}
	.integration-option-description {
		min-width: 0;
		font-size: 14.5px;
		line-height: 1.4;
		white-space: normal;
		overflow-wrap: anywhere;
	}
	:global(button:disabled) .integration-option-description {
		color: inherit;
	}
	@media (max-width: 767px) {
		.integration-option-description { display: none; }
	}
	@container (max-width: 520px) {
		.integration-option-copy {
			flex-direction: column;
			align-items: flex-start;
			gap: 1px;
		}
	}
</style>
