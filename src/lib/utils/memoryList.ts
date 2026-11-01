import { getMemories } from '$lib/apis/memories';

export type SavedMemory = { id: string; content: string; updated_at: number; [key: string]: any };

export function createMemoryListCache(fetchList = getMemories) {
	let owner = '';
	let records: SavedMemory[] | null = null;
	let revision = 0;
	let pending: Promise<SavedMemory[]> | null = null;
	const read = (userId: string) => owner === userId && records !== null ? [...records] : null;

	const load = async (userId: string, token: string, refresh = false): Promise<SavedMemory[]> => {
		if (owner !== userId) {
			owner = userId;
			records = null;
			pending = null;
			revision += 1;
		}
		if (!refresh && records !== null) return [...records];
		if (pending) return pending;
		const startedRevision = revision;
		const request = (async () => {
			const result = await fetchList(token);
			if (!Array.isArray(result)) throw new Error('Failed to load memories');
			if (owner !== userId) return [];
			// A response started before a confirmed mutation must not undo that mutation.
			if (revision === startedRevision) records = result;
			return [...(records ?? [])];
		})();
		pending = request;
		try { return await request; }
		finally { if (pending === request) pending = null; }
	};
	const save = (userId: string, memory: SavedMemory) => {
		if (owner !== userId) return [];
		revision += 1;
		const list = records ?? [];
		records = list.some(item => item.id === memory.id)
			? list.map(item => item.id === memory.id ? memory : item)
			: [...list, memory];
		return [...records];
	};
	const remove = (userId: string, id?: string) => {
		if (owner !== userId) return [];
		revision += 1;
		records = id ? (records ?? []).filter(item => item.id !== id) : [];
		return [...records];
	};
	return { read, load, save, remove };
}

// Only the current account's list is held in memory, never in localStorage.
export const memoryListCache = createMemoryListCache();
