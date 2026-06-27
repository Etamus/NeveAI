export type LocalModelContextPreference = 'ask' | number;
export type LocalModelVisionPreference = 'ask' | 'yes' | 'no';
export type LocalModelCachePreference = 'default' | 'f16' | 'q8_0' | 'q4_0';
export type LocalModelStreamPreference = 'default' | 'on' | 'off';
export type LocalModelSpeculativePreference = 'default' | 'high' | 'low' | 'off';
export type LocalModelTokenPredictionPreference = 'on' | 'off';

export const LOCAL_MODEL_CONTEXT_OPTIONS = [2048, 4096, 8192, 16384, 32768, 65536, 131072];

const CONTEXT_KEY = 'llamacpp_load_context';
const VISION_KEY = 'llamacpp_load_vision';
const CACHE_KEY = 'llamacpp_cache_type';
const STREAM_KEY = 'llamacpp_stream_response';
const SPECULATIVE_KEY = 'llamacpp_speculative_decoding';
const TOKEN_PREDICTION_KEY = 'llamacpp_token_prediction';

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

const parseStreamPreference = (value: string | null): LocalModelStreamPreference => {
	return value === 'on' || value === 'off' ? value : 'default';
};

const parseSpeculativePreference = (value: string | null): LocalModelSpeculativePreference => {
	return value === 'low' || value === 'high' || value === 'off' ? value : 'default';
};

const parseTokenPredictionPreference = (
	value: string | null
): LocalModelTokenPredictionPreference => {
	return value === 'on' || value === 'stable' || value === 'aggressive' ? 'on' : 'off';
};

export const getLocalModelLoadPreferences = () => {
	if (!hasStorage()) {
		return {
			context: 'ask' as LocalModelContextPreference,
			vision: 'ask' as LocalModelVisionPreference,
			cache: 'default' as LocalModelCachePreference,
			stream: 'default' as LocalModelStreamPreference,
			speculative: 'default' as LocalModelSpeculativePreference,
			tokenPrediction: 'off' as LocalModelTokenPredictionPreference
		};
	}

	return {
		context: parseContextPreference(localStorage.getItem(CONTEXT_KEY)),
		vision: parseVisionPreference(localStorage.getItem(VISION_KEY)),
		cache: parseCachePreference(localStorage.getItem(CACHE_KEY)),
		stream: parseStreamPreference(localStorage.getItem(STREAM_KEY)),
		speculative: parseSpeculativePreference(localStorage.getItem(SPECULATIVE_KEY)),
		tokenPrediction: parseTokenPredictionPreference(localStorage.getItem(TOKEN_PREDICTION_KEY))
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

export const setLocalModelStreamPreference = (preference: LocalModelStreamPreference) => {
	if (!hasStorage()) return;
	if (preference === 'default') {
		localStorage.removeItem(STREAM_KEY);
		return;
	}

	localStorage.setItem(STREAM_KEY, preference);
};

export const setLocalModelSpeculativePreference = (preference: LocalModelSpeculativePreference) => {
	if (!hasStorage()) return;
	if (preference === 'default') {
		localStorage.removeItem(SPECULATIVE_KEY);
		return;
	}

	localStorage.setItem(SPECULATIVE_KEY, preference);
};

export const setLocalModelTokenPredictionPreference = (
	preference: LocalModelTokenPredictionPreference
) => {
	if (!hasStorage()) return;
	if (preference === 'off') {
		localStorage.removeItem(TOKEN_PREDICTION_KEY);
		return;
	}

	localStorage.setItem(TOKEN_PREDICTION_KEY, preference);
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

export const getStreamPreferenceLabel = (preference: LocalModelStreamPreference) => {
	if (preference === 'on') return 'Ligado';
	if (preference === 'off') return 'Desligado';
	return 'Padrão';
};

export const getSpeculativePreferenceLabel = (preference: LocalModelSpeculativePreference) => {
	if (preference === 'low') return 'Moderado';
	if (preference === 'high') return 'Rápido';
	if (preference === 'off') return 'Desligado';
	return 'Padrão';
};

export const getTokenPredictionPreferenceLabel = (
	preference: LocalModelTokenPredictionPreference
) => {
	if (preference === 'on') return 'Ligado';
	return 'Desligado';
};
