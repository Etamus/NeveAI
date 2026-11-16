import { afterEach, describe, expect, it, vi } from 'vitest';
import { normalizeSidebarChatSort, getSidebarChatSort, saveSidebarChatSort, sortSidebarChats } from './sidebarChatSort';

afterEach(() => { vi.unstubAllGlobals(); });
describe('sidebar conversation ordering', () => {
	it('sorts only a copy for names, folds accents and casing, and keeps deterministic ties', () => {
		const items = [{id:'4',title:'Zebra'}, {id:'2',title:'Ágata'}, {id:'1',title:'agata'}, {id:'3',title:'Beta'}];
		const before = structuredClone(items);
		expect(sortSidebarChats(items,'name').map(row=>row.id)).toEqual(['1','2','3','4']);
		expect(items).toEqual(before);
		expect(sortSidebarChats(items,'recent')).toBe(items);
	});
	it('defaults to recent and persists selection without changing other preferences', () => {
		const store = new Map([['other','keep']]);
		vi.stubGlobal('localStorage',{getItem:(key:string)=>store.get(key),setItem:(key:string,value:string)=>store.set(key,value)});
		expect(getSidebarChatSort()).toBe('recent');
		saveSidebarChatSort('name');expect(getSidebarChatSort()).toBe('name');
		expect(store.get('other')).toBe('keep');
		for(const value of [null,undefined,'bad'])expect(normalizeSidebarChatSort(value)).toBe('recent');
	});
	it('works for the session if storage is unavailable', () => {
		vi.stubGlobal('localStorage',{getItem(){throw Error('unavailable');},setItem(){throw Error('unavailable');}});
		saveSidebarChatSort('name');expect(getSidebarChatSort()).toBe('name');
		saveSidebarChatSort('recent');expect(getSidebarChatSort()).toBe('recent');
	});
});
