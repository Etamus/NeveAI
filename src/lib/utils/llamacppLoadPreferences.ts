export type LocalModelContextPreference = 'ask' | number;
export type LocalModelVisionPreference = 'ask' | 'yes' | 'no';
export type LocalModelCachePreference = 'default' | 'q8_0' | 'q4_0' | 'f16';

export const LOCAL_MODEL_CONTEXT_OPTIONS = [2048, 4096, 8192, 16384, 32768, 65536];

const CONTEXT_KEY = 'llamacpp_load_context';
const VISION_KEY = 'llamacpp_load_vision';
const CACHE_KEY = 'llamacpp_cache_type';

const hasStorage = () => typeof window !== 'undefined' && typeof localStorage !== 'undefined';

const parseContextPreference = (value: string | null): LocalModelContextPreference => {
	if (!value || value === 'ask') return 'ask';

	const parsed = Number(value);
	return LOCAL_MODEL_CONTEXT_OPTIONS.includes(parsed) ? parsed : 'ask';
};

const parseVisionPreference = (value: string | null): LocalModelVisionPreference => {
	return value === 'yes' || value === 'no' ? value : 'ask';
};

const parseCachePreference = (value: string | null): LocalModelCachePreference => {
	return value === 'q8_0' || value === 'q4_0' || value === 'f16' ? value : 'default';
};

export const getLocalModelLoadPreferences = () => {
	if (!hasStorage()) {
		return {
			context: 'ask' as LocalModelContextPreference,
			vision: 'ask' as LocalModelVisionPreference,
			cache: 'default' as LocalModelCachePreference
		};
	}

	return {
		context: parseContextPreference(localStorage.getItem(CONTEXT_KEY)),
		vision: parseVisionPreference(localStorage.getItem(VISION_KEY)),
		cache: parseCachePreference(localStorage.getItem(CACHE_KEY))
	};
};

export const setLocalModelContextPreference = (preference: LocalModelContextPreference) => {
	if (!hasStorage()) return;
	localStorage.setItem(CONTEXT_KEY, String(preference));
};

export const setLocalModelVisionPreference = (preference: LocalModelVisionPreference) => {
	if (!hasStorage()) return;
	localStorage.setItem(VISION_KEY, preference);
};

export const setLocalModelCachePreference = (preference: LocalModelCachePreference) => {
	if (!hasStorage()) return;
	if (preference === 'default') {
		localStorage.removeItem(CACHE_KEY);
		return;
	}

	localStorage.setItem(CACHE_KEY, preference);
};

export const getContextPreferenceLabel = (preference: LocalModelContextPreference) => {
	return preference === 'ask' ? 'Perguntar' : preference.toLocaleString('pt-BR');
};

export const getVisionPreferenceLabel = (preference: LocalModelVisionPreference) => {
	if (preference === 'yes') return 'Sim';
	if (preference === 'no') return 'Não';
	return 'Perguntar';
};

export const getCachePreferenceLabel = (preference: LocalModelCachePreference) => {
	if (preference === 'q8_0') return 'Q8_0';
	if (preference === 'q4_0') return 'Q4_0';
	if (preference === 'f16') return 'FP16';
	return 'Padrão';
};
