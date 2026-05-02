export type LocalModelContextPreference = 'ask' | number;
export type LocalModelVisionPreference = 'ask' | 'yes' | 'no';

export const LOCAL_MODEL_CONTEXT_OPTIONS = [2048, 4096, 8192, 16384, 32768, 65536];

const CONTEXT_KEY = 'llamacpp_load_context';
const VISION_KEY = 'llamacpp_load_vision';

const hasStorage = () => typeof window !== 'undefined' && typeof localStorage !== 'undefined';

const parseContextPreference = (value: string | null): LocalModelContextPreference => {
	if (!value || value === 'ask') return 'ask';

	const parsed = Number(value);
	return LOCAL_MODEL_CONTEXT_OPTIONS.includes(parsed) ? parsed : 'ask';
};

const parseVisionPreference = (value: string | null): LocalModelVisionPreference => {
	return value === 'yes' || value === 'no' ? value : 'ask';
};

export const getLocalModelLoadPreferences = () => {
	if (!hasStorage()) {
		return {
			context: 'ask' as LocalModelContextPreference,
			vision: 'ask' as LocalModelVisionPreference
		};
	}

	return {
		context: parseContextPreference(localStorage.getItem(CONTEXT_KEY)),
		vision: parseVisionPreference(localStorage.getItem(VISION_KEY))
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

export const getContextPreferenceLabel = (preference: LocalModelContextPreference) => {
	return preference === 'ask' ? 'Perguntar' : preference.toLocaleString('pt-BR');
};

export const getVisionPreferenceLabel = (preference: LocalModelVisionPreference) => {
	if (preference === 'yes') return 'Sim';
	if (preference === 'no') return 'Não';
	return 'Perguntar';
};