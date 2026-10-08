import { beforeEach, describe, expect, it, vi } from 'vitest';
import { get } from 'svelte/store';
const toggle = vi.hoisted(() => vi.fn());
vi.mock('$lib/apis/chats', () => ({ toggleChatPinnedStatusById: toggle }));
vi.mock('$lib/stores', async () => {
	const { writable } = await import('svelte/store');
	return { chats: writable([]), pinnedChats: writable([]) };
});
import { chats, pinnedChats } from '$lib/stores';
import { pendingChatPins, toggleChatPinOptimistically } from './chatPinActions';
const a = { id: 'a', title: 'A', updated_at: 2 };
const b = { id: 'b', title: 'B', updated_at: 1 };
describe('optimistic sidebar pins', () => {
	beforeEach(() => { toggle.mockReset(); chats.set([a, b]); pinnedChats.set([]); pendingChatPins.set([]); });
	it('moves immediately and blocks duplicate requests even after remounting', async () => {
		let resolve!: () => void;
		toggle.mockReturnValue(new Promise<void>(r => { resolve = r; }));
		const request = toggleChatPinOptimistically('token', a);
		expect(get(pinnedChats).map(c => c.id)).toEqual(['a']);
		expect(get(chats)?.map(c => c.id)).toEqual(['b']);
		await toggleChatPinOptimistically('token', a);
		expect(toggle).toHaveBeenCalledTimes(1);
		resolve(); await request; expect(get(pendingChatPins)).toEqual([]);
	});
	it('unpins immediately and restores chronological order', async () => {
		chats.set([b]); pinnedChats.set([{ ...a, pinned: true }]); toggle.mockResolvedValue({});
		const request = toggleChatPinOptimistically('token', a);
		expect(get(pinnedChats)).toEqual([]);
		expect(get(chats)?.map(c => c.id)).toEqual(['a', 'b']);
		await request;
	});
	it('rolls back only the failed chat without losing a concurrent pin', async () => {
		let reject!: (error: Error) => void;
		toggle.mockImplementationOnce(() => new Promise((_, r) => { reject = r; })).mockResolvedValue({});
		const first = toggleChatPinOptimistically('token', a);
		const failure = expect(first).rejects.toThrow('offline');
		await toggleChatPinOptimistically('token', b);
		reject(new Error('offline')); await failure;
		expect(get(pinnedChats).map(c => c.id)).toEqual(['b']);
		expect(get(chats)?.map(c => c.id)).toEqual(['a']);
	});
	it('restores a failed unpin and does not leak project chats into conversations', async () => {
		const project = { ...a, folder_id: 'project', pinned: true };
		pinnedChats.set([project]); chats.set([b]); toggle.mockRejectedValue(new Error('offline'));
		await expect(toggleChatPinOptimistically('token', project)).rejects.toThrow('offline');
		expect(get(pinnedChats).map(c => c.id)).toEqual(['a']);
		expect(get(chats)?.map(c => c.id)).toEqual(['b']);
	});
});
