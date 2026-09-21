<script lang="ts">
	export let kind: 'image' | 'video' = 'image';
	export let progress = 0;
	export let widescreen = false;

	$: percent = Math.min(100, Math.max(0, Math.round(Number(progress) || 0)));
	$: label = kind === 'video' ? 'Criando vídeo' : 'Criando imagem';
</script>

<div
	class="relative w-full overflow-hidden rounded-lg border border-gray-200/80 bg-gray-50 shadow-sm dark:border-gray-700/70 dark:bg-gray-800/55 {kind ===
	'video' || widescreen
		? 'aspect-video max-w-[32rem]'
		: 'aspect-square max-w-[26rem]'}"
	role="progressbar"
	aria-label={label}
	aria-valuemin="0"
	aria-valuemax="100"
	aria-valuenow={percent}
>
	<div class="absolute inset-0 flex flex-col items-center justify-center gap-1.5">
		<span class="text-2xl font-medium tabular-nums text-gray-700 dark:text-gray-200">{percent}%</span>
	</div>

	<div class="absolute inset-x-3 bottom-3 h-1 overflow-hidden rounded-full bg-gray-200 dark:bg-gray-700">
		<div
			class="h-full rounded-full bg-gray-700 transition-[width] duration-300 ease-out dark:bg-gray-200"
			style="width: {percent}%"
		></div>
	</div>
</div>
