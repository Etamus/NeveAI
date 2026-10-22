import type { ImageModeOptions } from './imageModes';
export type OutpaintHandle = 'n'|'ne'|'e'|'se'|'s'|'sw'|'w'|'nw'|'move'|'rotate';
export const rotatedImageSize = (width: number, height: number, degrees: number) => {
	const angle = degrees * Math.PI / 180;
	const w = Math.abs(width * Math.cos(angle)) + Math.abs(height * Math.sin(angle));
	const h = Math.abs(height * Math.cos(angle)) + Math.abs(width * Math.sin(angle));
	return [Math.ceil((width + w) / 2) - Math.floor((width - w) / 2), Math.ceil((height + h) / 2) - Math.floor((height - h) / 2)];
};
export const outpaintFrame = (width: number, height: number, options: ImageModeOptions) => {
	const [rw,rh] = rotatedImageSize(width,height,options.rotation??0);
	const left=Math.round(width*(options.pad_left??0)/100), right=Math.round(width*(options.pad_right??0)/100);
	const top=Math.round(height*(options.pad_top??0)/100), bottom=Math.round(height*(options.pad_bottom??0)/100);
	return {left,top,right,bottom,rotatedWidth:rw,rotatedHeight:rh,width:rw+left+right,height:rh+top+bottom};
};
export const outpaintAspect = (width:number,height:number,options:ImageModeOptions,ratio:number):ImageModeOptions|null => {
	if(!Number.isFinite(ratio)||ratio<=0)return null;
	const [rw,rh]=rotatedImageSize(width,height,options.rotation??0);
	const targetWidth=Math.max(rw,rh*ratio),targetHeight=targetWidth/ratio;
	const horizontal=(targetWidth-rw)/width*50,vertical=(targetHeight-rh)/height*50;
	if(horizontal>100||vertical>100)return null;
	return{...options,pad_left:Math.round(horizontal),pad_right:Math.round(horizontal),pad_top:Math.round(vertical),pad_bottom:Math.round(vertical)};
};
export const dragOutpaintFrame = (initial: ImageModeOptions, handle: OutpaintHandle, dx: number, dy: number, width: number, height: number): ImageModeOptions => {
	const next={...initial};
	const clamp=(value:number)=>Math.max(0,Math.min(100,Math.round(value)));
	if(handle==='move') {
		const x=Math.max(-(initial.pad_left??0),Math.min(initial.pad_right??0,dx/width*100));
		const y=Math.max(-(initial.pad_top??0),Math.min(initial.pad_bottom??0,dy/height*100));
		next.pad_left=clamp((initial.pad_left??0)+x);next.pad_right=clamp((initial.pad_right??0)-x);
		next.pad_top=clamp((initial.pad_top??0)+y);next.pad_bottom=clamp((initial.pad_bottom??0)-y);
	} else {
		if(handle.includes('w'))next.pad_left=clamp((initial.pad_left??0)-dx/width*100);
		if(handle.includes('e'))next.pad_right=clamp((initial.pad_right??0)+dx/width*100);
		if(handle.includes('n'))next.pad_top=clamp((initial.pad_top??0)-dy/height*100);
		if(handle.includes('s'))next.pad_bottom=clamp((initial.pad_bottom??0)+dy/height*100);
	}
	return next;
};
