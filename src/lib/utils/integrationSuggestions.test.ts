import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { get } from 'svelte/store';
import { getIntegrationSuggestions, integrationSuggestionUsage, loadIntegrationSuggestionUsage, recordIntegrationUse } from './integrationSuggestions';

let storage: Map<string, string>;
beforeEach(() => {
	storage = new Map();
	integrationSuggestionUsage.set({});
	vi.stubGlobal('localStorage', {
		getItem: vi.fn((key: string) => storage.get(key) ?? null),
		setItem: vi.fn((key: string, value: string) => { storage.set(key, value); })
	});
});
afterEach(() => { vi.unstubAllGlobals(); });

describe('recently used integration suggestions', () => {
	it('keeps the three original defaults for a new user', () => {
		expect(getIntegrationSuggestions(undefined)).toEqual(['stable_diffusion', 'guided_learning', 'web_search']);
	});
	it('promotes the latest integration and shifts the previous suggestions', () => {
		recordIntegrationUse('one', { video_generation: true });
		expect(getIntegrationSuggestions(get(integrationSuggestionUsage).one)).toEqual(['video_generation', 'stable_diffusion', 'guided_learning']);
		recordIntegrationUse('one', { music_generation: true });
		expect(getIntegrationSuggestions(get(integrationSuggestionUsage).one)).toEqual(['music_generation', 'video_generation', 'stable_diffusion']);
		recordIntegrationUse('one', { video_generation: true });
		expect(getIntegrationSuggestions(get(integrationSuggestionUsage).one)).toEqual(['video_generation', 'music_generation', 'stable_diffusion']);
	});
	it('never includes deep research or tools, including research with web enabled', () => {
		for (const features of [{ deep_search: true, web_search: true }, { file_generation: true }, {}]) recordIntegrationUse('one', features);
		expect(get(integrationSuggestionUsage)).toEqual({});
		expect(getIntegrationSuggestions(['deep_search', 'file_generation', 'unknown', 'web_search'])).toEqual(['web_search', 'stable_diffusion', 'guided_learning']);
	});
	it('persists order across reloads without mixing users', () => {
		recordIntegrationUse('one', { music_generation: true });
		recordIntegrationUse('two', { web_search: true });
		integrationSuggestionUsage.set({});
		loadIntegrationSuggestionUsage('one');loadIntegrationSuggestionUsage('two');
		expect(getIntegrationSuggestions(get(integrationSuggestionUsage).one)[0]).toBe('music_generation');
		expect(getIntegrationSuggestions(get(integrationSuggestionUsage).two)[0]).toBe('web_search');
	});
	it('does not write again for repeated use of the first integration', () => {
		recordIntegrationUse('one', { guided_learning: true });
		recordIntegrationUse('one', { guided_learning: true });
		expect(localStorage.setItem).toHaveBeenCalledTimes(1);
	});
	it('handles corrupt or blocked storage without breaking chat', () => {
		storage.set('neveai.integration-suggestions.v1:one', '{broken');loadIntegrationSuggestionUsage('one');
		expect(getIntegrationSuggestions(get(integrationSuggestionUsage).one)[0]).toBe('stable_diffusion');
		vi.stubGlobal('localStorage', { getItem() { throw Error('blocked'); }, setItem() { throw Error('blocked'); } });
		expect(() => recordIntegrationUse('two', { video_generation: true })).not.toThrow();
		expect(getIntegrationSuggestions(get(integrationSuggestionUsage).two)[0]).toBe('video_generation');
	});
	it('deduplicates cached history and respects available integrations', () => {
		expect(getIntegrationSuggestions(['video_generation', 'video_generation', 'web_search'], ['guided_learning', 'web_search', 'music_generation'])).toEqual(['web_search', 'guided_learning', 'music_generation']);
	});
	it('keeps history bounded to five entries and ignores missing users', () => {
		for (const id of ['video_generation', 'music_generation', 'stable_diffusion', 'guided_learning', 'web_search']) recordIntegrationUse('one', { [id]: true });
		expect(get(integrationSuggestionUsage).one).toHaveLength(5);
		recordIntegrationUse(undefined, { video_generation: true });
		expect(Object.keys(get(integrationSuggestionUsage))).toEqual(['one']);
	});
	it('suggests 3D after a request without changing the three defaults', () => {
		recordIntegrationUse('one', { model3d_generation: true });
		const recent = get(integrationSuggestionUsage).one;
		expect(getIntegrationSuggestions(recent)).toEqual(['model3d_generation', 'stable_diffusion', 'guided_learning']);
		expect(getIntegrationSuggestions(recent, ['stable_diffusion', 'guided_learning', 'web_search'])).toEqual(['stable_diffusion', 'guided_learning', 'web_search']);
	});
});
