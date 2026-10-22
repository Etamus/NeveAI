import {describe,expect,it} from 'vitest';
import {ImageMaskHistory} from './imageMaskHistory';

describe('image mask undo history',()=>{
	it('undoes and redoes brush, eraser, selection and clear snapshots',()=>{
		const history=new ImageMaskHistory();history.reset('empty');
		for(const state of ['paint','erase','selected','cleared'])history.commit(state);
		for(const state of ['selected','erase','paint','empty'])expect(history.step(-1)).toBe(state);
		expect(history.canUndo).toBe(false);expect(history.step(-1)).toBeNull();
		for(const state of ['paint','erase','selected','cleared'])expect(history.step(1)).toBe(state);
		expect(history.canRedo).toBe(false);
	});
	it('discards redo on new edits and bounds retained snapshots',()=>{
		const history=new ImageMaskHistory(3);history.reset('empty');history.commit('a');history.commit('b');history.step(-1);history.commit('c');
		expect(history.canRedo).toBe(false);history.commit('d');expect(history.step(-1)).toBe('c');expect(history.step(-1)).toBe('a');expect(history.step(-1)).toBeNull();
	});
	it('does not add duplicate states and resets between images',()=>{
		const history=new ImageMaskHistory();history.reset('empty');history.commit('empty');expect(history.canUndo).toBe(false);
		history.commit('paint');history.reset('other');expect(history.canUndo).toBe(false);expect(history.canRedo).toBe(false);
	});
});
