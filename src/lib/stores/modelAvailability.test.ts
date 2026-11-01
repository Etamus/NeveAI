import { beforeEach, describe, expect, it, vi } from 'vitest';
import { get } from 'svelte/store';
vi.mock('$lib/constants', () => ({ NEVEAI_BASE_URL: '' }));
import { applyModelAvailability, invalidateModelAvailability, modelAvailability, projectAvailableModels, refreshModelAvailability } from './modelAvailability';

const model: any = { id: 'local/test', filename: 'test.gguf', is_loaded: true, n_ctx: 8192 };
const state = (revision: number, busy: boolean, loaded_models: any[] = []) => ({ epoch: 'server', revision, busy, loaded_models });

beforeEach(() => {
	modelAvailability.set({ known: false, epoch: '', revision: -1, busy: false, loaded_models: [], receivedAt: 0 });
	vi.restoreAllMocks();
});

describe('model availability projection', () => {
	it('masks cached loaded state immediately while busy or unconfirmed', () => {
		expect(projectAvailableModels([model], get(modelAvailability), 0)[0].is_loaded).toBe(false);
		applyModelAvailability(state(1, true), 100);
		expect(projectAvailableModels([model], get(modelAvailability), 200)[0].is_loaded).toBe(false);
		expect(model.is_loaded).toBe(true);
	});
	it('shows restored parameters without waiting for catalog polling', () => {
		applyModelAvailability(state(2, false, [{ ...model, n_ctx: 32768 }]), 100);
		const result = projectAvailableModels([{ ...model, is_loaded: false }], get(modelAvailability), 90);
		expect(result[0]).toMatchObject({ is_loaded: true, n_ctx: 32768 });
	});
	it('does not replace a newer manual or catalog state', () => {
		applyModelAvailability(state(0, false, [model]), 100);
		const newer = [{ ...model, is_loaded: false }];
		expect(projectAvailableModels(newer, get(modelAvailability), 101)).toBe(newer);
		expect(projectAvailableModels(newer, get(modelAvailability), 0, 101)).toBe(newer);
	});
	it('keeps confirmed media restoration ahead of stale catalog payloads', () => {
		applyModelAvailability(state(2, false, [model]), 100);
		expect(projectAvailableModels([{ ...model, is_loaded: false }], get(modelAvailability), 101)[0].is_loaded).toBe(true);
	});
	it('rejects stale revisions and invalid responses', () => {
		applyModelAvailability(state(5, true));
		expect(applyModelAvailability(state(4, false, [model]))).toBe(false);
		expect(applyModelAvailability({ busy: false })).toBe(false);
		expect(get(modelAvailability).busy).toBe(true);
	});
	it('does not let duplicate events supersede a later manual operation', () => {
		applyModelAvailability(state(2, false, [model]), 100);
		expect(applyModelAvailability(state(2, false, [model]), 200)).toBe(false);
		expect(get(modelAvailability).receivedAt).toBe(100);
	});
	it('hides cached loaded state after disconnect and revalidates on reconnect', () => {
		applyModelAvailability(state(2, false, [model]), 100);
		invalidateModelAvailability();
		expect(projectAvailableModels([model], get(modelAvailability), 0)[0].is_loaded).toBe(false);
		expect(applyModelAvailability(state(2, false, [model]), 200)).toBe(true);
		expect(get(modelAvailability).known).toBe(true);
	});
	it('accepts a new backend epoch after restart', () => {
		applyModelAvailability(state(5, true));
		applyModelAvailability({ ...state(0, false, [model]), epoch: 'new-server' });
		expect(get(modelAvailability).busy).toBe(false);
	});
	it('ignores an HTTP response overtaken by a socket event', async () => {
		let finish: (value: any) => void = () => {};
		vi.stubGlobal('fetch', vi.fn(() => new Promise(resolve => { finish = resolve; })));
		const pending = refreshModelAvailability();
		applyModelAvailability(state(2, true));
		finish({ ok: true, json: async () => state(1, false, [model]) });
		await pending;
		expect(get(modelAvailability).busy).toBe(true);
		vi.unstubAllGlobals();
	});
	it('uses request start time so a late response cannot undo a manual action', async () => {
		vi.spyOn(Date, 'now').mockReturnValueOnce(100);
		vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => state(1, false, [model]) })));
		await refreshModelAvailability();
		expect(get(modelAvailability).receivedAt).toBe(100);
		expect(projectAvailableModels([{ ...model, is_loaded: false }], get(modelAvailability), 0, 101)[0].is_loaded).toBe(false);
		vi.unstubAllGlobals();
	});
});
