<script context="module" lang="ts">
	let active = 0;
	const waiting: (() => void)[] = [];
	const cache = new Map<string, { image?: string; text?: string }>();
	async function limited<T>(work: () => Promise<T>) {
		if (active >= 2) await new Promise<void>((resolve) => waiting.push(resolve));
		else active++;
		try {
			return await work();
		} finally {
			const next = waiting.shift();
			if (next) next();
			else active--;
		}
	}
</script>

<script lang="ts">
	import { onMount } from 'svelte';
	import Document from '$lib/components/icons/Document.svelte';
	import { NEVEAI_API_BASE_URL } from '$lib/constants';
	import pdfWorkerUrl from 'pdfjs-dist/build/pdf.worker.mjs?url';
	export let file: any;
	let element: HTMLDivElement;
	let image = '';
	let text = '';
	onMount(() => {
		const controller = new AbortController();
		let task: any;
		let started = false;
		const key = `${file.id}:${file.updated_at ?? file.created_at}`;
		const load = async () => {
			if (started) return;
			started = true;
			const saved = cache.get(key);
			if (saved) {
				image = saved.image ?? '';
				text = saved.text ?? '';
				return;
			}
			await limited(async () => {
				if (controller.signal.aborted || (file.meta?.size ?? 0) > 20 * 1024 * 1024) return;
				const timeout = setTimeout(() => {
					controller.abort();
					void task?.destroy();
				}, 15000);
				try {
					const url = `${NEVEAI_API_BASE_URL}/files/${file.id}/content`;
					const mime = file.meta?.content_type ?? '';
					if (mime === 'application/pdf' || /\.pdf$/i.test(file.filename)) {
						const pdfjs = await import('pdfjs-dist');
						if (controller.signal.aborted) return;
						pdfjs.GlobalWorkerOptions.workerSrc = pdfWorkerUrl;
						task = pdfjs.getDocument({
							url,
							httpHeaders: { Authorization: `Bearer ${localStorage.token}` },
							maxImageSize: 4000000
						});
						const pdf = await task.promise;
						const page = await pdf.getPage(1);
						const viewport = page.getViewport({
							scale: 320 / page.getViewport({ scale: 1 }).width
						});
						const canvas = document.createElement('canvas');
						canvas.width = Math.ceil(viewport.width);
						canvas.height = Math.min(2048, Math.ceil(viewport.height));
						await page.render({ canvas, canvasContext: canvas.getContext('2d')!, viewport })
							.promise;
						if (!controller.signal.aborted) image = canvas.toDataURL('image/webp');
					} else if (mime.startsWith('text/') || /\.(txt|md|csv|json)$/i.test(file.filename)) {
						const response = await fetch(url, {
							signal: controller.signal,
							headers: { Authorization: `Bearer ${localStorage.token}`, Range: 'bytes=0-8191' }
						});
						if (!response.ok) return;
						const reader = response.body?.getReader();
						if (!reader) return;
						const chunk = await reader.read();
						await reader.cancel();
						if (!controller.signal.aborted)
							text = new TextDecoder().decode(chunk.value?.subarray(0, 8192)).slice(0, 1800);
					}
					if (!controller.signal.aborted) {
						if (cache.size >= 64) cache.delete(cache.keys().next().value!);
						cache.set(key, { image, text });
					}
				} catch {
					/* Unavailable previews retain the document icon. */
				} finally {
					clearTimeout(timeout);
					await task?.destroy()?.catch(() => {});
				}
			});
		};
		const observer = new IntersectionObserver(
			(entries) => {
				if (entries.some((entry) => entry.isIntersecting)) {
					observer.disconnect();
					void load();
				}
			},
			{ rootMargin: '100px' }
		);
		observer.observe(element);
		return () => {
			observer.disconnect();
			controller.abort();
			void task?.destroy();
		};
	});
</script>

<div bind:this={element} class="h-full w-full overflow-hidden pointer-events-none">
	{#if image}<img src={image} alt="" class="w-full h-full object-cover object-top" />
	{:else if text}<div
			class="h-full overflow-hidden px-4 py-3 text-[10px] leading-relaxed whitespace-pre-wrap text-gray-600 dark:text-gray-400"
		>
			{text}
		</div>
	{:else}<div class="h-full flex items-center justify-center">
			<Document className="size-12 text-gray-400" />
		</div>{/if}
</div>
