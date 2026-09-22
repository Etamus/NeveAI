<script lang="ts">
	export let kind: 'image' | 'video' = 'image';
	export let progress = 0;
	export let width = 1;
	export let height = 1;

	$: percent = Math.min(100, Math.max(0, Math.round(Number(progress) || 0)));
	$: label = kind === 'video' ? 'Criando vídeo' : 'Criando imagem';
	$: safeWidth = kind === 'video' ? 16 : Math.max(1, Number(width) || 1);
	$: safeHeight = kind === 'video' ? 9 : Math.max(1, Number(height) || 1);
	$: aspectRatio = safeWidth / safeHeight;
	$: displayWidth = Math.min(26, 26 * aspectRatio);
</script>

<div
	class="relative overflow-hidden rounded-lg bg-gray-50/35 backdrop-blur-sm dark:bg-gray-900/45 {kind ===
	'video'
		? 'aspect-video w-full max-w-[32rem] self-start'
		: 'w-full'}"
	style={kind === 'video'
		? undefined
		: `aspect-ratio: ${safeWidth} / ${safeHeight}; width: min(100%, ${displayWidth}rem); max-height: 26rem;`}
	role="progressbar"
	aria-label={label}
	aria-valuemin="0"
	aria-valuemax="100"
	aria-valuenow={percent}
>
	<div class="absolute inset-0 flex flex-col items-center justify-center gap-1.5">
		<span class="text-2xl font-medium tabular-nums text-gray-700 dark:text-gray-200">{percent}%</span>
	</div>
</div>
