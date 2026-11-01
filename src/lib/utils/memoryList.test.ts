import { describe, expect, it, vi } from 'vitest';
import { createMemoryListCache } from './memoryList';

const note = (id = 'one', content = 'Meu nome e Marina') => ({id, content, updated_at: 1});

describe('Memory list without visual reloads', () => {
	it('preloads once and exposes the list synchronously for a ready modal', async () => {
		const fetch = vi.fn().mockResolvedValue([note()]);
		const cache = createMemoryListCache(fetch);
		expect(cache.read('user')).toBeNull();
		await cache.load('user', 'token');
		expect(cache.read('user')).toEqual([note()]);
		await cache.load('user', 'token');
		expect(fetch).toHaveBeenCalledTimes(1);
	});
	it('deduplicates a preload and a simultaneous first opening', async () => {
		let resolve!: (value: any[]) => void;
		const fetch = vi.fn(() => new Promise<any[]>(done => {resolve = done;}));
		const cache = createMemoryListCache(fetch);
		const preload = cache.load('user', 'token');
		const open = cache.load('user', 'token');
		resolve([note()]);
		expect(await preload).toEqual([note()]);
		expect(await open).toEqual([note()]);
		expect(fetch).toHaveBeenCalledTimes(1);
	});
	it('updates and adds from saved API objects without another GET', async () => {
		const fetch = vi.fn().mockResolvedValue([note()]);
		const cache = createMemoryListCache(fetch);
		await cache.load('user', 'token');
		expect(cache.save('user', note('one', 'Moro em Salvador'))).toEqual([note('one', 'Moro em Salvador')]);
		expect(cache.save('user', note('two'))).toHaveLength(2);
		expect(fetch).toHaveBeenCalledTimes(1);
	});
	it.each(['save', 'remove', 'clear'])('a stale refresh cannot undo a confirmed %s', async action => {
		let resolve!: (value: any[]) => void;
		const fetch = vi.fn().mockResolvedValueOnce([note()]).mockImplementationOnce(() => new Promise<any[]>(done => {resolve = done;}));
		const cache = createMemoryListCache(fetch);
		await cache.load('user', 'token');
		const refresh = cache.load('user', 'token', true);
		const expected = action === 'save' ? cache.save('user', note('one', 'Updated')) : cache.remove('user', action === 'remove' ? 'one' : undefined);
		resolve([note()]);
		expect(await refresh).toEqual(expected);
		expect(cache.read('user')).toEqual(expected);
	});
	it('keeps the current list readable during a refresh and accepts external changes', async () => {
		let resolve!: (value: any[]) => void;
		const cache = createMemoryListCache(vi.fn().mockResolvedValueOnce([note()]).mockImplementationOnce(() => new Promise<any[]>(done => {resolve = done;})));
		await cache.load('user', 'token');
		const refresh = cache.load('user', 'token', true);
		expect(cache.read('user')).toEqual([note()]);
		resolve([note('two')]);
		await refresh;
		expect(cache.read('user')).toEqual([note('two')]);
	});
	it('does not share notes across users or let an old user request overwrite the new user', async () => {
		let resolve!: (value: any[]) => void;
		const cache = createMemoryListCache(vi.fn().mockImplementationOnce(() => new Promise<any[]>(done => {resolve = done;})).mockResolvedValueOnce([note('other')]).mockResolvedValueOnce([note()]));
		const old = cache.load('first', 'one');
		await cache.load('second', 'two');
		expect(cache.read('first')).toBeNull();
		resolve([note()]);
		await old;
		expect(cache.read('second')).toEqual([note('other')]);
		await cache.load('first', 'one');
		expect(cache.read('second')).toBeNull();
	});
	it('distinguishes a failed cold load from an empty list and can retry', async () => {
		const cache = createMemoryListCache(vi.fn().mockResolvedValueOnce(null).mockResolvedValueOnce([]));
		await expect(cache.load('user', 'token')).rejects.toThrow('Failed to load memories');
		expect(cache.read('user')).toBeNull();
		await cache.load('user', 'token');
		expect(cache.read('user')).toEqual([]);
	});
});
