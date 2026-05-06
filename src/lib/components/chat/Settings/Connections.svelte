<script lang="ts">
	export let saveSettings: Function;

	const updateHandler = async () => {
		await saveSettings({
			directConnections: {
				OPENAI_API_BASE_URLS: [],
				OPENAI_API_KEYS: [],
				OPENAI_API_CONFIGS: {}
			}
		});
	};
</script>

<form
	id="tab-connections"
	class="flex flex-col h-full justify-between text-sm"
	on:submit|preventDefault={updateHandler}
>
	<div class="overflow-y-scroll scrollbar-hidden h-full"></div>
</form>