<script lang="ts">
	import { getContext, onDestroy } from 'svelte';
	import { Minus, Plus, Trash2, Undo2 } from '@lucide/svelte';
	import SelectionBrush from '$lib/components/icons/SelectionBrush.svelte';
	import type { I18nStore } from '$lib/i18n';
	import Tooltip from '$lib/components/common/Tooltip.svelte';

	export let request: (points: [number,number,0|1][], signal: AbortSignal) => Promise<{mask:string}>;
	export let selection = '';
	export let frameKey: string, width: number, height: number, transform = '', crop = false;
	export let pending = false;
	const i18n = getContext<I18nStore>('i18n');
	$: pending=busy;
	let busy = false, subtract = false, error = '';
	let points: [number,number,0|1][] = [];
	let svg: SVGSVGElement;
	let keyboardPoint: [number,number] | null = null;
	let controller: AbortController;
	const label = 'Select what to erase';
	async function update() {
		controller?.abort();
		const current = controller = new AbortController();
		error = '';
		if (!points.length) { selection=''; subtract=false; busy=false; return; }
		busy = true;
		try {
			const result = await request(points, current.signal);
			if (current.signal.aborted) return;
			selection = result.mask ?? '';
		} catch (e) {
			if (!current.signal.aborted) { selection=''; error = 'Could not select this region.'; }
		} finally { if (!current.signal.aborted) busy = false; }
	}
	function mark(e: MouseEvent) {
		if (points.length >= 64) return;
		const transform = svg.getScreenCTM();
		if (!transform) return;
		const at = e.detail ? new DOMPoint(e.clientX,e.clientY).matrixTransform(transform.inverse()) :
			new DOMPoint((keyboardPoint?.[0] ?? .5)*width,(keyboardPoint?.[1] ?? .5)*height);
		const x = at.x/width, y = at.y/height;
		if (x<0 || x>1 || y<0 || y>1) return;
		points = [...points,[x,y,points.length && (subtract || e.shiftKey || e.altKey) ? 0 : 1]];
		if (!e.detail) keyboardPoint = null;
		void update();
	}
	function movePoint(e: KeyboardEvent) {
		if (!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(e.key)) return;
		e.preventDefault(); e.stopPropagation();
		const [x,y] = keyboardPoint ?? [.5,.5];
		keyboardPoint = [Math.max(0,Math.min(1,x+.01*(Number(e.key==='ArrowRight')-Number(e.key==='ArrowLeft')))),
			Math.max(0,Math.min(1,y+.01*(Number(e.key==='ArrowDown')-Number(e.key==='ArrowUp'))))];
	}
	function resetFrame(_frame: string) {
		controller?.abort(); points=[]; selection=''; keyboardPoint=null; busy=false; subtract=false; error='';
	}
	$: resetFrame(frameKey);
	onDestroy(() => controller?.abort());
</script>

<div class="pick-overlay absolute inset-0">
	<div class="absolute left-2 top-2 z-10 flex flex-col items-center gap-1 rounded-md bg-gray-50 p-1 text-gray-700 dark:bg-gray-850 dark:text-gray-200">
		{#each [false,true] as remove}
			{@const name = remove ? 'Remove selection' : 'Select object'}
			<Tooltip content={$i18n.t(name)} placement="right">
				<button type="button" class="pick-tool" aria-label={$i18n.t(name)} aria-pressed={subtract===remove}
					disabled={remove && !points.length} on:click={() => subtract = remove}>
					<span class="relative"><SelectionBrush className="size-4"/>
						<span class="absolute -bottom-1.5 -right-1.5">{#if remove}<Minus size={10}/>{:else}<Plus size={10}/>{/if}</span>
					</span>
				</button>
			</Tooltip>
		{/each}
		<Tooltip content={$i18n.t('Undo')} placement="right"><button type="button" class="pick-tool" aria-label={$i18n.t('Undo')}
			disabled={!points.length} on:click={() => {points = points.slice(0,-1); void update();}}><Undo2 size={16}/></button></Tooltip>
		<Tooltip content={$i18n.t('Clear')} placement="right"><button type="button" class="pick-tool" aria-label={$i18n.t('Clear')}
			disabled={!points.length} on:click={() => {points=[]; void update();}}><Trash2 size={16}/></button></Tooltip>
	</div>
	<div class="absolute inset-0">
		<button type="button" class="absolute inset-0 h-full w-full cursor-crosshair bg-transparent p-0" aria-label={$i18n.t(label)} on:click={mark}
			on:keydown={movePoint} on:pointerdown={() => keyboardPoint=null} on:blur={() => keyboardPoint=null}>
			
			<svg bind:this={svg} class="h-full w-full" style:transform={transform} viewBox={`0 0 ${width} ${height}`} preserveAspectRatio={crop?'xMidYMid slice':'xMidYMid meet'} aria-hidden="true">
				{#if selection}
					<mask id="maker-selected-region" maskUnits="userSpaceOnUse" x="0" y="0" {width} {height}>
						<image href={selection} {width} {height} preserveAspectRatio="none"/>
					</mask>
					<rect data-maker-mask {width} {height} mask="url(#maker-selected-region)" fill="#3988ff" opacity=".52"/>
				{/if}
				{#if keyboardPoint}
					<circle cx={keyboardPoint[0]*width} cy={keyboardPoint[1]*height} r={width/95} fill="none" stroke="white" stroke-width="2" vector-effect="non-scaling-stroke"/>
				{/if}
			</svg>
		</button>
		<div class="pick-hint pointer-events-none absolute bottom-2 left-1/2 flex max-w-full -translate-x-1/2 items-center gap-2 rounded bg-black/75 px-2 py-1 text-center text-xs text-white" role="status">

			{$i18n.t(error || label)}

		</div>
	</div>
</div>

<style>
	.pick-overlay {container-type:inline-size;}
	@container (max-width:600px) {
		.pick-hint {top:.5rem;bottom:auto;max-width:calc(100% - 104px);}
	}
	.pick-tool { width:30px;height:30px;display:grid;place-items:center;border-radius:6px; }
	.pick-tool:hover:not(:disabled) { background:rgb(128 128 128 / .14); }
	.pick-tool[aria-pressed="true"] { color:#3b82f6;background:rgb(59 130 246 / .14); }
	.pick-tool:disabled { opacity:.35; }
</style>
