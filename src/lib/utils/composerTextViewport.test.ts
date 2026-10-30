import { describe, expect, it } from 'vitest';
import type { EditorView } from 'prosemirror-view';
import { scrollComposerSelectionToEnd } from './composerTextViewport';

const fixture = () => {
	const viewport = {scrollTop:42,scrollHeight:1000,clientHeight:200,scrollWidth:200,clientWidth:200};
	const state = {selection:{empty:true,to:99},doc:{content:{size:100},lastChild:{isTextblock:true}}};
	const dom = {closest:()=>viewport};
	return {viewport,state,view:{state,dom} as unknown as EditorView};
};
describe('composer end selection scrolling', () => {
	it('handles the caret at the document end synchronously', () => {
		const {view,viewport}=fixture();expect(scrollComposerSelectionToEnd(view)).toBe(true);expect(viewport.scrollTop).toBe(1000);
	});
	it.each(['selection','middle','horizontal','short','atom'])('leaves native scrolling intact for %s', kind => {
		const {view,viewport,state}=fixture();
		if(kind==='selection')state.selection.empty=false;
		if(kind==='middle')state.selection.to=50;
		if(kind==='horizontal')viewport.scrollWidth=300;
		if(kind==='short')viewport.scrollHeight=100;
		if(kind==='atom')state.doc.lastChild.isTextblock=false;
		expect(scrollComposerSelectionToEnd(view)).toBe(false);expect(viewport.scrollTop).toBe(42);
	});
	it('does not affect a rich text editor outside the composer', () => {
		const {view}=fixture();
		const elsewhere={state:view.state,dom:{closest:()=>null}} as unknown as EditorView;
		expect(scrollComposerSelectionToEnd(elsewhere)).toBe(false);
	});
});
