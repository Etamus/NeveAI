export type SupportedLanguage = 'pt-BR' | 'en-US';
export type LanguagePreference = 'auto' | SupportedLanguage;

export function normalizeLanguagePreference(value: string | null | undefined): LanguagePreference {
	return value === 'pt-BR' || value === 'en-US' ? value : 'auto';
}

export function resolveSystemLanguage(language?: string | null): SupportedLanguage {
	return /^pt(?:[-_]|$)/i.test(language ?? '') ? 'pt-BR' : 'en-US';
}

export function getLanguagePreference(): LanguagePreference {
	return normalizeLanguagePreference(
		typeof localStorage === 'undefined' ? null : localStorage.getItem('neveai.language')
	);
}

export function resolveLanguage(
	preference: LanguagePreference,
	systemLanguage?: string | null
): SupportedLanguage {
	return preference === 'auto' ? resolveSystemLanguage(systemLanguage) : preference;
}
