import { describe, expect, it } from 'vitest';
import { isNeveModel, normalizeModelFavorites } from './modelFavorites';

describe('Model favorites', () => {
	it('migrates pins without losing other preferences', () => {
		const source = { pinnedModels: ['a', 'a', '', null, 'b'], theme: 'dark' };
		expect(normalizeModelFavorites(source)).toEqual({ favoriteModels: ['a', 'b'], theme: 'dark' });
		expect(source.pinnedModels).toHaveLength(5);
	});
	it('does not restore removed favorites on subsequent migrations', () => {
		expect(normalizeModelFavorites({ favoriteModels: [], pinnedModels: ['a'] })).toEqual({ favoriteModels: [] });
		expect(normalizeModelFavorites({ favoriteModels: ['b', 'b'], other: true })).toEqual({ favoriteModels: ['b'], other: true });
	});
	it('recognizes catalog identities even after renaming', () => {
		expect(isNeveModel({ name: 'Custom name', info: { meta: { neve_catalog_id: 'echo', managed_by: 'neve_download' } } })).toBe(true);
		expect(isNeveModel({ id: 'local/Neve-Echo-Q4.gguf' })).toBe(false);
		expect(isNeveModel({ name: 'Neve Sense' })).toBe(false);
		expect(isNeveModel({ name: 'Snow Qwen', id: 'local/qwen.gguf' })).toBe(false);
		expect(isNeveModel({ name: 'Nevele' })).toBe(false);
	});
	it('requires downloader provenance and a nonempty catalog identity', () => {
		expect(isNeveModel({ meta: { managed_by: 'neve_download', neve_catalog_id: 'echo' } })).toBe(true);
		expect(isNeveModel({ meta: { neve_catalog_id: 'echo' } })).toBe(false);
		expect(isNeveModel({ meta: { managed_by: 'neve_download', neve_catalog_id: ' ' } })).toBe(false);
		expect(isNeveModel({ info: { meta: {} }, meta: { managed_by: 'neve_download', neve_catalog_id: 'echo' } })).toBe(false);
	});
});
