export type SidebarChatSort = 'recent' | 'name';
const key = 'neveai.sidebarChatSort';
let fallback: SidebarChatSort = 'recent';

export const normalizeSidebarChatSort = (value: unknown): SidebarChatSort => value === 'name' ? 'name' : 'recent';

export function getSidebarChatSort(): SidebarChatSort {
	try { return normalizeSidebarChatSort(localStorage.getItem(key)); } catch { return fallback; }
}

export function saveSidebarChatSort(value: SidebarChatSort) {
	fallback = normalizeSidebarChatSort(value);
	try { localStorage.setItem(key, fallback); } catch { /* Keep the preference for this session. */ }
}

const nameKey = (value: string) => value.normalize('NFKD').replace(/\p{M}/gu, '').toLowerCase();
export function sortSidebarChats<T extends { title?: string; id?: string; created_at?: number }>(items: T[], order: SidebarChatSort): T[] {
	if (order !== 'name') return items;
	const keys = new Map(items.map(item => [item, nameKey(item.title ?? '')]));
	return [...items].sort((a, b) => {
		const left = keys.get(a)!, right = keys.get(b)!;
		if (left !== right) return left < right ? -1 : 1;
		return (a.id ?? '') < (b.id ?? '') ? -1 : (a.id ?? '') > (b.id ?? '') ? 1 : 0;
	});
}
