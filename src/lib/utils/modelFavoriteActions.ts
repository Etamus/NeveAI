import { get } from 'svelte/store';
import { settings } from '$lib/stores';
import { updateUserSettings } from '$lib/apis/users';
import { normalizeModelFavorites } from './modelFavorites';

let saving: Promise<unknown> = Promise.resolve();

export function saveModelFavorites() {
	// Serialize writes so rapid toggles cannot persist an older favorites list last.
	saving = saving.catch(() => {}).then(async () => {
		const result = await updateUserSettings(localStorage.token, { ui: get(settings) });
		if (!result) throw new Error('Favorites could not be saved');
		return result;
	});
	return saving;
}

export function toggleModelFavorite(modelId: string) {
	const ui = normalizeModelFavorites(get(settings));
	const favoriteModels = ui.favoriteModels.includes(modelId)
		? ui.favoriteModels.filter((id) => id !== modelId)
		: [...ui.favoriteModels, modelId];
	settings.set({ ...ui, favoriteModels });
	return saveModelFavorites();
}
