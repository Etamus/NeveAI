<script lang="ts">
	import { getContext, onMount } from 'svelte';
	import { preloadImageModeThumbnails, mountImageModeThumbnail } from '$lib/utils/imageModeThumbnails';
	import { IMAGE_MODES, imageModeDefaults, imageModeAvailable, type ImageModeOptions } from '$lib/utils/imageModes';
	import CheckCircle from '$lib/components/icons/CheckCircle.svelte';
	const i18n = getContext('i18n');
	export let options: ImageModeOptions = imageModeDefaults();
	export let files: any[] = [];
	export let show = false;
	export let ongoing = false;
	export let position: (node: HTMLElement, options?: any) => any;
	export let scroller: (node: HTMLElement) => any;
	export let onOpen: () => void = () => {};
	export let disabled = false;
	let panelReady=false;
	function placePanel(node:HTMLElement,settings:any){
		panelReady=false;node.style.visibility='hidden';
		const action=position(node,{...settings,immediate:true});
		node.style.visibility='';panelReady=true;
		return{destroy(){action?.destroy?.();}};
	}
	$: label = IMAGE_MODES.find(mode => mode.id === options.mode)?.label ?? 'Padrão';
	onMount(()=>{void preloadImageModeThumbnails();});
	function close(){show=false;}
	function toggle(){
		if(show){close();return;}
		onOpen();show=true;
	}
	function choose(mode:typeof IMAGE_MODES[number]['id']){
		if(options.mode!==mode)options=imageModeDefaults(mode);
		close();
	}
	function keyNavigation(event:KeyboardEvent){
		if((event.target as Element)?.closest('[role="scrollbar"]'))return;
		if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;
		const buttons=Array.from((event.currentTarget as HTMLElement).querySelectorAll<HTMLButtonElement>('[role="menuitemradio"]:not(:disabled)'));
		const index=buttons.indexOf(document.activeElement as HTMLButtonElement);
		const next=event.key==='Home'?0:event.key==='End'?buttons.length-1:Math.max(0,Math.min(buttons.length-1,index+(event.key==='ArrowLeft'?-1:1)));
		buttons[next]?.focus({preventScroll:true});buttons[next]?.scrollIntoView({block:'nearest',inline:'nearest'});event.preventDefault();
	}
</script>

<svelte:window on:click={(event) => {
	if (show && !(event.target as Element).closest('#image-mode-dropdown-container, #image-mode-dropdown')) close();
}} on:keydown={(event) => { if (event.key === 'Escape') close(); }} />

<div id="image-mode-dropdown-container" class="relative flex shrink-0 items-center">
	<button type="button" aria-label={$i18n.t('Modo de imagem')} aria-expanded={show}
		class="flex shrink-0 items-center gap-1 rounded-full px-2 py-[7px] text-[0.8125rem] text-gray-600 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-800"
		on:click={toggle}>
		<span>{$i18n.t(label)}</span><svg viewBox="0 0 20 20" fill="currentColor" class="size-3.5 transition-transform duration-150 {show?'':'rotate-180'}" aria-hidden="true"><path fill-rule="evenodd" d="M14.78 12.78a.75.75 0 0 1-1.06 0L10 9.06l-3.72 3.72a.75.75 0 0 1-1.06-1.06l4.25-4.25a.75.75 0 0 1 1.06 0l4.25 4.25a.75.75 0 0 1 0 1.06Z" clip-rule="evenodd" /></svg>
	</button>
	{#if show}
		<div id="image-mode-dropdown" use:placePanel={{fullWidth:true,positionAnchorId:'message-input-container',fitAvailableHeight:true}} role="menu" tabindex="-1" aria-label={$i18n.t('Modo de imagem')}
			class="fixed z-50 text-sm" class:mode-thumbnails-ready={panelReady} style:--image-style-dropdown-enter-y={ongoing?'6px':'-6px'} on:keydown={keyNavigation}>
			<div class="mode-card-strip flex w-full items-start gap-1.5">
				<button type="button" role="menuitemradio" aria-checked={options.mode==='normal'} disabled={disabled} on:click={()=>choose('normal')}
					class="relative aspect-[4/5] w-[calc((100%_-.75rem)/3)] sm:w-[calc((100%_-_1.5rem)/5)] shrink-0 overflow-hidden rounded-md border-0 p-0 text-left outline-hidden focus-visible:ring-2 focus-visible:ring-gray-400 {options.mode==='normal'?'bg-gray-200 dark:bg-gray-700':'bg-gray-100 hover:bg-gray-200 dark:bg-gray-800 dark:hover:bg-gray-700'}">
					<span class="absolute inset-x-0 bottom-0 px-2 pb-2 text-xs font-medium leading-5 text-gray-700 dark:text-gray-200">{$i18n.t('Padrão')}</span>
					{#if options.mode==='normal'}<CheckCircle className="absolute right-2 top-2 size-4 text-gray-700 dark:text-gray-100" strokeWidth="2" />{/if}
				</button>
				<div class="min-w-0 flex-1" use:scroller>
					<div id="image-mode-options-viewport" data-style-options-viewport class="scrollbar-none overflow-x-auto overflow-y-hidden overscroll-x-none">
						<div class="grid grid-flow-col auto-cols-[calc((100%_-.375rem)/2)] sm:auto-cols-[calc((100%_-_1.125rem)/4)] gap-1.5">
							{#each IMAGE_MODES.slice(1) as mode}
								<button type="button" role="menuitemradio" aria-checked={options.mode===mode.id} aria-label={$i18n.t(mode.label)} disabled={disabled||!imageModeAvailable(mode.id,files)} on:click={()=>choose(mode.id)}
									class="relative aspect-[4/5] w-full overflow-hidden rounded-md border-0 bg-gray-200 p-0 text-left outline-hidden hover:brightness-110 disabled:cursor-not-allowed disabled:brightness-50 disabled:hover:brightness-50 focus-visible:ring-2 focus-visible:ring-gray-400 dark:bg-gray-800">
									<span class="absolute inset-0" aria-hidden="true" use:mountImageModeThumbnail={mode.image}></span>
									<span class="absolute inset-x-0 bottom-0 bg-linear-to-t from-black/80 via-black/35 to-transparent px-2 pb-2 pt-8 text-[10px] sm:text-xs font-medium leading-4 text-white"><span class="block">{$i18n.t(mode.label)}</span></span>
									{#if options.mode===mode.id}<CheckCircle className="absolute right-2 top-2 size-4 text-white drop-shadow-md" strokeWidth="2" />{/if}
								</button>
							{/each}
						</div>
					</div>
					<div data-style-options-track class="mt-1 flex h-2 cursor-pointer items-center rounded-full outline-hidden focus-visible:ring-2 focus-visible:ring-gray-400" role="scrollbar" tabindex="0" aria-label={$i18n.t('Modos de imagem')} aria-controls="image-mode-options-viewport" aria-orientation="horizontal" aria-valuemin="0" aria-valuemax="0" aria-valuenow="0">
						<div data-style-options-thumb class="h-1 rounded-full bg-gray-300 dark:bg-gray-600"></div>
					</div>
				</div>
			</div>
		</div>
	{/if}
</div>

<style>
	.mode-card-strip{position:relative;isolation:isolate;}
	.mode-card-strip::before{content:'';position:absolute;inset:0 0 .75rem;z-index:-1;border-radius:6px;background:rgb(255 255 255 / 75%);backdrop-filter:blur(10px);clip-path:inset(0 round 6px);mask-image:linear-gradient(to bottom,transparent,#000 6%,#000 94%,transparent);pointer-events:none;}
	:global(.dark) .mode-card-strip::before{background:rgb(0 0 0 / 72%);}
	.mode-thumbnails-ready{animation:enter-mode-cards 180ms cubic-bezier(.33,1,.68,1);}
	@keyframes enter-mode-cards{from{opacity:0;transform:translateY(var(--image-style-dropdown-enter-y,-6px));}to{opacity:1;transform:translateY(0);}}
</style>
