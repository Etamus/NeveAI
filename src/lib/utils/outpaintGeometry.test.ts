import {describe,it,expect} from 'vitest';
import {outpaintFrame,outpaintAspect,dragOutpaintFrame,rotatedImageSize} from './outpaintGeometry';
import {imageModeDefaults} from './imageModes';
describe('direct outpaint manipulation',()=>{
	it('matches the rotated canvas geometry used by Pillow',()=>{
		expect(rotatedImageSize(864,1152,12)).toEqual([1086,1308]);
		expect(outpaintFrame(864,1152,{mode:'outpaint',rotation:12,pad_left:10,pad_right:10}).width).toBe(1258);
	});
	it('drags sides and corners without shrinking inside the source image',()=>{
		const initial=imageModeDefaults('outpaint');
		expect(dragOutpaintFrame(initial,'e',100,0,400,300).pad_right).toBe(25);
		const corner=dragOutpaintFrame(initial,'nw',-40,-30,400,300);
		expect([corner.pad_left,corner.pad_top]).toEqual([10,10]);
		expect(dragOutpaintFrame(initial,'w',1000,0,400,300).pad_left).toBe(0);
		expect(initial.pad_right).toBe(0);
	});
	it('starts with the source dimensions and fits supported ratios without cropping',()=>{
		const initial=imageModeDefaults('outpaint');
		expect(outpaintFrame(864,1152,initial)).toMatchObject({width:864,height:1152});
		for(const ratio of [1,16/9,9/16,4/3,3/4,3/2,2/3]){
			const next=outpaintAspect(864,1152,initial,ratio)!;
			const frame=outpaintFrame(864,1152,next);
			expect(Math.abs(frame.width/frame.height-ratio)).toBeLessThan(.025);
			expect(frame.width).toBeGreaterThanOrEqual(864);expect(frame.height).toBeGreaterThanOrEqual(1152);
		}
		expect(outpaintAspect(4000,100,initial,1)).toBeNull();
		expect(outpaintAspect(864,1152,initial,NaN)).toBeNull();
	});
	it('moves the source inside a fixed-size canvas',()=>{
		const initial={...imageModeDefaults('outpaint'),pad_left:20,pad_right:40,pad_top:20,pad_bottom:20};
		const moved=dragOutpaintFrame(initial,'move',40,30,400,300);
		expect([moved.pad_left,moved.pad_right,moved.pad_top,moved.pad_bottom]).toEqual([30,30,30,10]);
		expect(outpaintFrame(400,300,moved).width).toBe(outpaintFrame(400,300,initial).width);
	});
});
