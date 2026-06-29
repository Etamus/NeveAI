<script lang="ts">
	export let name = 'Modelo';
	export let progress = 0;
	export let label = '';
	export let cancelling = false;
	export let onCancel: () => void = () => {};

	$: percent = Math.min(100, Math.max(0, Math.round((progress || 0) * 100)));
</script>

<div
	class="pointer-events-auto w-[20.75rem] -translate-x-1 translate-y-5 rounded-xl border border-gray-200 bg-white px-4 py-3 text-gray-900 shadow-lg dark:border-gray-800 dark:bg-gray-900 dark:text-gray-100"
>
	<div class="flex min-w-0 items-start gap-3">
		<div class="min-w-0 flex-1">
			<div class="truncate text-sm font-medium">{name}</div>
		</div>

		<button
			type="button"
			class="shrink-0 rounded-md px-0 py-0.5 text-xs font-medium text-gray-500 transition hover:text-gray-900 disabled:cursor-default disabled:opacity-40 dark:text-gray-400 dark:hover:text-gray-100"
			disabled={cancelling}
			on:click={onCancel}
		>
			{cancelling ? 'Cancelando...' : 'Cancelar'}
		</button>
	</div>

	<div class="mt-1 flex items-center justify-between gap-3 text-xs text-gray-500 dark:text-gray-400">
		<span class="truncate">{label || 'Preparando download...'}</span>
		<span class="shrink-0 text-right">{percent}%</span>
	</div>

	<div class="mt-2 h-1.5 overflow-hidden rounded-full bg-gray-100 dark:bg-gray-800">
		<div class="h-full rounded-full bg-black transition-all dark:bg-white" style="width: {percent}%"></div>
	</div>
</div>

<style>
	:global([data-sonner-toast].neve-download-progress-toast-shell) {
		pointer-events: none;
		overflow-wrap: normal;
	}
</style>
