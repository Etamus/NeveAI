export type LocalModelContextPreference = 'auto' | number;
export type LocalModelVisionPreference = 'yes' | 'no';
export type LocalModelCachePreference = 'default' | 'f16' | 'q8_0' | 'q4_0';
export type LocalModelSpeculativePreference = 'default' | 'high' | 'off';
export type LocalModelAccelerationMode = 'normal' | 'de' | 'mtp';
export type LocalModelTokenPredictionPreference = 'default' | 'on' | 'off';
export type LocalModelContextShiftPreference = 'default' | 'on' | 'off';

export const LOCAL_MODEL_CONTEXT_OPTIONS = [2048, 4096, 8192, 16384, 32768, 65536, 131072, 262144];

const CONTEXT_KEY = 'llamacpp_load_context';
const VISION_KEY = 'llamacpp_load_vision';
const CACHE_KEY = 'llamacpp_cache_type';
const SPECULATIVE_KEY = 'llamacpp_speculative_decoding';
const RESPONSE_SPEED_KEY = 'neveai.responseSpeed';
export const RESPONSE_SPEED_CHANGED = 'neve:response-speed-changed';

export function getResponseSpeed(): 'normal' | 'fast' {
	return hasStorage() &&
		localStorage.getItem(CONTEXT_SHIFT_KEY) !== 'on' &&
		localStorage.getItem(RESPONSE_SPEED_KEY) === 'fast'
		? 'fast'
		: 'normal';
}

export function setResponseSpeed(speed: 'normal' | 'fast') {
	if (!hasStorage()) return;
	if (localStorage.getItem(CONTEXT_SHIFT_KEY) === 'on') return;
	localStorage.setItem(RESPONSE_SPEED_KEY, speed);
	if (speed === 'fast') localStorage.setItem(SPECULATIVE_KEY, 'off');
	window.dispatchEvent(new Event(RESPONSE_SPEED_CHANGED));
}

export function setLocalModelTokenPredictionPreference(
	preference: LocalModelTokenPredictionPreference
) {
	if (!hasStorage()) return;
	if (preference !== 'default' || localStorage.getItem(CONTEXT_SHIFT_KEY) === 'on') {
		setResponseSpeed(preference === 'on' ? 'fast' : 'normal');
		return;
	}
	localStorage.setItem(RESPONSE_SPEED_KEY, 'default');
	window.dispatchEvent(new Event(RESPONSE_SPEED_CHANGED));
}

const CONTEXT_SHIFT_KEY = 'llamacpp_context_shift';

const hasStorage = () => typeof window !== 'undefined' && typeof localStorage !== 'undefined';

const parseContextPreference = (value: string | null): LocalModelContextPreference => {
	if (!value || value === 'ask' || value === 'auto') return 'auto';

	const parsed = Number(value);
	return LOCAL_MODEL_CONTEXT_OPTIONS.includes(parsed) ? parsed : 'auto';
};

const parseVisionPreference = (value: string | null): LocalModelVisionPreference => {
	return value === 'no' ? 'no' : 'yes';
};

const parseCachePreference = (value: string | null): LocalModelCachePreference => {
	return value === 'q8_0' || value === 'q4_0' || value === 'f16' ? value : 'default';
};

const parseSpeculativePreference = (value: string | null): LocalModelSpeculativePreference => {
	if (value === 'low') return 'high';
	return value === 'high' || value === 'off' ? value : 'default';
};

export function getLocalModelAccelerationMode(): LocalModelAccelerationMode {
	const preferences = getLocalModelLoadPreferences();
	if (preferences.tokenPrediction === 'on') return 'mtp';
	return preferences.speculative === 'high' ? 'de' : 'normal';
}

export function setLocalModelAccelerationMode(mode: LocalModelAccelerationMode) {
	if (!hasStorage()) return;
	if (localStorage.getItem(CONTEXT_SHIFT_KEY) === 'on') return;
	// Commit both settings before notifying mounted controls and load planners.
	localStorage.setItem(RESPONSE_SPEED_KEY, mode === 'mtp' ? 'fast' : 'normal');
	localStorage.setItem(SPECULATIVE_KEY, mode === 'de' ? 'high' : 'off');
	window.dispatchEvent(new Event(RESPONSE_SPEED_CHANGED));
}

const parseContextShiftPreference = (value: string | null): LocalModelContextShiftPreference => {
	if (!value || value === 'default') return 'default';
	return value === 'on' ? 'on' : 'off';
};

export const getLocalModelLoadPreferences = () => {
	if (!hasStorage()) {
		return {
			context: 'auto' as LocalModelContextPreference,
			vision: 'yes' as LocalModelVisionPreference,
			cache: 'default' as LocalModelCachePreference,
			speculative: 'default' as LocalModelSpeculativePreference,
			tokenPrediction: 'off' as LocalModelTokenPredictionPreference,
			contextShift: 'default' as LocalModelContextShiftPreference
		};
	}

	return {
		context: parseContextPreference(localStorage.getItem(CONTEXT_KEY)),
		vision: parseVisionPreference(localStorage.getItem(VISION_KEY)),
		cache: parseCachePreference(localStorage.getItem(CACHE_KEY)),
		speculative:
			localStorage.getItem(CONTEXT_SHIFT_KEY) === 'on' || getResponseSpeed() === 'fast'
				? ('off' as LocalModelSpeculativePreference)
				: parseSpeculativePreference(localStorage.getItem(SPECULATIVE_KEY)),
		tokenPrediction:
			getResponseSpeed() === 'fast'
				? ('on' as LocalModelTokenPredictionPreference)
				: ((localStorage.getItem(CONTEXT_SHIFT_KEY) !== 'on' &&
					localStorage.getItem(RESPONSE_SPEED_KEY) === 'default'
						? 'default'
						: 'off') as LocalModelTokenPredictionPreference),
		contextShift: parseContextShiftPreference(localStorage.getItem(CONTEXT_SHIFT_KEY))
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

export const setLocalModelSpeculativePreference = (preference: LocalModelSpeculativePreference) => {
	if (!hasStorage()) return;
	if (localStorage.getItem(CONTEXT_SHIFT_KEY) === 'on') return;
	if (getResponseSpeed() === 'fast') preference = 'off';
	if (preference === 'default') {
		localStorage.removeItem(SPECULATIVE_KEY);
	} else {
		localStorage.setItem(SPECULATIVE_KEY, preference);
	}
	window.dispatchEvent(new Event(RESPONSE_SPEED_CHANGED));
};

export const setLocalModelContextShiftPreference = (
	preference: LocalModelContextShiftPreference
) => {
	if (!hasStorage()) return;
	if (preference === 'default') {
		localStorage.removeItem(CONTEXT_SHIFT_KEY);
	} else {
		localStorage.setItem(CONTEXT_SHIFT_KEY, preference);
	}
	// Readers mask acceleration while shifting context; retain the user's saved mode.
	window.dispatchEvent(new Event(RESPONSE_SPEED_CHANGED));
};

export const getVisionPreferenceLabel = (preference: LocalModelVisionPreference) => {
	return preference === 'no' ? 'Não' : 'Sim';
};

export const getCachePreferenceLabel = (preference: LocalModelCachePreference) => {
	if (preference === 'q8_0') return 'Q8_0';
	if (preference === 'q4_0') return 'Q4_0';
	if (preference === 'f16') return 'FP16';
	return 'Padrão';
};

export const getSpeculativePreferenceLabel = (preference: LocalModelSpeculativePreference) => {
	if (preference === 'high') return 'Alto';
	if (preference === 'off') return 'Desligado';
	return 'Padrão';
};

export const getContextShiftPreferenceLabel = (preference: LocalModelContextShiftPreference) => {
	if (preference === 'on') return 'Ligado';
	if (preference === 'off') return 'Desligado';
	return 'Padrão';
};
