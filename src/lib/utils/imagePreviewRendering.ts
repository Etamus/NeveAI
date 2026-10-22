export const imagePreviewSize = (width:number,height:number,dpr=1) => {
	const ratio=Number.isFinite(dpr)&&dpr>0?dpr:1;
	return{width:Math.max(1,Math.round(width*ratio)),height:Math.max(1,Math.round(height*ratio))};
};

export function drawImagePreview(canvas:HTMLCanvasElement,image:HTMLImageElement,width:number,height:number,dpr=1,cover=false){
	const size=imagePreviewSize(width,height,dpr);
	canvas.width=size.width;canvas.height=size.height;
	const context=canvas.getContext('2d')!;
	context.imageSmoothingEnabled=true;context.imageSmoothingQuality='high';
	if(cover){
		const scale=Math.max(size.width/image.naturalWidth,size.height/image.naturalHeight);
		const sw=size.width/scale,sh=size.height/scale;
		context.drawImage(image,(image.naturalWidth-sw)/2,(image.naturalHeight-sh)/2,sw,sh,0,0,size.width,size.height);
	}else context.drawImage(image,0,0,size.width,size.height);
}
