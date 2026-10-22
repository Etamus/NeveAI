<script lang="ts">
	import {createEventDispatcher,onDestroy,onMount} from 'svelte';
	import Spinner from './Spinner.svelte';
	import {acquireAttachmentThumbnail} from '$lib/utils/attachmentThumbnails';
	export let src='';
	export let alt='';
	export let className='size-full object-cover';
	export let draggable=false;
	export let loadingBackground=false;
	export let pending=false;
	let loadedSource='';
	let displaySource='',mounted=false,revision=0;
	let release=()=>{};
	const dispatch=createEventDispatcher<{loading:boolean}>();
	$: ready=!pending&&Boolean(src)&&loadedSource===src;
	$: dispatch('loading',!ready);
	$: if(mounted)prepare(src,pending);
	onMount(()=>{mounted=true;dispatch('loading',!ready);});
	onDestroy(()=>{revision++;release();dispatch('loading',false);});
	async function prepare(source:string,uploading:boolean){
		const version=++revision;release();release=()=>{};loadedSource='';displaySource='';
		if(!source||uploading){displaySource='';return;}
		const thumbnail=acquireAttachmentThumbnail(source);release=thumbnail.release;
		const result=await thumbnail.ready;
		if(version===revision)displaySource=result;
	}
	async function loaded(event:Event){
		const image=event.currentTarget as HTMLImageElement,source=src,version=revision;
		try{await image.decode();if(version===revision&&source===src)loadedSource=source;}catch{}
	}
</script>
<span class="attachment-thumbnail relative block shrink-0 overflow-hidden {className}">
	<img src={displaySource||undefined} decoding="async" {alt} {draggable} class="size-full object-cover" class:invisible={!ready} on:load={loaded} on:error={()=>dispatch('loading',false)} on:dragstart />
	{#if !ready}<span class="absolute inset-0 grid place-items-center {loadingBackground?'bg-gray-200 dark:bg-gray-800':''}" aria-hidden="true"><Spinner className="size-4" /></span>{/if}
</span>
<style>
	.attachment-thumbnail img{border-radius:inherit;object-fit:inherit;}
</style>
