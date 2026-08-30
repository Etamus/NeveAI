const FILE_GENERATION_PREFERENCE_KEY = 'neveai.file-generation-enabled';

export const getFileGenerationPreference = (fallback = false) => {
	if (typeof localStorage === 'undefined') return fallback;
	const storedValue = localStorage.getItem(FILE_GENERATION_PREFERENCE_KEY);
	return storedValue === null ? fallback : storedValue === 'true';
};

export const setFileGenerationPreference = (enabled: boolean) => {
	if (typeof localStorage === 'undefined') return;
	localStorage.setItem(FILE_GENERATION_PREFERENCE_KEY, `${enabled}`);
};
