import {afterEach,describe,expect,it,vi} from 'vitest';
import {attachmentScroller} from './attachmentScroll';
afterEach(()=>{vi.unstubAllGlobals();});
describe('attachment wheel scrolling',()=>{
	function setup(rtl=false,reduced=false) {
		let time=0,id=0;
		const frames=new Map<number,FrameRequestCallback>();
		const handlers=new Map<string,Function>();
		vi.stubGlobal('requestAnimationFrame',(f:FrameRequestCallback)=>{frames.set(++id,f);return id;});
		vi.stubGlobal('cancelAnimationFrame',(id:number)=>frames.delete(id));
		vi.stubGlobal('performance',{now:()=>time});
		vi.stubGlobal('matchMedia',()=>({matches:reduced}));
		vi.stubGlobal('getComputedStyle',()=>({direction:rtl?'rtl':'ltr'}));
		const container={scrollWidth:1000,clientWidth:300,scrollLeft:0,isConnected:true,addEventListener:(name:string,f:Function)=>handlers.set(name,f),removeEventListener:(name:string)=>handlers.delete(name)};
		const action=attachmentScroller(container as unknown as HTMLElement);
		return{container,action,frames,handlers,step(){time+=16;const current=[...frames.values()];frames.clear();current.forEach(f=>f(time));},wheel(overrides={}){const value={deltaX:0,deltaY:80,deltaMode:0,ctrlKey:false,preventDefault:vi.fn(),stopPropagation:vi.fn(),...overrides};handlers.get('wheel')!(value);return value;}};
	}
	it('accumulates wheel input smoothly without passing it to the chat',()=>{
		const s=setup(),event=s.wheel();s.step();expect(s.container.scrollLeft).toBeGreaterThan(0);expect(s.container.scrollLeft).toBeLessThan(80);
		s.wheel();for(let i=0;i<30;i++)s.step();expect(s.container.scrollLeft).toBe(160);expect(s.frames.size).toBe(0);
		expect(event.preventDefault).toHaveBeenCalled();expect(event.stopPropagation).toHaveBeenCalled();
	});
	it('stops on direct interaction, external scrolling, detachment and cleanup',()=>{
		for(const operation of ['pointerdown','keydown','external','detach','destroy']){
			const s=setup();s.wheel();s.step();
			if(operation==='external')s.container.scrollLeft=200;
			else if(operation==='detach')s.container.isConnected=false;
			else if(operation==='destroy')s.action.destroy();
			else s.handlers.get(operation)!();
			const before=s.container.scrollLeft;s.step();expect(s.container.scrollLeft).toBe(before);expect(s.frames.size).toBe(0);
		}
	});
	it('preserves zoom, horizontal trackpad scrolling and no-overflow behavior',()=>{
		const s=setup();
		for(const options of [{ctrlKey:true},{deltaX:100,deltaY:1}])expect(s.wheel(options).preventDefault).not.toHaveBeenCalled();
		s.container.scrollWidth=300;expect(s.wheel().preventDefault).not.toHaveBeenCalled();expect(s.frames.size).toBe(0);
	});
	it('finishes even when the browser rounds scroll offsets to integer pixels',()=>{
		const s=setup();let offset=0;
		Object.defineProperty(s.container,'scrollLeft',{get:()=>offset,set:value=>{offset=Math.round(value);}});
		s.wheel({deltaY:120});for(let i=0;i<30;i++)s.step();
		expect(offset).toBe(120);expect(s.frames.size).toBe(0);
	});
	it('supports RTL, clamping, direction reversal and reduced motion',()=>{
		const s=setup(true);s.wheel({deltaY:-100,deltaMode:1});for(let i=0;i<30;i++)s.step();expect(s.container.scrollLeft).toBe(-700);
		s.wheel({deltaY:100});s.step();const before=s.container.scrollLeft;s.wheel({deltaY:-50});s.step();expect(s.container.scrollLeft).toBeLessThan(before);
		const reduced=setup(false,true);reduced.wheel();expect(reduced.container.scrollLeft).toBe(80);expect(reduced.frames.size).toBe(0);
	});
});
