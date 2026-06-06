<script lang="ts">
	import LocalModels from '$lib/components/workspace/LocalModels.svelte';
	import { NEVEAI_NAME } from '$lib/stores';
	import i18n from '$lib/i18n';
</script>

<svelte:head>
	<title>{$i18n.t('Models')} • {$NEVEAI_NAME}</title>
</svelte:head>

<LocalModels />
