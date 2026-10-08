import { get, writable } from 'svelte/store';
import { chats, pinnedChats } from '$lib/stores';
import { toggleChatPinnedStatusById } from '$lib/apis/chats';

export const pendingChatPins = writable<string[]>([]);

export async function toggleChatPinOptimistically(token: string, fallback: { id: string; title: string; created_at?: number | null }) {
	const id = fallback.id;
	if (get(pendingChatPins).includes(id)) return;
	const pinned = get(pinnedChats).find((chat) => chat.id === id);
	const normalIndex = (get(chats) ?? []).findIndex((chat) => chat.id === id);
	const chat = pinned ?? get(chats)?.[normalIndex] ?? fallback;
	const wasPinned = Boolean(pinned);
	const pinnedIndex = get(pinnedChats).findIndex((item) => item.id === id);
	const apply = (pin: boolean, rollback = false) => {
		pinnedChats.update((items) => {
			const remaining = items.filter((item) => item.id !== id);
			if (pin) remaining.splice(rollback && pinnedIndex >= 0 ? pinnedIndex : 0, 0, { ...chat, pinned: true });
			return remaining;
		});
		chats.update((items) => {
			const remaining = (items ?? []).filter((item) => item.id !== id);
			if (pin || chat.folder_id) return remaining;
			const restored = { ...chat, pinned: false };
			if (rollback && normalIndex >= 0) remaining.splice(normalIndex, 0, restored);
			else {
				remaining.push(restored);
				remaining.sort((a, b) => (b.updated_at ?? b.created_at ?? 0) - (a.updated_at ?? a.created_at ?? 0));
			}
			return remaining;
		});
	};
	// Shared pending state survives the item moving between the two sidebar sections.
	pendingChatPins.update((ids) => [...ids, id]);
	apply(!wasPinned);
	try {
		await toggleChatPinnedStatusById(token, id);
	} catch (error) {
		apply(wasPinned, true);
		throw error;
	} finally {
		pendingChatPins.update((ids) => ids.filter((item) => item !== id));
	}
}
