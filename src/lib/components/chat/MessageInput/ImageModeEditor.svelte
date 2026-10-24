<script lang="ts">
	import {getContext,tick} from 'svelte';
	import {toast} from 'svelte-sonner';
	import Modal from '$lib/components/common/Modal.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import Spinner from '$lib/components/common/Spinner.svelte';
	import Brush from '$lib/components/icons/Brush.svelte';
	import Eraser from '$lib/components/icons/Eraser.svelte';
	import SelectionBrush from '$lib/components/icons/SelectionBrush.svelte';
	import Trash from '$lib/components/icons/Trash.svelte';
	import Minus from '$lib/components/icons/Minus.svelte';
	import Plus from '$lib/components/icons/Plus.svelte';
	import XMark from '$lib/components/icons/XMark.svelte';
	import ImageOutpaintEditor from './ImageOutpaintEditor.svelte';
	import ImageEditorMoveIcon from './ImageEditorMoveIcon.svelte';
	import {ImageMaskHistory} from '$lib/utils/imageMaskHistory';
	import {imagePreviewSize} from '$lib/utils/imagePreviewRendering';
	import {IMAGE_MODES,imageModeFiles,imageModeSource,imageModeSourceKey,type ImageModeOptions} from '$lib/utils/imageModes';
	const i18n=getContext('i18n');
	export let show=false;
	export let options:ImageModeOptions;
	export let files:any[]=[];
	export let disabled=false;
	let draft:ImageModeOptions;
	let opened=false,loading=false,busy=false,drawing=false,restoring=false;
	let image:HTMLImageElement,overlay:HTMLCanvasElement,mask:HTMLCanvasElement;
	let viewport:HTMLDivElement;
	let viewportWidth=600,viewportHeight=480;
	let pan:{id:number;x:number;y:number;left:number;top:number}|null=null;
	type Tool='move'|'paint'|'erase'|'select';
	let tool:Tool='move';
	let brush=32,eraser=32,brushMenu=false,zoom=1,loadVersion=0,historyVersion=0,zoomVersion=0,previewAspect=1;
	let sizePreviewTool:'paint'|'erase'|null=null;
	let sizeHoldTimer:ReturnType<typeof setTimeout>|undefined;
	let sizeHoldOpened:'paint'|'erase'|null=null;
	$: activeSize=tool==='erase'?eraser:brush;
	let last:{x:number;y:number}|null=null;
	let history=new ImageMaskHistory();
	let positive:{x:number;y:number}[]=[],negative:{x:number;y:number}[]=[];
	let exclude=false,loadedSource='';
	let request:AbortController,warmRequest:AbortController;
	$: images=imageModeFiles(files);
	$: title=IMAGE_MODES.find(mode=>mode.id===options.mode)?.label??'Editar região';
	$: fittedWidth=Math.max(1,Math.min(viewportWidth-24,(viewportHeight-24)*previewAspect));
	$: displayWidth=fittedWidth*zoom;
	$: displayHeight=displayWidth/previewAspect;
	$: brushCursor=tool==='paint'||tool==='erase'?circleCursor(activeSize*displayWidth/Math.max(1,mask?.width??displayWidth)):'';
	$: if(show&&overlay&&mask)renderMask(displayWidth,displayHeight);
	$: if(tool==='select'||tool==='move')brushMenu=false;
	function chooseTool(next:Tool,toggle=true){if(busy||loading)return;brushMenu=false;if(next==='select')exclude=tool==='select'&&toggle?!exclude:false;tool=next;}
	function setSize(value:number){if(tool==='erase')eraser=value;else brush=value;}
	function sizeRadius(value:number){return 3+5*Math.sqrt(Math.max(0,Math.min(1,(value-4)/156)));}
	function circleCursor(diameter:number){
		const visibleDiameter=Math.max(4,Math.min(96,diameter));
		const size=Math.ceil(visibleDiameter)+4,center=size/2,radius=Math.max(1,visibleDiameter/2);
		const svg=`<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 ${size} ${size}"><circle cx="${center}" cy="${center}" r="${radius}" fill="none" stroke="black" stroke-width="2"/><circle cx="${center}" cy="${center}" r="${radius}" fill="none" stroke="white" stroke-width="1"/></svg>`;
		return `url("data:image/svg+xml,${encodeURIComponent(svg)}") ${Math.floor(center)} ${Math.floor(center)}, crosshair`;
	}
	function beginSizeHold(next:'paint'|'erase',event:PointerEvent){
		if(busy||loading||event.button!==0)return;
		sizeHoldOpened=null;
		clearTimeout(sizeHoldTimer);
		sizeHoldTimer=setTimeout(()=>{
			chooseTool(next);brushMenu=true;sizeHoldOpened=next;
		},120);
	}
	function endSizeHold(){clearTimeout(sizeHoldTimer);}
	function releaseSizeHold(){
		endSizeHold();sizePreviewTool=null;
		setTimeout(()=>sizeHoldOpened=null,0);
	}
	function activateSizeTool(next:'paint'|'erase'){
		if(sizeHoldOpened===next){sizeHoldOpened=null;return;}
		chooseTool(next);
	}
	function changeToolSize(next:'paint'|'erase',value:number){
		if(next==='erase')eraser=value;else brush=value;
	}
	$: if(show&&!opened){
		opened=true;draft=structuredClone(options);tool='move';zoom=1;history=new ImageMaskHistory();positive=[];negative=[];exclude=false;brushMenu=false;sizePreviewTool=null;
		if(draft.source_id&&draft.source_id!==imageModeSourceKey(images[0]))draft.mask=null;
		loadedSource='';
	}else if(!show&&opened){
		opened=false;loadVersion++;historyVersion++;request?.abort();warmRequest?.abort();drawing=false;restoring=false;brushMenu=false;sizePreviewTool=null;clearTimeout(sizeHoldTimer);sizeHoldOpened=null;pan=null;
	}
	$: if(show&&opened&&draft?.mode==='inpaint'&&imageModeSource(images[0])!==loadedSource){loadedSource=imageModeSource(images[0]);loadImage();}
	function measureViewport(node:HTMLElement){
		const observer=new ResizeObserver(()=>{viewportWidth=node.clientWidth;viewportHeight=node.clientHeight;});
		observer.observe(node);return{destroy(){observer.disconnect();}};
	}
	async function loadImage(){
		const version=++loadVersion,source=imageModeSource(images[0]);if(!source)return;
		loading=true;warmRequest?.abort();warmRequest=new AbortController();
		void fetch('/api/v1/stable-diffusion/modes/segment',{method:'POST',signal:warmRequest.signal,headers:{'Content-Type':'application/json',Authorization:`Bearer ${localStorage.token}`},body:JSON.stringify({image:source,prepare:true})}).catch(()=>{});
		try{
			const next=new Image();next.src=source;await next.decode();if(version!==loadVersion||!show)return;
			image=next;await tick();mask=document.createElement('canvas');
			const scale=Math.min(1,1536/Math.max(image.naturalWidth,image.naturalHeight));
			mask.width=Math.round(image.naturalWidth*scale);mask.height=Math.round(image.naturalHeight*scale);
			if(draft.mask)await importMask(draft.mask);
			if(version!==loadVersion||!show)return;
			previewAspect=image.naturalWidth/image.naturalHeight;
			renderMask();history.reset(mask.toDataURL());history=history;
		}catch{if(version===loadVersion&&show)toast.error($i18n.t('Não foi possível abrir a imagem.'));}
		finally{if(version===loadVersion)loading=false;}
	}
	function renderMask(width=displayWidth,height=displayHeight){
		if(!overlay||!mask)return;
		const size=imagePreviewSize(width,height,window.devicePixelRatio||1);
		overlay.width=size.width;overlay.height=size.height;
		const context=overlay.getContext('2d')!;
		context.imageSmoothingEnabled=true;context.imageSmoothingQuality='high';
		context.drawImage(mask,0,0,size.width,size.height);
		context.globalCompositeOperation='source-in';context.fillStyle='#3b82f6';context.fillRect(0,0,size.width,size.height);
	}
	async function importMask(source:string){
		const next=new Image();next.src=source;await next.decode();
		const context=mask.getContext('2d')!;context.globalCompositeOperation='source-over';context.clearRect(0,0,mask.width,mask.height);context.drawImage(next,0,0,mask.width,mask.height);
		const data=context.getImageData(0,0,mask.width,mask.height);
		for(let i=0;i<data.data.length;i+=4){const alpha=data.data[i];data.data[i]=data.data[i+1]=data.data[i+2]=255;data.data[i+3]=alpha;}
		context.putImageData(data,0,0);renderMask();
	}
	function commit(){history.commit(mask.toDataURL());history=history;}
	async function stepHistory(direction:-1|1){
		if(!mask||busy||loading)return;
		finishStroke();const snapshot=history.step(direction);history=history;if(!snapshot)return;
		positive=[];negative=[];const version=++historyVersion;restoring=true;
		try{
			const img=new Image();img.src=snapshot;await img.decode();if(version!==historyVersion||!show)return;
			const context=mask.getContext('2d')!;context.globalCompositeOperation='source-over';context.clearRect(0,0,mask.width,mask.height);context.drawImage(img,0,0);renderMask();
		}finally{if(version===historyVersion)restoring=false;}
	}
	function point(event:PointerEvent){const b=overlay.getBoundingClientRect();return{x:(event.clientX-b.left)/b.width*mask.width,y:(event.clientY-b.top)/b.height*mask.height};}
	function stroke(event:PointerEvent){
		if(!drawing||!mask)return;const next=point(event),context=mask.getContext('2d')!;
		context.globalCompositeOperation=tool==='erase'?'destination-out':'source-over';context.strokeStyle=context.fillStyle='#ffffff';context.lineWidth=activeSize;context.lineCap=context.lineJoin='round';
		context.beginPath();context.moveTo(last?.x??next.x,last?.y??next.y);context.lineTo(next.x,next.y);context.stroke();context.beginPath();context.arc(next.x,next.y,activeSize/2,0,Math.PI*2);context.fill();last=next;renderMask();
	}
	function finishStroke(){if(!drawing)return;drawing=false;last=null;commit();}
	async function select(event:PointerEvent){
		if(busy)return;const p=point(event),normalized={x:Math.max(0,Math.min(1,p.x/mask.width)),y:Math.max(0,Math.min(1,p.y/mask.height))};
		if(exclude&&!positive.length)return;
		(exclude?negative:positive).push(normalized);busy=true;request=new AbortController();
		try{
			const response=await fetch('/api/v1/stable-diffusion/modes/segment',{method:'POST',signal:request.signal,headers:{'Content-Type':'application/json',Authorization:`Bearer ${localStorage.token}`},body:JSON.stringify({image:imageModeSource(images[0]),positive,negative})});
			const result=await response.json();if(!response.ok)throw new Error(result.detail??'Falha na seleção.');
			if(show){await importMask(result.mask);commit();}
		}catch(error){(exclude?negative:positive).pop();if((error as Error).name!=='AbortError')toast.error((error as Error).message);}
		finally{busy=false;}
	}
	function start(event:PointerEvent){
		if(event.button!==0||tool==='move'||pan)return;
		if(busy||loading||restoring||!mask)return;event.preventDefault();brushMenu=false;if(tool==='select'){select(event);return;}
		positive=[];negative=[];drawing=true;last=null;overlay.setPointerCapture(event.pointerId);stroke(event);
	}
	function clear(){if(!mask||restoring||busy)return;mask.getContext('2d')!.clearRect(0,0,mask.width,mask.height);positive=[];negative=[];renderMask();commit();}
	function startPan(event:PointerEvent){
		if((event.button!==1&&(event.button!==0||tool!=='move'))||loading||drawing||pan)return;
		event.preventDefault();event.stopPropagation();brushMenu=false;
		pan={id:event.pointerId,x:event.clientX,y:event.clientY,left:viewport.scrollLeft,top:viewport.scrollTop};
		viewport.setPointerCapture(event.pointerId);
	}
	function movePan(event:PointerEvent){
		if(!pan||pan.id!==event.pointerId)return;
		event.preventDefault();viewport.scrollLeft=pan.left+pan.x-event.clientX;viewport.scrollTop=pan.top+pan.y-event.clientY;
	}
	function stopPan(event:PointerEvent){if(pan?.id===event.pointerId){pan=null;if(viewport.hasPointerCapture(event.pointerId))viewport.releasePointerCapture(event.pointerId);}}
	async function changeZoom(value:number,clientX?:number,clientY?:number){
		if(!viewport||loading||!overlay||drawing)return;
		const next=Math.max(.25,Math.min(4,value));if(next===zoom)return;
		const rect=viewport.getBoundingClientRect(),before=overlay.getBoundingClientRect();
		const x=clientX??rect.left+rect.width/2,y=clientY??rect.top+rect.height/2;
		const relativeX=(x-before.left)/before.width,relativeY=(y-before.top)/before.height;
		const version=++zoomVersion;zoom=next;await tick();if(version!==zoomVersion||!show)return;
		const after=overlay.getBoundingClientRect();viewport.scrollLeft+=after.left+relativeX*after.width-x;viewport.scrollTop+=after.top+relativeY*after.height-y;
	}
	function wheelZoom(event:WheelEvent){
		event.preventDefault();event.stopPropagation();
		const delta=event.deltaY*(event.deltaMode===1?16:event.deltaMode===2?viewportHeight:1);
		void changeZoom(zoom*Math.exp(-delta*.0015),event.clientX,event.clientY);
	}
	function keyboard(event:KeyboardEvent){
		if(!show)return;
		if(event.key==='Escape'&&brushMenu){brushMenu=false;event.preventDefault();event.stopImmediatePropagation();return;}
		if(draft?.mode!=='inpaint'||busy||loading)return;
		if((event.target as Element)?.closest('textarea, input:not([type="range"]), [contenteditable="true"]'))return;
		const key=event.key.toLowerCase(),modifier=event.ctrlKey||event.metaKey;
		if(modifier&&(key==='z'||key==='y')){event.preventDefault();event.stopImmediatePropagation();void stepHistory(key==='y'||event.shiftKey?1:-1);}
		else if(!modifier&&!event.altKey){
			if(key==='v')chooseTool('move');else if(key==='b')chooseTool('paint');else if(key==='e')chooseTool('erase');else if(key==='w')chooseTool('select',false);
			else if(key==='[')setSize(Math.max(4,activeSize-2));else if(key===']')setSize(Math.min(160,activeSize+2));
			else if(key==='delete'||key==='backspace'){event.preventDefault();clear();}
		}
	}
	async function apply(){
		if(busy||disabled||loading||restoring)return;
		finishStroke();
		if(draft.mode==='inpaint'){
			if(!mask){toast.error($i18n.t('Adicione a imagem base.'));return;}
			const exported=document.createElement('canvas');exported.width=mask.width;exported.height=mask.height;
			const context=exported.getContext('2d')!;context.fillStyle='#000';context.fillRect(0,0,mask.width,mask.height);context.drawImage(mask,0,0);
			if(!context.getImageData(0,0,mask.width,mask.height).data.some((value,index)=>index%4===0&&value>0)){toast.error($i18n.t('Selecione a área que deseja editar.'));return;}
			draft.mask=exported.toDataURL('image/png');
		}
		options={...draft,source_id:imageModeSourceKey(images[0])};show=false;
	}
</script>

<svelte:window on:keydown|capture={keyboard} on:pointerdown={event=>{if(brushMenu&&!(event.target as Element).closest('[data-brush-size]'))brushMenu=false;}} on:pointerup={releaseSizeHold} on:pointercancel={()=>{endSizeHold();sizePreviewTool=null;sizeHoldOpened=null;}} />

<Modal bind:show size="md" animated={false}>
	<div class="image-mode-dialog dark:text-gray-200">
		<div class="flex justify-between px-5 pt-4 pb-3 border-b border-gray-200/30 dark:border-gray-700/20">
			<h2 class="self-center text-lg font-medium dark:text-gray-100">{$i18n.t(title)}</h2>
			<button type="button" class="self-center text-gray-500 hover:text-gray-900 dark:text-gray-300 dark:hover:text-white" aria-label={$i18n.t('Close')} on:click={()=>show=false}><XMark className="size-5" /></button>
		</div>
		{#if draft}
		<div class="mode-editor max-h-[min(65dvh,620px)] overflow-y-auto overscroll-contain px-5 py-4" class:region-editor={draft.mode==='inpaint'}>
			{#if images.length&&draft.mode==='outpaint'}<ImageOutpaintEditor bind:options={draft} source={imageModeSource(images[0])} />
			{:else if images.length}
				<div class="region-layout">
				<div class="region-tools flex shrink-0 flex-col gap-1" role="toolbar" aria-label={$i18n.t('Ferramentas de seleção')} data-mask-tools>
					<Tooltip content={$i18n.t('Mover')} placement="right"><button type="button" class="tool" class:active={tool==='move'} disabled={loading} aria-disabled={busy||loading} aria-label={$i18n.t('Mover')} aria-pressed={tool==='move'} on:click={()=>chooseTool('move')}><ImageEditorMoveIcon className="size-4" /></button></Tooltip>
					{#each [{id:'paint' as const,label:'Pincel',icon:Brush,value:brush},{id:'erase' as const,label:'Borracha',icon:Eraser,value:eraser}] as item (item.id)}
						<div data-brush-size class="relative">
							<Tooltip content={$i18n.t(item.label)} placement="right"><button type="button" class="tool size-tool" class:active={tool===item.id} disabled={loading} aria-disabled={busy||loading} aria-label={$i18n.t(item.label)} aria-pressed={tool===item.id} aria-expanded={tool===item.id&&brushMenu} on:pointerdown={event=>beginSizeHold(item.id,event)} on:pointerleave={endSizeHold} on:click={()=>activateSizeTool(item.id)}>
								<span class="tool-primary-icon">{#if sizePreviewTool===item.id}<svg viewBox="0 0 20 20" class="size-preview-circle block size-5" fill="currentColor" aria-hidden="true"><circle cx="10" cy="10" r={sizeRadius(item.value)} /></svg>{:else}<svelte:component this={item.icon} className="size-4" />{/if}</span>
								<span class="tool-corner-indicator" aria-hidden="true"></span>
							</button></Tooltip>
							{#if tool===item.id&&brushMenu}<div class="size-menu absolute left-full top-0 z-30 ml-1 w-48 rounded-lg bg-white p-3 shadow-md dark:bg-gray-850">
								<div class="flex items-center gap-3"><input type="range" class="min-w-0 flex-1" style:--brush-progress={`${(item.value-4)/156*100}%`} min="4" max="160" step="2" value={item.value} on:pointerdown={()=>sizePreviewTool=item.id} on:input={event=>changeToolSize(item.id,Number(event.currentTarget.value))} aria-label={$i18n.t(item.id==='paint'?'Tamanho do pincel':'Tamanho da borracha')} /><output class="w-10 text-right text-xs tabular-nums text-gray-500">{item.value}px</output></div>
							</div>{/if}
						</div>
					{/each}
					<Tooltip content={$i18n.t(tool==='select'&&exclude?'Remover seleção':'Selecionar objeto')} placement="right"><button type="button" class="tool" class:active={tool==='select'} class:subtract={tool==='select'&&exclude} disabled={loading} aria-disabled={busy||loading} aria-label={$i18n.t(tool==='select'&&exclude?'Remover seleção':'Selecionar objeto')} aria-pressed={tool==='select'} on:click={()=>chooseTool('select')}><SelectionBrush className="size-4" /></button></Tooltip>
					<Tooltip content={$i18n.t('Limpar')} placement="right"><button type="button" class="tool" disabled={loading||restoring} aria-disabled={busy||loading||restoring} aria-label={$i18n.t('Limpar')} on:click={clear}><Trash className="size-4" /></button></Tooltip>
				</div>
				<div class="region-image min-w-0">
				<div class="mask-field relative">
				<div bind:this={viewport} use:measureViewport role="region" aria-label={$i18n.t('Prévia da edição')} tabindex="0" class="mask-viewport relative h-[min(50dvh,480px)] min-h-32 overflow-auto overscroll-contain rounded-md" style:cursor={pan?'grabbing':tool==='move'?'grab':undefined} on:wheel|nonpassive={wheelZoom} on:pointerdown|capture={startPan} on:pointermove={movePan} on:pointerup={stopPan} on:pointercancel={stopPan} on:lostpointercapture={stopPan} on:auxclick|preventDefault>
					<div class="grid min-h-full place-items-center p-[12px]" style:width={`${Math.max(viewportWidth,fittedWidth*zoom+24)}px`}>
						<div class="relative" style:width={`${displayWidth}px`} style:height={`${displayHeight}px`}>
							{#if image}<img src={image.src} alt={$i18n.t('Prévia da edição')} class="region-source-image block size-full" draggable="false" />{/if}
							<!-- svelte-ignore a11y_no_static_element_interactions -->
							<canvas bind:this={overlay} class="absolute inset-0 h-full w-full touch-none opacity-50" style:cursor={pan?'grabbing':tool==='move'?'grab':tool==='select'?'crosshair':brushCursor} on:pointerdown={start} on:pointermove={stroke} on:pointerup={finishStroke} on:pointercancel={finishStroke}></canvas>
						</div>
					</div>
					{#if loading}<div class="absolute inset-0 grid place-items-center bg-white/50 dark:bg-black/50"><Spinner className="size-5" /></div>{/if}
				</div>
				<div class="absolute bottom-3 left-3 z-20 flex items-center gap-1 rounded-md bg-white/90 text-gray-600 dark:bg-gray-850/90 dark:text-gray-300" data-image-zoom-controls><button type="button" class="tool" aria-label={$i18n.t('Zoom out')} on:click={()=>changeZoom(zoom-.25)}><Minus className="size-4" /></button><output class="w-10 text-center text-xs tabular-nums" data-image-zoom>{Math.round(zoom*100)}%</output><button type="button" class="tool" aria-label={$i18n.t('Zoom in')} on:click={()=>changeZoom(zoom+.25)}><Plus className="size-4" /></button></div>
				</div>
				</div>
				</div>
			{/if}
		</div>
		{/if}
		<div class="flex justify-end gap-2 px-5 pb-4 pt-1 text-sm font-medium">
			<button type="button" class="rounded-lg px-4 py-1.5 text-xs font-medium bg-gray-100 hover:bg-gray-200 dark:bg-gray-850 dark:hover:bg-gray-800" on:click={()=>show=false}>{$i18n.t('Cancel')}</button>
			<button type="button" class="rounded-lg px-4 py-1.5 text-xs font-medium bg-black text-white hover:opacity-90 disabled:opacity-40 dark:bg-white dark:text-black" disabled={disabled||loading||!imageModeSource(images[0])||images[0]?.status==='uploading'} aria-disabled={busy||disabled||loading||restoring||!imageModeSource(images[0])||images[0]?.status==='uploading'} aria-busy={busy||restoring} on:click={apply}>{$i18n.t('Apply')}</button>
		</div>
	</div>
</Modal>

<style>
	.region-editor{padding-left:12px;padding-right:12px;}
	.region-layout{display:grid;grid-template-columns:32px minmax(0,1fr);column-gap:12px;align-items:start;}
	.region-tools{grid-column:1;grid-row:1;}
	.region-image{grid-column:2;grid-row:1;}
	.region-source-image{width:100%;height:100%;max-width:none;margin:0;image-rendering:auto;}
	.mask-viewport{background-color:#f5f5f5;background-image:repeating-conic-gradient(#e5e5e5 0% 25%,transparent 0% 50%);background-size:16px 16px;}
	:global(.dark) .mask-viewport{background-color:#202020;background-image:repeating-conic-gradient(#2b2b2b 0% 25%,transparent 0% 50%);}
	input[type='range']{appearance:none;-webkit-appearance:none;height:16px;accent-color:#3b82f6;background:transparent;border:0;outline:none;box-shadow:none;padding:0;}
	input[type='range']::-webkit-slider-runnable-track{height:4px;border:0;border-radius:999px;background:linear-gradient(to right,#3b82f6 var(--brush-progress),var(--brush-track,#d1d5db) var(--brush-progress));box-shadow:none;}
	input[type='range']::-moz-range-track{height:4px;border:0;border-radius:999px;background:linear-gradient(to right,#3b82f6 var(--brush-progress),var(--brush-track,#d1d5db) var(--brush-progress));box-shadow:none;}
	input[type='range']::-webkit-slider-thumb{appearance:none;-webkit-appearance:none;width:14px;height:14px;margin-top:-5px;border:0;border-radius:50%;background:#3b82f6;box-shadow:none;}
	input[type='range']::-moz-range-thumb{width:14px;height:14px;border:0;border-radius:50%;background:#3b82f6;box-shadow:none;}
	:global(.dark) input[type='range']{--brush-track:#525252;}
	.tool{position:relative;display:flex;width:32px;height:32px;flex-shrink:0;align-items:center;justify-content:center;border-radius:6px;}
	.tool:hover{background:rgb(0 0 0 / 5%);}
	:global(.dark) .tool:hover{background:rgb(255 255 255 / 8%);}
	.tool.active{color:#3b82f6;background:rgb(59 130 246 / 12%);}.tool:disabled{opacity:.35;}
	.size-tool{padding:0;}
	.tool-primary-icon{display:grid;width:20px;height:20px;flex-shrink:0;place-items:center;line-height:0;}
	.tool-primary-icon :global(svg){display:block;margin:auto;}
	.tool-primary-icon :global(.size-preview-circle){transform:translate(-1.5px,-1.5px);}
	.tool-corner-indicator{position:absolute;right:3px;bottom:3px;width:5px;height:5px;background:currentColor;clip-path:polygon(100% 0,100% 100%,0 100%);opacity:.65;}
	.tool.subtract::after{content:'';position:absolute;right:4px;bottom:5px;width:6px;height:2px;background:currentColor;}
	.mask-viewport::-webkit-scrollbar-corner{background:transparent;}
	:global(.dark) .mask-viewport{color-scheme:dark;}
</style>
