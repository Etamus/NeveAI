import { beforeEach, describe, expect, it, vi } from 'vitest';
import { get } from 'svelte/store';

const update = vi.hoisted(() => vi.fn());
vi.mock('$lib/apis/users', () => ({ updateUserSettings: update }));
vi.mock('$lib/stores', async () => {
	const { writable } = await import('svelte/store');
	return { settings: writable({}) };
});
import { settings } from '$lib/stores';
import { toggleModelFavorite } from './modelFavoriteActions';

describe('Shared favorites persistence', () => {
	beforeEach(() => {
		vi.stubGlobal('localStorage', { token: 'test' });
		update.mockReset();
		settings.set({ theme: 'dark', favoriteModels: [] });
	});
	it('serializes rapid changes and persists the latest list without losing unrelated settings', async () => {
		let release!: () => void;
		const firstSave = new Promise<void>((resolve) => { release = resolve; });
		update.mockImplementationOnce(async () => { await firstSave; return {}; });
		update.mockResolvedValue({});
		const first = toggleModelFavorite('a');
		await vi.waitFor(() => expect(update).toHaveBeenCalledTimes(1));
		const second = toggleModelFavorite('b');
		const third = toggleModelFavorite('a');
		expect(get(settings)).toEqual({ theme: 'dark', favoriteModels: ['b'] });
		expect(update).toHaveBeenCalledTimes(1);
		release();
		await Promise.all([first, second, third]);
		expect(update).toHaveBeenCalledTimes(3);
		expect(update.mock.lastCall).toEqual(['test', { ui: { theme: 'dark', favoriteModels: ['b'] } }]);
	});
	it('reports a failed save and allows the next toggle to save normally', async () => {
		update.mockResolvedValueOnce(null).mockResolvedValue({});
		await expect(toggleModelFavorite('a')).rejects.toThrow('could not be saved');
		await toggleModelFavorite('b');
		expect(update.mock.lastCall?.[1].ui.favoriteModels).toEqual(['a', 'b']);
	});
});
