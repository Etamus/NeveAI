<script lang="ts">
	import { toast } from 'svelte-sonner';
	import { createEventDispatcher, onMount, getContext } from 'svelte';

	const dispatch = createEventDispatcher();
	const i18n = getContext('i18n');

	import { getModels as _getModels, getBackendConfig } from '$lib/apis';
	import { getConnectionsConfig, setConnectionsConfig } from '$lib/apis/configs';
	import { config, models, user } from '$lib/stores';

	import Switch from '$lib/components/common/Switch.svelte';
	import Spinner from '$lib/components/common/Spinner.svelte';

	const getModels = async () => {
		return await _getModels(localStorage.token, null, false, true);
	};

	let connectionsConfig: any = null;

	const updateConnectionsHandler = async () => {
		const res = await setConnectionsConfig(localStorage.token, {
			...connectionsConfig,
			ENABLE_DIRECT_CONNECTIONS: false
		}).catch((error) => {
			toast.error(`${error}`);
		});

		if (res) {
			connectionsConfig = res;
			connectionsConfig.ENABLE_DIRECT_CONNECTIONS = false;
			await models.set(await getModels());
			await config.set(await getBackendConfig());
		}
	};

	onMount(async () => {
		if ($user?.role === 'admin') {
			connectionsConfig = await getConnectionsConfig(localStorage.token);
			connectionsConfig.ENABLE_DIRECT_CONNECTIONS = false;
		}
	});

	const submitHandler = async () => {
		await updateConnectionsHandler();
		dispatch('save');
		await config.set(await getBackendConfig());
	};
</script>

<form class="flex flex-col h-full justify-between text-sm" on:submit|preventDefault={submitHandler}>
	<div class="overflow-y-scroll scrollbar-hidden h-full">
		{#if connectionsConfig !== null}
			<div class="mb-3.5">
				<div class="mt-0.5 mb-2.5 text-base font-medium">{$i18n.t('General')}</div>

				<hr class="border-gray-100/30 dark:border-gray-850/30 my-2" />

				<div class="my-2">
					<div class="flex justify-between items-center text-sm">
						<div class="text-xs font-medium">{$i18n.t('Cache Base Model List')}</div>

						<div class="flex items-center">
							<Switch
								bind:state={connectionsConfig.ENABLE_BASE_MODELS_CACHE}
								on:change={async () => {
									updateConnectionsHandler();
								}}
							/>
						</div>
					</div>

					<div class="mt-1 text-xs text-gray-400 dark:text-gray-500">
						{$i18n.t(
							'Base Model List Cache speeds up access by fetching base models only at startup or on settings save—faster, but may not show recent base model changes.'
						)}
					</div>
				</div>
			</div>
		{:else}
			<div class="flex h-full justify-center">
				<div class="my-auto">
					<Spinner className="size-6" />
				</div>
			</div>
		{/if}
	</div>

	<div class="flex justify-end pt-3 text-sm font-medium">
		<button
			class="px-3.5 py-1.5 text-sm font-medium bg-black hover:bg-gray-900 text-white dark:bg-white dark:text-black dark:hover:bg-gray-100 transition rounded-full"
			type="submit"
		>
			{$i18n.t('Save')}
		</button>
	</div>
</form>
