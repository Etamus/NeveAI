<script lang="ts">
	import { getContext, onDestroy } from 'svelte';
	import { DropdownMenu } from 'bits-ui';
	import { NEVEAI_API_BASE_URL } from '$lib/constants';
	import type { I18nStore } from '$lib/i18n';
	import CheckCircle from '$lib/components/icons/CheckCircle.svelte';
	import ChevronDown from '$lib/components/icons/ChevronDown.svelte';
	import Cube from '$lib/components/icons/Cube.svelte';
	import Download from '$lib/components/icons/ModelDownload.svelte';
	import { saveChatFile } from '$lib/utils/chatFileSave';
	import OrbitingSpheres from './OrbitingSpheres.svelte';
	import MeshPreview, { type ViewMode } from './MeshPreview.svelte';

	export let id: string;
	export let name: string;
	export let deferred = true;
	export let showName = true;
	export let previewOnly = false;
	let nearViewport = false;
	let mode: ViewMode = 'textured';
	$: id, mode = 'textured';
	let formatOpen = false;
	let format = '3mf';
	let height: number | undefined = 100;
	let baseMode = 'original';
	let baseOpen = false;
	const baseLabel = (value: string) => value === 'stable' ? 'Stable base' : 'Original base';
	let downloading = false;
	let error = '';
	$: id, height, format, baseMode, error = '';
	let controller: AbortController;
	const formats = ['3mf', 'stl', 'blend', 'obj', 'fbx', 'glb'];
	const label = (extension: string) => extension.toUpperCase();
	$: hasPrintHeight = format === '3mf' || format === 'stl';
	$: invalidHeight = hasPrintHeight && !(height !== undefined && height >= 5 && height <= 10000);
	const i18n = getContext<I18nStore>('i18n');
	onDestroy(() => controller?.abort());

	function observePreview(node: HTMLElement) {
		if (!deferred || !('IntersectionObserver' in window)) {
			nearViewport = true;
			return;
		}
		const observer = new IntersectionObserver(([entry]) => {
			nearViewport = entry.isIntersecting;
		}, { rootMargin: '240px 0px' });
		observer.observe(node);
		return { destroy: () => observer.disconnect() };
	}

	async function download() {
		if (downloading) return;
		downloading = true;
		error = '';
		const task = controller = new AbortController();
		const base = `${NEVEAI_API_BASE_URL}`;
		const endpoint = format === 'glb' ? `files/${encodeURIComponent(id)}/content?attachment=true` :
			`model3d/${encodeURIComponent(id)}/export/${format}${hasPrintHeight ? `?height_mm=${height}${baseMode === 'stable' ? '&flat_base=true' : ''}` : ''}`;
		try {
			const filename = name.replace(/\.glb$/i, '') + '.' + (format === 'obj' ? 'zip' : format);
			await saveChatFile(filename, async () => {
				const response = await fetch(`${base}/${endpoint}`, {
					signal: task.signal, headers: { Authorization: `Bearer ${localStorage.token ?? ''}` }
				});
				if (response.status === 422) {
					const detail = (await response.json().catch(() => null))?.detail;
					error = detail === 'flat_base_failed' ? $i18n.t('Cannot stabilize this base without losing geometry. Turn off Stable base to keep the original shape.') :
						hasPrintHeight ? $i18n.t('The mesh is not closed enough for printing.') : $i18n.t('Unable to export the 3D model');
					throw new Error(error);
				}
				return response;
			});
		} catch {
			if (!error && !task.signal.aborted) error = $i18n.t('Unable to export the 3D model');
		} finally {
			downloading = false;
		}
	}
</script>

<div data-mesh-result={id} class="overflow-hidden rounded-lg bg-gray-50 dark:bg-gray-850/50">
	{#if !previewOnly}<div class="flex flex-wrap items-center gap-2 p-3 text-sm">
		{#if showName}
			<Cube className="size-4 shrink-0" />
			<span data-mesh-name class="min-w-0 flex-1 truncate">{name}</span>
		{/if}
		<div class="ml-auto flex shrink-0 items-center gap-1.5">
		{#if hasPrintHeight}
			<label class="flex h-7 items-center gap-1 pl-1.5 rounded-md border border-black/5 pr-1.5 text-xs focus-within:border-black/20 dark:border-white/[0.06] dark:focus-within:border-white/20">
				<input type="number" min="5" max="10000" value={height ?? ''} on:input={(event) => {
					const input = event.currentTarget;
					if (!input.value) { height = undefined; return; }
					height = Math.min(10000, Math.max(0, Math.trunc(input.valueAsNumber)));
					input.value = String(height);
				}} disabled={downloading} aria-label={$i18n.t('Print height')} aria-invalid={invalidHeight} class="w-[calc(5ch+2px)] appearance-none [&::-webkit-inner-spin-button]:appearance-none border-0 bg-transparent p-0 text-right tabular-nums outline-none" />
				<span class="text-gray-500 dark:text-gray-400">mm</span>
			</label>
		<DropdownMenu.Root bind:open={baseOpen} portal={null} preventScroll={false}>
			<DropdownMenu.Trigger aria-label={`${$i18n.t('Stable base')}: ${$i18n.t(baseLabel(baseMode))}`} disabled={downloading}
				class="flex shrink-0 items-center gap-1.5 rounded-full px-2.5 py-1.5 text-[0.79rem] font-normal text-gray-600 hover:bg-gray-100 disabled:opacity-50 dark:text-gray-300 dark:hover:bg-gray-800">
				{$i18n.t(baseLabel(baseMode))}
				<ChevronDown className="size-3 shrink-0 transition-transform {baseOpen ? 'rotate-180' : ''}" />
			</DropdownMenu.Trigger>
			<DropdownMenu.Content align="end" sideOffset={5} strategy="fixed"
				class="z-[10002] min-w-28 rounded-md border border-gray-100 bg-white p-1 text-sm text-gray-700 shadow-md dark:border-gray-800 dark:bg-gray-850 dark:text-gray-200">
				<DropdownMenu.RadioGroup bind:value={baseMode}>
					{#each ['original', 'stable'] as option}
						<DropdownMenu.RadioItem value={option}
							class="flex cursor-pointer select-none items-center justify-between gap-3 rounded-sm px-3 py-1.5 outline-none data-[highlighted]:bg-gray-100 dark:data-[highlighted]:bg-gray-800">
							{$i18n.t(baseLabel(option))}
							<span class="size-3.5 shrink-0">{#if baseMode === option}<CheckCircle className="size-3.5" />{/if}</span>
						</DropdownMenu.RadioItem>
					{/each}
				</DropdownMenu.RadioGroup>
			</DropdownMenu.Content>
		</DropdownMenu.Root>
		{/if}
		<DropdownMenu.Root bind:open={formatOpen} portal={null} preventScroll={false}>
			<DropdownMenu.Trigger aria-label={`${$i18n.t('File format')}: ${label(format)}`} disabled={downloading}
				class="flex shrink-0 items-center gap-1.5 rounded-full px-2.5 py-1.5 text-[0.79rem] font-normal text-gray-600 hover:bg-gray-100 disabled:opacity-50 dark:text-gray-300 dark:hover:bg-gray-800">
				{label(format)}
				<ChevronDown className="size-3 shrink-0 transition-transform {formatOpen ? 'rotate-180' : ''}" />
			</DropdownMenu.Trigger>
			<DropdownMenu.Content align="end" sideOffset={5} strategy="fixed"
				class="z-[10002] min-w-28 rounded-md border border-gray-100 bg-white p-1 text-sm text-gray-700 shadow-md dark:border-gray-800 dark:bg-gray-850 dark:text-gray-200">
				<DropdownMenu.RadioGroup bind:value={format}>
					{#each formats as extension (extension)}
						<DropdownMenu.RadioItem value={extension}
							class="flex cursor-pointer select-none items-center justify-between gap-3 rounded-sm px-3 py-1.5 outline-none data-[highlighted]:bg-gray-100 dark:data-[highlighted]:bg-gray-800">
							{label(extension)}
							<span class="size-3.5 shrink-0">{#if format === extension}<CheckCircle className="size-3.5" />{/if}</span>
						</DropdownMenu.RadioItem>
					{/each}
				</DropdownMenu.RadioGroup>
			</DropdownMenu.Content>
		</DropdownMenu.Root>
		<button type="button" aria-label={$i18n.t('Download')} title={$i18n.t('Download')} aria-busy={downloading} disabled={downloading || invalidHeight} class="grid size-8 place-items-center rounded-md hover:bg-gray-200 disabled:opacity-50 dark:hover:bg-gray-800" on:click={download}>{#if downloading}<OrbitingSpheres className="size-4" />{:else}<Download className="size-4" />{/if}</button>
		</div>
	</div>
	{/if}
	{#if error}<p class="px-3 pb-2 text-sm text-red-500" role="alert">{error}</p>{/if}
	<div use:observePreview class="h-[min(52vh,30rem)] bg-gray-100 dark:bg-gray-850">
		{#if nearViewport}
			{#key id}<MeshPreview {id} bind:mode />{/key}
		{/if}
	</div>
</div>
