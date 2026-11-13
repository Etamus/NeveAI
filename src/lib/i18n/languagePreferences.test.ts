import { afterEach, describe, expect, it, vi } from 'vitest';
import {
	getLanguagePreference,
	normalizeLanguagePreference,
	resolveLanguage,
	resolveSystemLanguage
} from './languagePreferences';

afterEach(() => { vi.unstubAllGlobals(); });

describe('automatic interface language', () => {
	it.each(['pt', 'pt-BR', 'pt-PT', 'PT-pt', 'pt_AO', 'pt-MZ'])(
		'uses Brazilian Portuguese for %s',
		(language) => {
			expect(resolveSystemLanguage(language)).toBe('pt-BR');
			expect(resolveLanguage('auto', language)).toBe('pt-BR');
		}
	);
	it.each(['en-US', 'en-GB', 'fr-FR', 'es-ES', 'de-DE', 'ja-JP', '', null, undefined])(
		'uses English for %s',
		(language) => {
			expect(resolveLanguage('auto', language)).toBe('en-US');
		}
	);
	it('defaults to automatic without saving a forced locale', () => {
		const getItem = vi.fn().mockReturnValue(null),
			setItem = vi.fn();
		vi.stubGlobal('localStorage', { getItem, setItem });
		expect(getLanguagePreference()).toBe('auto');
		expect(setItem).not.toHaveBeenCalled();
	});
	it.each(['auto', 'es-ES', 'invalid', null])('normalizes %s to automatic', (value) =>
		expect(normalizeLanguagePreference(value)).toBe('auto')
	);
	it('preserves manual selections independently of the computer language', () => {
		expect(resolveLanguage('pt-BR', 'en-US')).toBe('pt-BR');
		expect(resolveLanguage('en-US', 'pt-PT')).toBe('en-US');
		for (const saved of ['pt-BR', 'en-US']) {
			vi.stubGlobal('localStorage', { getItem: () => saved });
			expect(getLanguagePreference()).toBe(saved);
		}
	});
});
