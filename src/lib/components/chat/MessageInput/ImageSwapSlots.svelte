<script lang="ts">
	import {getContext,tick} from 'svelte';
	import {toast} from 'svelte-sonner';
	import Upload from '$lib/components/icons/Upload.svelte';
	import AttachmentRemoveButton from '$lib/components/common/AttachmentRemoveButton.svelte';
	import Settings from '$lib/components/icons/Settings.svelte';
	import AttachmentThumbnail from '$lib/components/common/AttachmentThumbnail.svelte';
	import ImageModeThumbnail from './ImageModeThumbnail.svelte';
	import {imageModeFiles,imageModeSource,imageSwapSlots,imageModeHasEditor,imageModeHasPreview,imageModeAttachmentLimit,type ImageModeOptions} from '$lib/utils/imageModes';
	import {attachmentScroller} from '$lib/utils/attachmentScroll';
	const i18n=getContext('i18n');
	export let mode:'outfit'|'body'|'restore'|'inpaint'|'outpaint'='outfit';
	export let options:ImageModeOptions={mode:'normal'};
	export let onEdit:()=>void=()=>{};
	export let files:any[]=[];
	export let uploadFiles:(files:File[])=>Promise<void>;
	export let disabled=false;
	let input:HTMLInputElement,busy=false;
	let suppressRemoveAt:{x:number;y:number}|null=null;
	let target:{role:'base'|'reference';file?:any}={role:'base'};
	$: assigned=imageSwapSlots(files);
	$: attachedImages=imageModeFiles(files);
	$: single=mode==='restore'||imageModeHasEditor(mode);
	$: limit=imageModeAttachmentLimit(mode);
	let pendingThumbnails=new Set<string>();
	$: uploading=busy||files.some(file=>file.status==='uploading')||files.some(file=>pendingThumbnails.has(key(file)));
	$: slots=single?[{role:'base' as const,file:attachedImages[0],label:'Referência'}]:[{role:'base' as const,file:assigned.base,label:'Referência'},...assigned.references.map((file,index)=>({role:'reference' as const,file,label:mode==='outfit'?`${$i18n.t('Roupa')} ${index+1}`:`${$i18n.t('Pessoa')} ${index+1}`})),...(!uploading&&attachedImages.length>0&&assigned.references.length<limit-1?[{role:'reference' as const,file:undefined,label:mode==='outfit'?'Roupa':'Pessoa'}]:[])];
	const localKeys=new WeakMap<object,string>();let nextKey=0;
	const key=(file:any)=>{
		if(!file)return '';
		if(file.itemId||file.id)return String(file.itemId||file.id);
		if(!localKeys.has(file))localKeys.set(file,`local-${++nextKey}`);
		return localKeys.get(file)!;
	};
	function withRole(file:any,role:string){if(file.image_mode_role===role)return file;const copy={...file,image_mode_role:role};localKeys.set(copy,key(file));return copy;}
	function normalize(value:any[]){const current=imageSwapSlots(value);return value.map(file=>{
		if(!imageModeFiles(value).includes(file))return file;
		return withRole(file,file===current.base?'base':'reference');
	});}
	function ordered(value:any[]){return [...value.filter(file=>file.image_mode_role==='base'),...value.filter(file=>file.image_mode_role!=='base')];}
	async function upload(selected:File[],replace=false){
		if(busy||disabled||!selected.length)return;
		const replaced=replace?target.file:undefined;
		const capacity=limit-files.length+(replaced?1:0);
		if(selected.length>capacity)toast.error($i18n.t(limit===1?'Este modo aceita at\u00e9 1 imagem.':'Este modo aceita at\u00e9 {{count}} imagens.',{count:limit}));
		if(capacity<=0){input.value='';return;}
		const role=!replaced&&target.file&&!single?'reference':target.role;
		const previous=normalize(files);
		const before=new Set(previous.map(key));busy=true;
		files=previous.filter(file=>key(file)!==key(replaced));
		try{
			await uploadFiles(selected.slice(0,role==='base'?1:capacity));await tick();
			const added=files.filter(file=>!before.has(key(file))&&file.status!=='error');
			if(!added.length){if(replaced)files=ordered([...files,replaced]);return;}
			files=ordered(files.map(file=>added.includes(file)?withRole(file,role):file));
		}catch(error){if(replaced)files=ordered([...files,replaced]);toast.error(String(error));}
		finally{busy=false;if(input)input.value='';}
	}
	function choose(slot:typeof target,event:MouseEvent){
		if(busy||disabled)return;
		target=slot;
		suppressRemoveAt={x:event.clientX,y:event.clientY};
		input.click();
	}
	function releaseRemoveSuppression(event:PointerEvent){
		if(!suppressRemoveAt)return;
		if(Math.hypot(event.clientX-suppressRemoveAt.x,event.clientY-suppressRemoveAt.y)>2)suppressRemoveAt=null;
	}
	function thumbnailPending(file:any,pending:boolean){
		const id=key(file);
		if(pendingThumbnails.has(id)===pending)return;
		pendingThumbnails=new Set(pendingThumbnails);
		if(pending)pendingThumbnails.add(id);else pendingThumbnails.delete(id);
	}
	function move(source:string,slot:typeof target){
		if(busy||disabled)return;
		const values=normalize(files),from=values.find(file=>key(file)===source),to=values.find(file=>key(file)===key(slot.file));if(!from||from===to)return;
		if(slot.role==='base'||from.image_mode_role==='base'){
			if(from.image_mode_role==='base'&&!to)return;
			files=ordered(values.map(file=>file===from?withRole(file,slot.role):file===to?withRole(file,from.image_mode_role):file));
		}else if(to){const a=values.indexOf(from),b=values.indexOf(to);[values[a],values[b]]=[values[b],values[a]];files=values;}
	}
</script>

<input bind:this={input} type="file" accept="image/*" multiple={target.role==='reference'} hidden on:change={event=>upload(Array.from((event.currentTarget as HTMLInputElement).files??[]),!!target.file)} aria-label={$i18n.t('Adicionar imagem ao slot')} />
<div class="image-swap-slots composer-attachment-strip image-role-attachments mx-2 mt-2.5 mb-1 flex min-w-0 max-w-full items-start gap-2 overflow-x-auto overflow-y-hidden px-1 pt-1 pb-1" class:single-image-attachment={single&&mode!=='inpaint'} use:attachmentScroller>
	{#each slots as slot,index (slot.file?key(slot.file):`empty-${slot.role}`)}
		{@const compactReference=!slot.file&&attachedImages.length>0&&slot.role==='reference'}
		<!-- svelte-ignore a11y_no_static_element_interactions -->
		<div class="group group/attachment relative h-[62px] {compactReference?'w-[84px]':'w-[146px]'} shrink-0 rounded-md border border-dashed border-gray-300 dark:border-gray-700" on:pointermove={releaseRemoveSuppression} on:pointerleave={()=>suppressRemoveAt=null} on:dragover|preventDefault on:drop|preventDefault={event=>{target=slot;const source=event.dataTransfer?.getData('application/neve-image-slot');if(source)move(source,slot);else upload(Array.from(event.dataTransfer?.files??[]));}}>
			<button type="button" data-image-slot={index===0?'base':`reference-${index}`} class="flex size-full items-center {compactReference?'justify-start gap-1.5 pl-3 pr-5':'gap-2 px-2 text-left'} rounded-md hover:bg-gray-100 dark:hover:bg-gray-800" disabled={disabled||busy} aria-label={`${$i18n.t('Selecionar')} ${$i18n.t(slot.label)}`} on:click={event=>choose(slot,event)}>
				<span class="slot-content grid {compactReference?'size-5 -translate-x-[3px]':'size-10'} shrink-0 place-items-center overflow-hidden rounded text-gray-400">
					{#if slot.file&&(slot.file.status==='uploading'||imageModeSource(slot.file))}
						{#if slot.file.status!=='uploading'&&imageModeHasPreview(options)}<ImageModeThumbnail file={slot.file} {options} />
						{:else}<AttachmentThumbnail pending={slot.file.status==='uploading'} className="size-full object-cover" draggable={true} on:loading={event=>thumbnailPending(slot.file,event.detail)} on:dragstart={event=>event.dataTransfer?.setData('application/neve-image-slot',key(slot.file))} src={imageModeSource(slot.file)} alt={$i18n.t(slot.label)} />{/if}
					{:else if attachedImages.length}<span class="text-lg leading-none">+</span>
					{:else}<Upload className="size-4" />{/if}
				</span><span class="slot-content {compactReference?'flex size-5 shrink-0 -translate-x-[3px] items-center justify-center':''} min-w-0 whitespace-nowrap text-xs text-gray-600 dark:text-gray-300">
					{#if !slot.file&&attachedImages.length&&slot.role==='reference'}
						{#if mode==='outfit'}
							<svg viewBox="0 0 24 24" fill="none" class="size-5 translate-y-[1.5px]" aria-label={$i18n.t('Roupa')}><path d="M3 7L6 4H9C9 4.39397 9.0776 4.78407 9.22836 5.14805C9.37913 5.51203 9.6001 5.84274 9.87868 6.12132C10.1573 6.3999 10.488 6.62087 10.8519 6.77164C11.2159 6.9224 11.606 7 12 7C12.394 7 12.7841 6.9224 13.1481 6.77164C13.512 6.62087 13.8427 6.3999 14.1213 6.12132C14.3999 5.84274 14.6209 5.51203 14.7716 5.14805C14.9224 4.78407 15 4.39397 15 4H18L21 7L20.5785 11.2152C20.542 11.5801 20.1382 11.7829 19.8237 11.5942L18 10.5V18C18 19.1046 17.1046 20 16 20H8C6.89543 20 6 19.1046 6 18V10.5L4.17629 11.5942C3.86184 11.7829 3.45801 11.5801 3.42152 11.2152L3 7Z" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" /></svg>
						{:else}
							<svg viewBox="0 0 32 32" fill="currentColor" class="size-4.5" aria-label={$i18n.t('Pessoa')}><path d="M23.313 26.102l-6.296-3.488c2.34-1.841 2.976-5.459 2.976-7.488v-4.223c0-2.796-3.715-5.91-7.447-5.91-3.73 0-7.544 3.114-7.544 5.91v4.223c0 1.845 0.78 5.576 3.144 7.472l-6.458 3.503s-1.688 0.752-1.688 1.689v2.534c0 0.933 0.757 1.689 1.688 1.689h21.625c0.931 0 1.688-0.757 1.688-1.689v-2.534c0-0.994-1.689-1.689-1.689-1.689zM23.001 30.015h-21.001v-1.788c0.143-0.105 0.344-0.226 0.502-0.298 0.047-0.021 0.094-0.044 0.139-0.070l6.459-3.503c0.589-0.32 0.979-0.912 1.039-1.579s-0.219-1.32-0.741-1.739c-1.677-1.345-2.396-4.322-2.396-5.911v-4.223c0-1.437 2.708-3.91 5.544-3.91 2.889 0 5.447 2.44 5.447 3.91v4.223c0 1.566-0.486 4.557-2.212 5.915-0.528 0.416-0.813 1.070-0.757 1.739s0.446 1.267 1.035 1.589l6.296 3.488c0.055 0.030 0.126 0.063 0.184 0.089 0.148 0.063 0.329 0.167 0.462 0.259v1.809zM30.312 21.123l-6.39-3.488c2.34-1.841 3.070-5.459 3.070-7.488v-4.223c0-2.796-3.808-5.941-7.54-5.941-2.425 0-4.904 1.319-6.347 3.007 0.823 0.051 1.73 0.052 2.514 0.302 1.054-0.821 2.386-1.308 3.833-1.308 2.889 0 5.54 2.47 5.54 3.941v4.223c0 1.566-0.58 4.557-2.305 5.915-0.529 0.416-0.813 1.070-0.757 1.739 0.056 0.67 0.445 1.267 1.035 1.589l6.39 3.488c0.055 0.030 0.126 0.063 0.184 0.089 0.148 0.063 0.329 0.167 0.462 0.259v1.779h-4.037c0.61 0.46 0.794 1.118 1.031 2h3.319c0.931 0 1.688-0.757 1.688-1.689v-2.503c-0.001-0.995-1.689-1.691-1.689-1.691z" /></svg>
						{/if}
					{:else}{$i18n.t(slot.file || attachedImages.length ? slot.label : 'Adicionar')}{/if}
				</span>
			</button>
			{#if slot.file&&!suppressRemoveAt}<AttachmentRemoveButton framed={true} topOffset="-top-0.5" disabled={disabled||busy} label={`${$i18n.t('Remove')} ${$i18n.t(slot.label)}`} on:click={()=>files=normalize(files).filter(file=>key(file)!==key(slot.file))} />{/if}
		</div>
	{/each}
	{#if imageModeHasEditor(mode)&&attachedImages.length}
		<button type="button" data-image-mode-edit aria-label={$i18n.t('Ajustar edição')} on:click={onEdit} disabled={disabled||busy||!imageModeFiles(files).length}
			class="grid h-[62px] w-[62px] shrink-0 place-items-center rounded-md border border-dashed border-gray-300 text-gray-500 hover:bg-gray-100 dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-800"><Settings className="size-4.5" /></button>
	{/if}
</div>
