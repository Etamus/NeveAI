<script lang="ts">
	import { onMount, getContext } from 'svelte';
	import { NEVEAI_NAME, showSidebar, functions, config, user } from '$lib/stores';
	import { goto } from '$app/navigation';

	const i18n = getContext('i18n');

	let loaded = false;

	onMount(async () => {
		if (
			!(
				($config?.features?.enable_notes ?? false) &&
				($user?.role === 'admin' || ($user?.permissions?.features?.notes ?? true))
			)
		) {
			// If the feature is not enabled, redirect to the home page
			goto('/');
		}

		loaded = true;
	});
</script>

<svelte:head>
	<title>
		{$i18n.t('Notes')} • {$NEVEAI_NAME}
	</title>
</svelte:head>

{#if loaded}
	<slot />
{/if}
