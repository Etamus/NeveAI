<script lang="ts">
	import { getContext, onDestroy } from 'svelte';
	import panzoom, { type PanZoom } from 'panzoom';
	import OrbitingSpheres from './OrbitingSpheres.svelte';
	import Minus from '../icons/Minus.svelte';
	import Plus from '../icons/Plus.svelte';

	export let src = '';
	export let alt = '';
	export let controls = false;
	export let imageClass = '';
	export let renderAt: ((scale: number) => Promise<string>) | undefined = undefined;
	export let originalWidth = 0;
	export let originalHeight = 0;
	const i18n = getContext('i18n');
	let viewport: HTMLDivElement;
	let controller: PanZoom;
	let zoom = 1;
	let sharp = '';
	let resolution = 1;
	let revision = 0;
	let timer: ReturnType<typeof setTimeout>;
	let disposed = false;

	function sharpen() {
		if (!renderAt || !viewport || !originalWidth || !originalHeight) return;
		const scale = Math.min(viewport.clientWidth / originalWidth, viewport.clientHeight / originalHeight)
			* Math.max(2, zoom * (window.devicePixelRatio || 1));
		const target = Math.min(Math.ceil(scale * 2) / 2, Math.sqrt(8_000_000 / (originalWidth * originalHeight)));
		const version = ++revision;
		clearTimeout(timer);
		if (target <= resolution) return;
		timer = setTimeout(async () => {
			try {
				const next = await renderAt!(target);
				const img = new Image();
				img.src = next;
				await img.decode();
				if (!disposed && revision === version) { sharp = next; resolution = target; }
			} catch { /* The original slide remains available. */ }
		}, 100);
	}

	$: if (src && originalWidth && renderAt) sharpen();

	function scene(node: HTMLElement) {
		controller = panzoom(node, { bounds: true, boundsPadding: 1, minZoom: 1, maxZoom: 8,
			smoothScroll: false, zoomSpeed: 0.065, disableKeyboardInteraction: true });
		controller.on('zoom', () => { zoom = controller.getTransform().scale; sharpen(); });
		const observer = new ResizeObserver(sharpen);
		observer.observe(node);
		return { destroy() { observer.disconnect(); controller.dispose(); } };
	}
	function scaleBy(factor: number) {
		controller.zoomTo(viewport.clientWidth / 2, viewport.clientHeight / 2, factor);
	}
	export function reset() {
		controller?.zoomAbs(0, 0, 1);
		controller?.moveTo(0, 0);
	}
	onDestroy(() => { disposed = true; clearTimeout(timer); });
</script>

<div class="relative h-full w-full min-h-0 overflow-hidden" bind:this={viewport}>
	<div class="absolute inset-0 overflow-hidden">
		<div use:scene class="flex h-full w-full items-center justify-center">
			{#if src}<img src={sharp || src} {alt} draggable="false" class="block max-h-full max-w-full select-none object-contain {controls ? 'size-full' : ''} {imageClass}" />{:else}<OrbitingSpheres className="size-5" />{/if}
		</div>
	</div>
	{#if controls}
		<div class="absolute bottom-3 left-1/2 z-10 flex -translate-x-1/2 items-center gap-0.5 rounded-lg border border-gray-200/60 bg-white/90 px-1 py-0.5 text-gray-500 shadow-lg dark:border-gray-700/60 dark:bg-gray-850/90 dark:text-gray-400">
			<button type="button" class="rounded-md p-1.5 hover:bg-black/5 dark:hover:bg-white/5" aria-label={$i18n.t('Zoom out')} on:click={() => scaleBy(0.8)}><Minus className="size-3.5" /></button>
			<button type="button" class="min-w-12 rounded-md px-1.5 py-1 text-[11px] tabular-nums hover:bg-black/5 dark:hover:bg-white/5" aria-label={$i18n.t('Reset zoom')} on:click={reset}>{Math.round(zoom * 100)}%</button>
			<button type="button" class="rounded-md p-1.5 hover:bg-black/5 dark:hover:bg-white/5" aria-label={$i18n.t('Zoom in')} on:click={() => scaleBy(1.25)}><Plus className="size-3.5" /></button>
		</div>
	{/if}
</div>
