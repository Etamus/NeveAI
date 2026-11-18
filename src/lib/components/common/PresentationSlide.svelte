<script lang="ts">
	import { getContext, onDestroy } from 'svelte';
	import ZoomSurface from './ZoomSurface.svelte';
	type Slides = Awaited<ReturnType<typeof import('$lib/utils/pptxToHtml').pptxToImages>>;
	export let presentation: Slides | null;
	export let index: number;
	const i18n = getContext('i18n');
	let surface: ZoomSurface;
	let src = '', failed = false, revision = 0;
	let timer: ReturnType<typeof setTimeout>;
	async function show(slides: Slides | null, current: number) {
		const version = ++revision;
		clearTimeout(timer);
		src = '';
		failed = false;
		if (!slides) return;
		try {
			const next = await slides.baseSlide(current);
			if (version !== revision) return;
			src = next;
			timer = setTimeout(async () => {
				for (const i of [current + 1, current - 1]) {
					if (version !== revision) break;
					if (i >= 0 && i < slides.count) await slides.baseSlide(i).catch(() => {});
				}
			}, 180);
		} catch { if (revision === version) failed = true; }
	}
	$: show(presentation, index);
	export const reset = () => surface?.reset();
	onDestroy(() => { revision++; clearTimeout(timer); });
</script>
{#if failed}
	<p role="alert" class="p-4 text-sm">{$i18n.t('Unable to preview this file.')}</p>
{:else}
	<ZoomSurface bind:this={surface} controls {src} alt={'Slide ' + (index + 1)}
		originalWidth={presentation?.width} originalHeight={presentation?.height}
		renderAt={presentation ? (scale) => presentation.renderSlide(index, scale) : undefined} />
{/if}
