import {describe,it,expect,vi} from 'vitest';
import {imagePreviewSize,drawImagePreview} from './imagePreviewRendering';
describe('display-resolution image previews',()=>{
	it('renders at device-pixel resolution, including fractional CSS sizes',()=>{
		expect(imagePreviewSize(41.4,41.4,2)).toEqual({width:83,height:83});
		expect(imagePreviewSize(400,300,1.5)).toEqual({width:600,height:450});
		expect(imagePreviewSize(0,0,NaN)).toEqual({width:1,height:1});
	});
	it('draws directly from the original at each zoom, without a reduced intermediate',()=>{
		const context={imageSmoothingEnabled:false,imageSmoothingQuality:'low',drawImage:vi.fn()};
		const canvas={width:0,height:0,getContext:()=>context} as unknown as HTMLCanvasElement;
		const image={naturalWidth:2400,naturalHeight:1600} as HTMLImageElement;
		drawImagePreview(canvas,image,600,400,2);drawImagePreview(canvas,image,900,600,2);
		expect(context.drawImage.mock.calls).toEqual([[image,0,0,1200,800],[image,0,0,1800,1200]]);
		expect(context.imageSmoothingQuality).toBe('high');
	});
	it('uses a centered source crop for cover thumbnails without changing the file',()=>{
		const context={imageSmoothingEnabled:false,imageSmoothingQuality:'low',drawImage:vi.fn()};
		const canvas={width:0,height:0,getContext:()=>context} as unknown as HTMLCanvasElement;
		const image={naturalWidth:200,naturalHeight:100} as HTMLImageElement;
		drawImagePreview(canvas,image,40,40,2,true);
		expect(context.drawImage).toHaveBeenCalledWith(image,50,0,100,100,0,0,80,80);
	});
});
