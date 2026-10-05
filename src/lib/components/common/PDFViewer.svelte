<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import pdfWorkerUrl from 'pdfjs-dist/build/pdf.worker.mjs?url';
	import panzoom, { type PanZoom } from 'panzoom';
	import Spinner from './Spinner.svelte';

	export let url: string | null = null;
	export let data: ArrayBuffer | Uint8Array | null = null;
	export let className = 'w-full h-[70vh]';

	let outerContainer: HTMLDivElement;
	let sceneElement: HTMLDivElement;
	let loading = true;
	let error = '';
	let pdfDoc: any = null;
	let pzInstance: PanZoom | null = null;
	let zoomLevel = 1;
	let rerenderTimer: ReturnType<typeof setTimeout> | null = null;
	let lastRenderedZoom = 1;
	let pageObserver: IntersectionObserver | null = null;
	let loadingTask: any = null;
	let destroyed = false;
	const renders = new Map<HTMLCanvasElement, any>();
	let renderQueue = Promise.resolve();

	const renderCanvas = async (canvas: HTMLCanvasElement, forZoom: number) => {
		if (destroyed || !pdfDoc) return;
		const previous = renders.get(canvas);
		previous?.cancel();
		await previous?.promise?.catch(() => {});
		if (destroyed || !pdfDoc) return;
		const page = await pdfDoc.getPage(Number(canvas.dataset.page));
		const viewport = page.getViewport({ scale: 1 });
		const cssScale = (outerContainer?.clientWidth || 800) / viewport.width;
		const requested = cssScale * forZoom * Math.min(window.devicePixelRatio || 1, 2);
		const scale = Math.min(requested, Math.sqrt(8000000 / (viewport.width * viewport.height)));
		const scaledViewport = page.getViewport({ scale });
		canvas.width = Math.ceil(scaledViewport.width);
		canvas.height = Math.ceil(scaledViewport.height);
		const task = page.render({ canvas, canvasContext: canvas.getContext('2d'), viewport: scaledViewport });
		renders.set(canvas, task);
		try { await task.promise; canvas.dataset.rendered = 'true'; }
		catch (error) { if (!destroyed && (error as Error).name !== 'RenderingCancelledException') throw error; }
		finally { if (renders.get(canvas) === task) renders.delete(canvas); }
	};

	const initPanzoom = () => {
		if (pzInstance) {
			pzInstance.dispose();
		}
		if (sceneElement) {
			pzInstance = panzoom(sceneElement, {
				bounds: true,
				boundsPadding: 0.1,
				zoomSpeed: 0.065,
				beforeWheel: (e) => {
					// Only zoom on pinch (ctrlKey / metaKey); let normal scroll pass through
					if (!e.ctrlKey && !e.metaKey) {
						return true; // returning true cancels the panzoom wheel handling
					}
					return false;
				},
				beforeMouseDown: (e) => {
					// Only allow drag-to-pan when zoomed in (not at default scale)
					const transform = pzInstance?.getTransform();
					if (transform && Math.abs(transform.scale - 1) < 0.01) {
						return true; // cancel panzoom mouse handling at 1x — allow text selection / normal interaction
					}
					return false;
				}
			});
			pzInstance.on('zoom', () => {
				zoomLevel = pzInstance?.getTransform()?.scale ?? 1;
				// Debounced re-render at new resolution so text stays crisp
				if (rerenderTimer) clearTimeout(rerenderTimer);
				rerenderTimer = setTimeout(() => {
					if (Math.abs(zoomLevel - lastRenderedZoom) > 0.05) {
						rerenderPages(zoomLevel);
					}
				}, 300);
			});
		}
	};

	const zoomIn = () => {
		if (!pzInstance || !outerContainer) return;
		const cx = outerContainer.clientWidth / 2;
		const cy = outerContainer.clientHeight / 2;
		pzInstance.zoomTo(cx, cy, 1.25); // +25%
		zoomLevel = pzInstance.getTransform().scale;
	};

	const zoomOut = () => {
		if (!pzInstance || !outerContainer) return;
		const cx = outerContainer.clientWidth / 2;
		const cy = outerContainer.clientHeight / 2;
		pzInstance.zoomTo(cx, cy, 0.8); // -20% (inverse of 1.25)
		zoomLevel = pzInstance.getTransform().scale;
	};

	export const resetView = () => {
		if (pzInstance) {
			pzInstance.moveTo(0, 0);
			pzInstance.zoomAbs(0, 0, 1);
			zoomLevel = 1;
			rerenderPages(1);
		}
	};

	// Re-render existing canvases at a new zoom level (preserves panzoom transform)
	const rerenderPages = async (forZoom: number) => {
		if (!pdfDoc || !sceneElement) return;
		renderQueue = renderQueue.then(async () => {
			if (destroyed) return;
			for (const canvas of sceneElement.querySelectorAll<HTMLCanvasElement>('canvas[data-rendered="true"]')) {
				if (destroyed) return;
				await renderCanvas(canvas, forZoom);
			}
			lastRenderedZoom = forZoom;
		}).catch(() => {});
		await renderQueue;
	};

	const renderAllPages = async () => {
		if (!pdfDoc || !sceneElement) return;
		pageObserver?.disconnect();
		pageObserver = new IntersectionObserver((entries) => {
			for (const entry of entries) if (entry.isIntersecting) {
				pageObserver?.unobserve(entry.target);
				renderQueue = renderQueue.then(() => renderCanvas(entry.target as HTMLCanvasElement, zoomLevel)).catch(() => {});
			}
		}, { root: outerContainer, rootMargin: '500px' });

		// Clear previous canvases
		sceneElement.innerHTML = '';

		for (let i = 1; i <= pdfDoc.numPages; i++) {
			if (destroyed) return;
			const page = await pdfDoc.getPage(i);
			const viewport = page.getViewport({ scale: 1 });

			// Scale to fit container width
			const containerWidth = outerContainer?.clientWidth || 800;
			const cssScale = containerWidth / viewport.width;

			const canvas = document.createElement('canvas');
			canvas.dataset.page = String(i);
			// CSS size stays at the CSS-pixel dimensions for layout
			canvas.style.width = `${Math.round(cssScale * viewport.width)}px`;
			canvas.style.height = `${Math.round(cssScale * viewport.height)}px`;
			canvas.style.display = 'block';

			if (i > 1) {
				canvas.style.marginTop = '4px';
			}

			sceneElement.appendChild(canvas);

			if (i === 1) { await renderCanvas(canvas, 1); loading = false; }
			else pageObserver.observe(canvas);
		}

		lastRenderedZoom = 1;
		initPanzoom();
	};

	const loadPdf = async () => {
		if (!url && !data) return;

		loading = true;
		error = '';

		try {
			const pdfjs = await import('pdfjs-dist');
			pdfjs.GlobalWorkerOptions.workerSrc = pdfWorkerUrl;

			let pdfData: ArrayBuffer | Uint8Array;
			if (data) {
				pdfData = data;
			} else {
				// Fetch with credentials so auth cookies are sent
				const res = await fetch(url!, { credentials: 'include' });
				if (!res.ok) throw new Error(`HTTP ${res.status}`);
				pdfData = await res.arrayBuffer();
			}
			if (destroyed) return;
			loadingTask = pdfjs.getDocument({ data: pdfData });
			pdfDoc = await loadingTask.promise;
			if (destroyed) return;
			await renderAllPages();
		} catch (e) {
			console.error('PDF render error:', e);
			error = 'Failed to load PDF.';
		} finally {
			loading = false;
		}
	};

	onMount(() => {
		loadPdf();
	});

	onDestroy(() => {
		destroyed = true;
		pageObserver?.disconnect();
		for (const task of renders.values()) task.cancel();
		if (rerenderTimer) clearTimeout(rerenderTimer);
		pzInstance?.dispose();
		void loadingTask?.destroy()?.catch(() => {});
		pdfDoc = null;
	});
</script>

<div class="relative {className}">
	{#if loading}
		<div class="absolute inset-0 flex items-center justify-center">
			<Spinner className="size-5" />
		</div>
	{:else if error}
		<div class="absolute inset-0 flex items-center justify-center text-sm text-red-500">
			{error}
		</div>
	{/if}

	<div class="overflow-y-auto h-full" bind:this={outerContainer}>
		<div bind:this={sceneElement} class="w-full"></div>
	</div>

	{#if !loading && !error && pdfDoc}
		<div
			class="absolute bottom-3 left-1/2 -translate-x-1/2 z-10 flex items-center gap-0.5 rounded-lg bg-white/90 dark:bg-gray-850/90 backdrop-blur-sm shadow-lg border border-gray-200/60 dark:border-gray-700/60 px-1 py-0.5"
		>
			<button
				class="p-1.5 rounded-md hover:bg-gray-100 dark:hover:bg-gray-800 transition text-gray-500 dark:text-gray-400"
				on:click={zoomOut}
				aria-label="Zoom out"
			>
				<svg
					xmlns="http://www.w3.org/2000/svg"
					viewBox="0 0 20 20"
					fill="currentColor"
					class="size-3.5"
				>
					<path
						fill-rule="evenodd"
						d="M4 10a.75.75 0 0 1 .75-.75h10.5a.75.75 0 0 1 0 1.5H4.75A.75.75 0 0 1 4 10Z"
						clip-rule="evenodd"
					/>
				</svg>
			</button>
			<button
				class="px-1.5 py-1 min-w-[3rem] text-center text-[11px] font-medium text-gray-500 dark:text-gray-400 rounded-md hover:bg-gray-100 dark:hover:bg-gray-800 transition tabular-nums"
				on:click={resetView}
				aria-label="Reset zoom"
			>
				{Math.round(zoomLevel * 100)}%
			</button>
			<button
				class="p-1.5 rounded-md hover:bg-gray-100 dark:hover:bg-gray-800 transition text-gray-500 dark:text-gray-400"
				on:click={zoomIn}
				aria-label="Zoom in"
			>
				<svg
					xmlns="http://www.w3.org/2000/svg"
					viewBox="0 0 20 20"
					fill="currentColor"
					class="size-3.5"
				>
					<path
						d="M10.75 4.75a.75.75 0 0 0-1.5 0v4.5h-4.5a.75.75 0 0 0 0 1.5h4.5v4.5a.75.75 0 0 0 1.5 0v-4.5h4.5a.75.75 0 0 0 0-1.5h-4.5v-4.5Z"
					/>
				</svg>
			</button>
		</div>
	{/if}
</div>
