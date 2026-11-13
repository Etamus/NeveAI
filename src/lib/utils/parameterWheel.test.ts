import {describe, expect, it, vi} from 'vitest';
import {parameterWheel} from './parameterWheel';

describe('Advanced parameter wheel',()=>{
	const setup=()=>{
		let listener: Function=()=>{};
		const node={scrollTop:100,scrollHeight:1000,clientHeight:300,addEventListener:vi.fn((_name,fn)=>listener=fn),removeEventListener:vi.fn()};
		const action=parameterWheel(node as unknown as HTMLElement);
		const wheel=(patch={})=>{const event={deltaX:0,deltaY:120,deltaMode:0,ctrlKey:false,shiftKey:false,preventDefault:vi.fn(),...patch};listener(event);return event;};
		return {node,action,wheel};
	};
	it('limits coarse mouse input and clamps both ends',()=>{
		const {node,wheel}=setup();
		expect(wheel().preventDefault).toHaveBeenCalled();expect(node.scrollTop).toBe(148);
		node.scrollTop=690;wheel();expect(node.scrollTop).toBe(700);
		node.scrollTop=10;wheel({deltaY:-120});expect(node.scrollTop).toBe(0);
	});
	it.each([{deltaY:4},{ctrlKey:true},{shiftKey:true},{deltaX:150}])('preserves fine gestures, zoom and horizontal input %j',patch=>{
		const {node,wheel}=setup();expect(wheel(patch).preventDefault).not.toHaveBeenCalled();expect(node.scrollTop).toBe(100);
	});
	it('cleans up its listener',()=>{const {node,action}=setup();action.destroy();expect(node.removeEventListener).toHaveBeenCalledWith('wheel',expect.any(Function));});
});
