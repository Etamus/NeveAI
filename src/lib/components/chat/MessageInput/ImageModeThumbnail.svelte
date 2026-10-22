<script lang="ts">
	import {onDestroy} from 'svelte';
	import {imageModeSource,type ImageModeOptions} from '$lib/utils/imageModes';
	import {outpaintFrame} from '$lib/utils/outpaintGeometry';
	import Spinner from '$lib/components/common/Spinner.svelte';
	export let file:any;
	export let options:ImageModeOptions;
	let canvas:HTMLCanvasElement;
	let ready=false,revision=0,renderedSource='';
	let decodedSource='',decodedImage:Promise<HTMLImageElement>;
	function loadSource(url:string){
		if(decodedSource!==url){
			decodedSource=url;
			const image=new Image();image.decoding='async';image.src=url;
			decodedImage=image.decode().then(()=>image).catch(error=>{if(decodedSource===url)decodedSource='';throw error;});
		}
		return decodedImage;
	}
	$: source=imageModeSource(file);
	$: if(canvas&&source)void draw(source,options);
	onDestroy(()=>{revision++;});
	function observe(node:HTMLCanvasElement){
		let frame:number;
		const update=()=>{cancelAnimationFrame(frame);frame=requestAnimationFrame(()=>{if(source)void draw(source,options);});};
		const observer=new ResizeObserver(update);if(node.parentElement)observer.observe(node.parentElement);window.addEventListener('resize',update);
		return{destroy(){observer.disconnect();cancelAnimationFrame(frame);window.removeEventListener('resize',update);}};
	}
	async function draw(url:string,settings:ImageModeOptions){
		const version=++revision;if(url!==renderedSource)ready=false;
		try{
			const image=await loadSource(url);if(version!==revision)return;
			const width=image.naturalWidth,height=image.naturalHeight;
			const frame=settings.mode==='outpaint'?outpaintFrame(width,height,settings):{width,height,left:0,top:0,rotatedWidth:width,rotatedHeight:height};
			const box=canvas.parentElement;
			const output=document.createElement('canvas');
			output.width=Math.max(1,Math.round((box?.clientWidth||40)*(window.devicePixelRatio||1)));
			output.height=Math.max(1,Math.round((box?.clientHeight||40)*(window.devicePixelRatio||1)));
			// Crop only the thumbnail, preserving the editor frame and selection coordinates.
			const scale=Math.max(output.width/frame.width,output.height/frame.height);
			const left=(output.width-frame.width*scale)/2,top=(output.height-frame.height*scale)/2;
			const context=output.getContext('2d')!;
			context.imageSmoothingEnabled=true;context.imageSmoothingQuality='high';
			if(settings.mode==='outpaint'){
				for(let y=0;y<output.height;y+=8)for(let x=0;x<output.width;x+=8){context.fillStyle=((x+y)/8)%2?'#737373':'#a3a3a3';context.fillRect(x,y,8,8);}
				context.save();context.translate(left,top);context.scale(scale,scale);context.translate(frame.left+frame.rotatedWidth/2,frame.top+frame.rotatedHeight/2);context.rotate(-(settings.rotation??0)*Math.PI/180);context.drawImage(image,-width/2,-height/2);context.restore();
			}else{
				context.drawImage(image,left,top,width*scale,height*scale);
				if(settings.mask){
					const mask=new Image();mask.src=settings.mask;await mask.decode();if(version!==revision)return;
					const tint=document.createElement('canvas');tint.width=output.width;tint.height=output.height;
					const maskContext=tint.getContext('2d')!;maskContext.drawImage(mask,left,top,width*scale,height*scale);
					const pixels=maskContext.getImageData(0,0,tint.width,tint.height);
					for(let i=0;i<pixels.data.length;i+=4){const alpha=pixels.data[i]*.55;pixels.data[i]=59;pixels.data[i+1]=130;pixels.data[i+2]=246;pixels.data[i+3]=alpha;}
					maskContext.putImageData(pixels,0,0);context.drawImage(tint,0,0);
				}
			}
			if(version!==revision)return;
			const target=canvas;
			target.width=output.width;target.height=output.height;target.getContext('2d')!.drawImage(output,0,0);renderedSource=url;ready=true;
		}catch{if(version===revision)ready=false;}
	}
</script>

{#if !ready}<Spinner className="size-4" />{/if}
<canvas bind:this={canvas} use:observe data-image-mode-thumbnail={options.mode} class="size-full object-cover" class:hidden={!ready} aria-hidden="true"></canvas>
