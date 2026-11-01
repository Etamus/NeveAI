import { get, writable } from 'svelte/store';
import { NEVEAI_BASE_URL } from '$lib/constants';
import type { LocalModel } from '$lib/apis/llamacpp';

export type ModelAvailability = {
	known: boolean;
	epoch: string;
	revision: number;
	busy: boolean;
	loaded_models: LocalModel[];
	receivedAt: number;
};

export const modelAvailability = writable<ModelAvailability>({
	known: false, epoch: '', revision: -1, busy: false, loaded_models: [], receivedAt: 0
});

let observation = 0;

export function applyModelAvailability(value: any, observedAt = Date.now()): boolean {
	if (!value || typeof value.epoch !== 'string' || !Number.isInteger(value.revision) ||
		typeof value.busy !== 'boolean' || !Array.isArray(value.loaded_models)) return false;
	const current = get(modelAvailability);
	if (current.epoch === value.epoch && value.revision < current.revision) return false;
	if (current.known && current.epoch === value.epoch && current.revision === value.revision &&
		current.busy === value.busy && JSON.stringify(current.loaded_models) === JSON.stringify(value.loaded_models)) return false;
	observation++;
	modelAvailability.set({ ...value, known: true, receivedAt: observedAt });
	return true;
}

export function invalidateModelAvailability(): void {
	observation++;
	modelAvailability.update(state => ({ ...state, known: false }));
}

export async function refreshModelAvailability(): Promise<void> {
	const before = observation;
	const startedAt = Date.now();
	try {
		const response = await fetch(`${NEVEAI_BASE_URL}/llamacpp/media-state`, {
			cache: 'no-store', headers: { Accept: 'application/json' }
		});
		if (!response.ok) return;
		const state = await response.json();
		// A socket event after the request started is more recent than its response.
		if (before === observation) applyModelAvailability(state, startedAt);
	} catch {
		// Preserve the last confirmed state during transient network errors.
	}
}

export function projectAvailableModels(
	models: LocalModel[], state: ModelAvailability, catalogUpdatedAt: number, manualUpdatedAt = 0
): LocalModel[] {
	if (!state.known || state.busy) return models.map(model => ({ ...model, is_loaded: false }));
	if (state.receivedAt < manualUpdatedAt ||
		(state.revision === 0 && state.receivedAt < catalogUpdatedAt)) return models;
	return models.map(model => {
		const loaded = state.loaded_models.find(item => item.id === model.id || item.filename === model.filename);
		return loaded ? { ...model, ...loaded, is_loaded: true } : { ...model, is_loaded: false };
	});
}
