<script lang="ts">
	import {getContext,onMount} from 'svelte';
	import Restore from '$lib/components/icons/Restore.svelte';
	import Spinner from '$lib/components/common/Spinner.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import CheckCircle from '$lib/components/icons/CheckCircle.svelte';
	import {fly} from 'svelte/transition';
	import {outpaintFrame,outpaintAspect,dragOutpaintFrame,type OutpaintHandle} from '$lib/utils/outpaintGeometry';
	import type {ImageModeOptions} from '$lib/utils/imageModes';
	const i18n=getContext('i18n');
	export let source='';
	export let options: ImageModeOptions;
	let stage:HTMLDivElement;
	let viewport=600;
	const stageHeight=480;
	let width=1,height=1,ready=false,loaded='';
	let aspect='free';
	let aspectMenu=false;
	const ratios=[
		{id:'1:1',shape:'h-4 w-4'},
		{id:'3:4',shape:'h-[18px] w-[14px]'},
		{id:'4:3',shape:'h-[14px] w-[18px]'},
		{id:'16:9',shape:'h-3 w-5'},
		{id:'9:16',shape:'h-5 w-[11px]'}
	];
	$: availableRatios=ratios.filter(option=>outpaintAspect(width,height,options,ratioValue(option.id)));
	function ratioValue(value:string){const [w,h]=value.split(':').map(Number);return w/h;}
	function setAspect(){if(aspect==='free')return;const next=outpaintAspect(width,height,options,ratioValue(aspect));if(next)options=next;}
	function chooseAspect(value:string){aspect=value;setAspect();aspectMenu=false;}
	function reset(){aspect='free';options={...options,rotation:0,pad_left:0,pad_right:0,pad_top:0,pad_bottom:0,crop:null};}
	let manipulating=false;
	let gesture: {id:number,handle:OutpaintHandle,x:number,y:number,scale:number,centerX:number,centerY:number,angle:number,initial:ImageModeOptions}|null=null;
	const handles=[{id:'nw',x:0,y:0},{id:'n',x:50,y:0},{id:'ne',x:100,y:0},{id:'e',x:100,y:50},{id:'se',x:100,y:100},{id:'s',x:50,y:100},{id:'sw',x:0,y:100},{id:'w',x:0,y:50}] as const;
	$: frame=outpaintFrame(width,height,options);
	$: scale=gesture?.scale??Math.min((viewport-72)/frame.width,(stageHeight-140)/frame.height);
	$: centerX=gesture?.centerX??(viewport-frame.width*scale)/2+(frame.left+frame.rotatedWidth/2)*scale;
	$: centerY=gesture?.centerY??(stageHeight-frame.height*scale)/2+(frame.top+frame.rotatedHeight/2)*scale;
	$: if(source!==loaded){loaded=source;load(source);}
	async function load(value:string){
		ready=false;if(!value)return;
		const img=new Image();img.src=value;
		try{await img.decode();if(value!==source)return;width=img.naturalWidth;height=img.naturalHeight;ready=true;}catch{ready=false;}
	}
	onMount(()=>{const observer=new ResizeObserver(([entry])=>viewport=entry.contentRect.width);observer.observe(stage);return()=>observer.disconnect();});
	function start(event:PointerEvent,handle:OutpaintHandle){
		if(!ready||event.button!==0||gesture)return;event.preventDefault();
		aspect='free';
		manipulating=false;
		const rect=stage.getBoundingClientRect();
		gesture={id:event.pointerId,handle,x:event.clientX,y:event.clientY,scale,centerX,centerY,angle:Math.atan2(event.clientY-rect.top-centerY,event.clientX-rect.left-centerX),initial:{...options}};
		stage.setPointerCapture(event.pointerId);
	}
	function updateManipulation(next:ImageModeOptions){
		if((['rotation','pad_left','pad_right','pad_top','pad_bottom'] as const).some(key=>(next[key]??0)!==(options[key]??0)))manipulating=true;
		options=next;
	}
	function finish(event?:PointerEvent){
		if(event&&gesture?.id!==event.pointerId)return;
		const id=gesture?.id;gesture=null;manipulating=false;
		if(id!==undefined&&stage.hasPointerCapture(id))stage.releasePointerCapture(id);
	}
	function move(event:PointerEvent){
		if(!gesture||gesture.id!==event.pointerId)return;
		if(gesture.handle==='rotate'){
			const rect=stage.getBoundingClientRect();
			const angle=Math.atan2(event.clientY-rect.top-gesture.centerY,event.clientX-rect.left-gesture.centerX);
			let delta=(angle-gesture.angle)*180/Math.PI;if(delta>180)delta-=360;if(delta< -180)delta+=360;
			updateManipulation({...gesture.initial,rotation:Math.max(-45,Math.min(45,Math.round((gesture.initial.rotation??0)-delta)))});
		}else updateManipulation(dragOutpaintFrame(gesture.initial,gesture.handle,(event.clientX-gesture.x)/gesture.scale,(event.clientY-gesture.y)/gesture.scale,width,height));
	}
	function keyboard(event:KeyboardEvent,handle:OutpaintHandle){
		const step=event.shiftKey?10:1;
		if(!ready||!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(event.key))return;
		aspect='free';
		event.preventDefault();
		if(handle==='rotate')updateManipulation({...options,rotation:Math.max(-45,Math.min(45,(options.rotation??0)+(event.key==='ArrowLeft'?step:-step)))});
		else updateManipulation(dragOutpaintFrame(options,handle,event.key==='ArrowLeft'?-width*step/100:event.key==='ArrowRight'?width*step/100:0,event.key==='ArrowUp'?-height*step/100:event.key==='ArrowDown'?height*step/100:0,width,height));
	}
</script>

<svelte:window on:click={event=>{if(!(event.target as Element).closest('[data-outpaint-aspect]'))aspectMenu=false;}} on:keydown|capture={event=>{if(event.key==='Escape'&&aspectMenu){aspectMenu=false;event.preventDefault();event.stopImmediatePropagation();}}} on:keyup={event=>{if(!gesture&&['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(event.key))manipulating=false;}} on:blur={()=>finish()} />
<!-- svelte-ignore a11y_no_static_element_interactions -->
<div bind:this={stage} class="outpaint-stage relative w-full overflow-hidden rounded-md bg-gray-100 dark:bg-black/25" style:height={`${stageHeight}px`} on:pointermove={move} on:pointerup={finish} on:pointercancel={finish} on:lostpointercapture={finish} on:focusout={()=>{if(!gesture)manipulating=false;}}>
<div class="absolute top-3 left-3 z-30 flex items-center text-sm" data-outpaint-toolbar>
	<div class="relative" data-outpaint-aspect>
		<button type="button" class="flex items-center gap-1 px-2 py-[7px] text-[0.8125rem] text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-full" aria-label={$i18n.t('Image aspect ratio')} aria-expanded={aspectMenu} on:click={()=>aspectMenu=!aspectMenu}>
			<span>{aspect==='free'?$i18n.t('Livre'):aspect}</span><svg viewBox="0 0 20 20" fill="currentColor" class="size-3.5 transition-transform duration-150 {aspectMenu?'':'rotate-180'}" aria-hidden="true"><path fill-rule="evenodd" d="M14.78 12.78a.75.75 0 0 1-1.06 0L10 9.06l-3.72 3.72a.75.75 0 0 1-1.06-1.06l4.25-4.25a.75.75 0 0 1 1.06 0l4.25 4.25a.75.75 0 0 1 0 1.06Z" clip-rule="evenodd" /></svg>
		</button>
		{#if aspectMenu}<div role="menu" class="absolute left-0 top-full z-30 mt-1 w-32 rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-850 shadow-md p-1 text-sm" transition:fly={{y:-5,duration:150}}>
			{#each availableRatios as option}<button type="button" role="menuitemradio" aria-checked={aspect===option.id} class="grid w-full grid-cols-[1fr_16px] items-center gap-2 px-2 py-2 rounded-md text-left text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800" on:click={()=>chooseAspect(option.id)}>
				<span class="grid grid-cols-[24px_1fr] items-center gap-2"><span class="flex h-5 w-6 items-center justify-center"><span class="block border border-current rounded-[1px] {option.shape}"></span></span><span class="leading-5">{option.id}</span></span>
				<span class="flex size-4 items-center justify-center">{#if aspect===option.id}<CheckCircle className="size-4" strokeWidth="1.7" />{/if}</span>
			</button>{/each}
		</div>{/if}
	</div>
</div>
	{#if ready}
		<div class="outpaint-frame absolute border border-blue-500" style:left={`${centerX-(frame.rotatedWidth/2+frame.left)*scale}px`} style:top={`${centerY-(frame.rotatedHeight/2+frame.top)*scale}px`} style:width={`${frame.width*scale}px`} style:height={`${frame.height*scale}px`}>
			{#each handles as handle}<button type="button" data-outpaint-handle={handle.id} class="handle absolute z-20 size-3 -translate-x-1/2 -translate-y-1/2 border border-white bg-blue-500 shadow-sm" style:left={`${handle.x}%`} style:top={`${handle.y}%`} style:cursor={`${handle.id}-resize`} aria-label={`${$i18n.t('Ajustar área')} ${handle.id}`} on:pointerdown={event=>start(event,handle.id)} on:keydown={event=>keyboard(event,handle.id)}></button>{/each}
		</div>
		<div class="absolute" style:left={`${centerX-width*scale/2}px`} style:top={`${centerY-height*scale/2}px`} style:width={`${width*scale}px`} style:height={`${height*scale}px`} style:transform={`rotate(${-(options.rotation??0)}deg)`}>
			<button type="button" class="block size-full cursor-move border border-white/60" aria-label={$i18n.t('Posicionar imagem')} on:pointerdown={event=>start(event,'move')} on:keydown={event=>keyboard(event,'move')}><img src={source} class="block size-full pointer-events-none" draggable="false" alt={$i18n.t('Imagem principal')} /></button>
			<span class="pointer-events-none absolute -top-6 left-1/2 h-6 border-l border-blue-500"></span>
			<button type="button" data-outpaint-handle="rotate" class="absolute -top-9 left-1/2 grid size-6 -translate-x-1/2 place-items-center rounded-full bg-white text-blue-600 shadow-sm dark:bg-gray-800 dark:text-blue-400 cursor-grab" aria-label={$i18n.t('Rotação')} on:pointerdown={event=>start(event,'rotate')} on:keydown={event=>keyboard(event,'rotate')}><Restore className="size-4" /></button>
		</div>
	{:else if source}<div class="absolute inset-0 grid place-items-center"><Spinner className="size-5" /></div>
	{:else}<div class="absolute inset-0 grid place-items-center text-sm text-gray-500">{$i18n.t('Imagem principal')}</div>{/if}
	<div class="absolute bottom-3 right-3 z-30"><Tooltip content={$i18n.t('Reset')}><button type="button" class="grid size-8 place-items-center rounded-md bg-white/90 text-gray-500 hover:bg-gray-100 dark:bg-gray-850/90 dark:text-gray-300 dark:hover:bg-gray-800" aria-label={$i18n.t('Reset')} on:click={reset}><Restore className="size-4" /></button></Tooltip></div>
	{#if ready&&manipulating}<div class="pointer-events-none absolute bottom-3 left-3 z-20 flex items-center gap-3 rounded-md bg-white/90 px-2 py-1.5 text-xs tabular-nums text-gray-500 dark:bg-gray-850/90 dark:text-gray-300" data-outpaint-info><span>{`${frame.width} \u00d7 ${frame.height}`}</span><span>{options.rotation??0}{'\u00b0'}</span></div>{/if}
</div>
<style>
	.outpaint-stage{touch-action:none;}
	.outpaint-frame{background-image:repeating-conic-gradient(rgb(128 128 128 / 12%) 0% 25%,transparent 0% 50%);background-size:16px 16px;}
	.handle{border-radius:1px;touch-action:none;}
	.handle::after{content:'';position:absolute;inset:-7px;}
</style>
