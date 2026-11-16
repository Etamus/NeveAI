import { afterEach, describe, expect, it, vi } from 'vitest';
vi.mock('$lib/constants',()=>({NEVEAI_API_BASE_URL:'http://neve.test/api/v1'}));
vi.mock('$lib/utils',()=>({getTimeRange:()=> 'today'}));
import { getChatList } from './index';
import { saveSidebarChatSort } from '$lib/utils/sidebarChatSort';
afterEach(()=>{ vi.unstubAllGlobals(); });
const storage = () => {
	let value = 'recent';
	vi.stubGlobal('localStorage',{getItem:()=>value,setItem:(_key:string,next:string)=>{value=next;}});
};
describe('sidebar list API ordering',()=>{
	it('orders each page on the server and does not change pinned/folder requests',async()=>{
		storage();saveSidebarChatSort('name');
		const fetch=vi.fn().mockImplementation(async()=>new Response('[]'));vi.stubGlobal('fetch',fetch);
		await getChatList('token',2);
		expect(new URL(fetch.mock.calls[0][0]).searchParams.get('sort')).toBe('name');
		expect(new URL(fetch.mock.calls[0][0]).searchParams.get('page')).toBe('2');
		await getChatList('token',1,true,true);
		expect(new URL(fetch.mock.calls[1][0]).searchParams.has('sort')).toBe(false);
	});
	it('retries stale responses in the new order instead of exposing the previous choice',async()=>{
		storage();let resolve!:(value:Response)=>void;
		const fetch=vi.fn().mockImplementationOnce(()=>new Promise(r=>{resolve=r;})).mockResolvedValueOnce(new Response(JSON.stringify([{id:'new',title:'Alpha',updated_at:1}])));
		vi.stubGlobal('fetch',fetch);
		const pending=getChatList('token',1);
		saveSidebarChatSort('name');resolve(new Response(JSON.stringify([{id:'stale',title:'Zulu',updated_at:1}])));
		expect((await pending)[0].id).toBe('new');expect(fetch).toHaveBeenCalledTimes(2);
	});
});
