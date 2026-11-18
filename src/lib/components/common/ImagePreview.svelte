<script lang="ts">
	import { getContext } from 'svelte';
	import ZoomSurface from './ZoomSurface.svelte';

	import { downloadChatFile } from '$lib/utils/chatFileSave';

	import XMark from '$lib/components/icons/XMark.svelte';

	export let show = false;
	export let src = '';
	export let alt = '';
	export let originalSrc = '';

	const i18n = getContext('i18n');

	let extension: string | null = null;
	function resolveExtension(url: string, original: string) {
		const entry = performance.getEntriesByName(new URL(url, document.baseURI).href).at(-1) as (PerformanceResourceTiming & { contentType?: string }) | undefined;
		const mime = /^data:(image\/[^;,]+)/i.exec(original || url)?.[1] || entry?.contentType || '';
		return /^image\/([a-z0-9-]+)/i.exec(mime)?.[1] || /\.(png|jpe?g|gif|webp|avif|svg|bmp)(?:$|[?#])/i.exec(original || url)?.[1];
	}

	function prepareFilename(node: HTMLElement, initial: { url: string; original: string }) {
		let probe: AbortController;
		const update = ({ url, original }: typeof initial) => {
			probe?.abort();
			probe = new AbortController();
			const signal = probe.signal;
			extension = resolveExtension(url, original) ?? null;
			if (extension) return;
			// Opaque URLs sometimes lack a file name. Resolve headers on open, never during the save gesture.
			void fetch(url, { method: url.startsWith('blob:') ? 'GET' : 'HEAD', signal })
				.then(response => {
					if (!signal.aborted) extension = /^image\/([a-z0-9-]+)/i.exec(response.headers.get('content-type') || '')?.[1] || '';
					return response.body?.cancel();
				})
				.catch(() => { if (!signal.aborted) extension = ''; });
		};
		update(initial);
		return { update, destroy() { probe.abort(); } };
	}

	function downloadImage() {
		const base = $i18n.t('Generated Image').toLowerCase().replace(/ /g, '_');
		return downloadChatFile(extension ? `${base}.${extension}` : base, () => fetch(src));
	}
	function portal(node: HTMLElement) {
		const overflow = document.body.style.overflow;
		document.body.appendChild(node);
		document.body.style.overflow = 'hidden';
		const close = (event: KeyboardEvent) => { if (event.key === 'Escape') show = false; };
		window.addEventListener('keydown', close);
		return { destroy() { window.removeEventListener('keydown', close); document.body.style.overflow = overflow; node.remove(); } };
	}
</script>

{#if show}
	<!-- svelte-ignore a11y-click-events-have-key-events -->
	<!-- svelte-ignore a11y-no-static-element-interactions -->
	<div
		use:portal
		use:prepareFilename={{url: src, original: originalSrc}}
		class="file-preview-immersive modal fixed top-0 right-0 left-0 bottom-0 bg-black text-white w-full min-h-screen h-screen flex justify-center z-9999 overflow-hidden overscroll-contain"
	>
		<div class="file-preview-header absolute left-0 w-full select-none z-20">
			<div class="ml-auto flex items-center gap-2">
				<button
					class="grid size-8 place-items-center rounded-md hover:bg-gray-800"
					aria-label={$i18n.t('Download')}
					on:click={downloadImage}
				>
					<svg
						xmlns="http://www.w3.org/2000/svg"
						viewBox="0 0 20 20"
						fill="currentColor"
						class="size-4"
					>
						<path
							d="M10.75 2.75a.75.75 0 0 0-1.5 0v8.614L6.295 8.235a.75.75 0 1 0-1.09 1.03l4.25 4.5a.75.75 0 0 0 1.09 0l4.25-4.5a.75.75 0 0 0-1.09-1.03l-2.955 3.129V2.75Z"
						/>
						<path
							d="M3.5 12.75a.75.75 0 0 0-1.5 0v2.5A2.75 2.75 0 0 0 4.75 18h10.5A2.75 2.75 0 0 0 18 15.25v-2.5a.75.75 0 0 0-1.5 0v2.5c0 .69-.56 1.25-1.25 1.25H4.75c-.69 0-1.25-.56-1.25-1.25v-2.5Z"
						/>
					</svg>
				</button>
				<button data-window-close type="button" aria-label={$i18n.t('Close')}
					on:pointerdown={(e) => {
						e.stopImmediatePropagation();
						e.preventDefault();
						show = false;
					}}
					on:click={() => show = false}>
					<XMark className="size-4" />
				</button>
			</div>
		</div>
		<ZoomSurface {src} {alt} />
	</div>
{/if}
