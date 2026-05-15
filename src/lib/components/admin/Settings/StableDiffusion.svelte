<script lang="ts">
	import { toast } from 'svelte-sonner';
	import { onMount, getContext } from 'svelte';
	import { getSDConfig, updateSDConfig } from '$lib/apis/stable-diffusion';

	import Switch from '$lib/components/common/Switch.svelte';

	const i18n = getContext('i18n');

	export let saveHandler: Function;

	let config = null;

	const submitHandler = async () => {
		const res = await updateSDConfig(localStorage.token, config);
	};

	onMount(async () => {
		const res = await getSDConfig(localStorage.token);

		if (res) {
			config = res;
		}
	});
</script>

<form
	class="flex flex-col h-full justify-between space-y-3 text-sm"
	on:submit|preventDefault={async () => {
		await submitHandler();
		saveHandler();
	}}
>
	<div class=" space-y-3 overflow-y-scroll scrollbar-hidden h-full">
		{#if config}
			<div>
				<div class="mb-3.5">
					<div class=" mt-0.5 mb-2.5 text-base font-medium">{$i18n.t('Geral')}</div>

					<hr class=" border-gray-100/30 dark:border-gray-850/30 my-2" />

					<div class="mb-2.5">
						<div class=" flex w-full justify-between">
							<div class=" self-center text-xs font-medium">
								{$i18n.t('Ativar Stable Diffusion')}
							</div>

							<Switch bind:state={config.ENABLE_STABLE_DIFFUSION} />
						</div>
					</div>

					{#if config.is_loaded}
						<div class="mb-2.5">
							<div class="flex items-center gap-2 text-xs text-green-500">
								<div class="w-2 h-2 rounded-full bg-green-500"></div>
								{$i18n.t('Pipeline carregado')}
							</div>
						</div>
					{/if}
				</div>

				<div class="mb-3.5">
					<div class=" mt-0.5 mb-2.5 text-base font-medium">{$i18n.t('Configuração')}</div>

					<hr class=" border-gray-100/30 dark:border-gray-850/30 my-2" />

					<div class="mb-2.5">
						<div class="flex w-full justify-between">
							<div class=" self-center text-xs font-medium">{$i18n.t('Modelo')}</div>
							<div class="flex items-center relative">
								<input
									class="w-60 rounded-sm px-2 p-1 text-xs bg-transparent outline-hidden text-right"
									type="text"
									bind:value={config.STABLE_DIFFUSION_MODEL}
									placeholder="leejet/Z-Image-Turbo-GGUF"
								/>
							</div>
						</div>
					</div>

					<div class="mb-2.5">
						<div class="flex w-full justify-between">
							<div class=" self-center text-xs font-medium">{$i18n.t('Largura')}</div>
							<div class="flex items-center relative">
								<input
									class="w-20 rounded-sm px-2 p-1 text-xs bg-transparent outline-hidden text-right"
									type="number"
									min="256"
									max="768"
									step="64"
									bind:value={config.STABLE_DIFFUSION_WIDTH}
								/>
							</div>
						</div>
					</div>

					<div class="mb-2.5">
						<div class="flex w-full justify-between">
							<div class=" self-center text-xs font-medium">{$i18n.t('Altura')}</div>
							<div class="flex items-center relative">
								<input
									class="w-20 rounded-sm px-2 p-1 text-xs bg-transparent outline-hidden text-right"
									type="number"
									min="256"
									max="768"
									step="64"
									bind:value={config.STABLE_DIFFUSION_HEIGHT}
								/>
							</div>
						</div>
					</div>

					<div class="mb-2.5">
						<div class="flex w-full justify-between">
							<div class=" self-center text-xs font-medium">{$i18n.t('Passos')}</div>
							<div class="flex items-center relative">
								<input
									class="w-20 rounded-sm px-2 p-1 text-xs bg-transparent outline-hidden text-right"
									type="number"
									min="1"
									max="8"
									bind:value={config.STABLE_DIFFUSION_STEPS}
								/>
							</div>
						</div>
					</div>

					<div class="mb-2.5">
						<div class="flex w-full justify-between">
							<div class=" self-center text-xs font-medium">{$i18n.t('Escala de Guia')}</div>
							<div class="flex items-center relative">
								<input
									class="w-20 rounded-sm px-2 p-1 text-xs bg-transparent outline-hidden text-right"
									type="number"
									min="1"
									max="1"
									step="0.1"
									bind:value={config.STABLE_DIFFUSION_GUIDANCE_SCALE}
								/>
							</div>
						</div>
						<div class="text-gray-500 text-xs mt-1">
							{$i18n.t('Z-Image-Turbo usa CFG 1.0 no stable-diffusion.cpp para melhor velocidade e consistência.')}
						</div>
					</div>
				</div>
			</div>
		{/if}
	</div>

	<div class="flex justify-end pt-3">
		<button
			class="px-3.5 py-1.5 text-sm font-medium bg-black hover:bg-gray-900 text-white dark:bg-white dark:text-black dark:hover:bg-gray-100 transition rounded-full"
			type="submit"
		>
			{$i18n.t('Salvar')}
		</button>
	</div>
</form>
