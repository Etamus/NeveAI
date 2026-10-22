<script lang="ts">
	import {getContext,tick} from 'svelte';
	import {toast} from 'svelte-sonner';
	import Photo from '$lib/components/icons/Photo.svelte';
	import Plus from '$lib/components/icons/Plus.svelte';
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
	let target:{role:'base'|'reference';file?:any}={role:'base'};
	$: assigned=imageSwapSlots(files);
	$: single=mode==='restore'||imageModeHasEditor(mode);
	$: limit=imageModeAttachmentLimit(mode);
	let pendingThumbnails=new Set<string>();
	$: uploading=busy||files.some(file=>file.status==='uploading')||files.some(file=>pendingThumbnails.has(key(file)));
	$: slots=single?[{role:'base' as const,file:imageModeFiles(files)[0],label:'Imagem'}]:[{role:'base' as const,file:assigned.base,label:'Imagem'},...assigned.references.map((file,index)=>({role:'reference' as const,file,label:mode==='outfit'?`${$i18n.t('Roupa')} ${index+1}`:`${$i18n.t('Pessoa')} ${index+1}`})),...(!uploading&&assigned.references.length<limit-1?[{role:'reference' as const,file:undefined,label:mode==='outfit'?'Roupa':'Pessoa'}]:[])];
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
	function choose(slot:typeof target){target=slot;input.click();}
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
		<!-- svelte-ignore a11y_no_static_element_interactions -->
		<div class="group group/attachment relative h-[62px] w-[154px] shrink-0 rounded-md border border-dashed border-gray-300 dark:border-gray-700" on:dragover|preventDefault on:drop|preventDefault={event=>{target=slot;const source=event.dataTransfer?.getData('application/neve-image-slot');if(source)move(source,slot);else upload(Array.from(event.dataTransfer?.files??[]));}}>
			<button type="button" data-image-slot={index===0?'base':`reference-${index}`} class="flex size-full items-center gap-2 rounded-md px-2 text-left hover:bg-gray-100 dark:hover:bg-gray-800" disabled={disabled||busy} aria-label={`${$i18n.t('Selecionar')} ${$i18n.t(slot.label)}`} on:click={()=>choose(slot)}>
				<span class="slot-content grid size-10 shrink-0 place-items-center overflow-hidden rounded text-gray-400">
					{#if slot.file&&(slot.file.status==='uploading'||imageModeSource(slot.file))}
						{#if slot.file.status!=='uploading'&&imageModeHasPreview(options)}<ImageModeThumbnail file={slot.file} {options} />
						{:else}<AttachmentThumbnail pending={slot.file.status==='uploading'} className="size-full object-cover" draggable={true} on:loading={event=>thumbnailPending(slot.file,event.detail)} on:dragstart={event=>event.dataTransfer?.setData('application/neve-image-slot',key(slot.file))} src={imageModeSource(slot.file)} alt={$i18n.t(slot.label)} />{/if}
					{:else if index===0}<Photo className="size-5" />{:else}<Plus className="size-4" />{/if}
				</span><span class="slot-content min-w-0 text-xs text-gray-600 dark:text-gray-300">{$i18n.t(slot.label)}</span>
			</button>
			{#if slot.file}<AttachmentRemoveButton framed={true} topOffset="-top-0.5" disabled={disabled||busy} label={`${$i18n.t('Remove')} ${$i18n.t(slot.label)}`} on:click={()=>files=normalize(files).filter(file=>key(file)!==key(slot.file))} />{/if}
		</div>
	{/each}
	{#if imageModeHasEditor(mode)}
		<button type="button" data-image-mode-edit aria-label={$i18n.t('Ajustar edição')} on:click={onEdit} disabled={disabled||busy||!imageModeFiles(files).length}
			class="grid h-[62px] w-[62px] shrink-0 place-items-center rounded-md border border-dashed border-gray-300 text-gray-500 hover:bg-gray-100 dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-800"><Settings className="size-4.5" /></button>
	{/if}
</div>
