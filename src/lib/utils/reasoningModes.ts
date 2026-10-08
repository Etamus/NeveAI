export const REASONING_LEVELS = ['Instantâneo', 'Médio', 'Alto', 'Extra alto'] as const;
export type ReasoningLevel = 0 | 1 | 2 | 3;
export function usesReasoningEffort(model: any): boolean {
	if (!model) return false;
	const meta = model.info?.meta ?? {};
	if (meta.neve_catalog_id === 'neve-sense' || model.llamacpp?.reasoning_control === 'effort') return true;
	const identity = [model.id, model.name, model.llamacpp?.filename, meta.base_model_id].join(' ');
	return /gpt[\s._-]*oss|\bneve[\s._-]*sense(?:\d+)?\b/i.test(identity);
}
const LEVEL_KEY = 'neveai.reasoningLevel';

export function getReasoningLevel(): ReasoningLevel {
	if (typeof localStorage === 'undefined') return 2;
	const saved = localStorage.getItem(LEVEL_KEY);
	if (saved !== null && ['0', '1', '2', '3'].includes(saved))
		return Number(saved) as ReasoningLevel;
	if (localStorage.getItem('neveai.globalThinkingEnabled') === 'false') return 0;
	return localStorage.getItem('neveai.thinkingExtendedEnabled') === 'false' ? 1 : 2;
}

export function setReasoningLevel(level: ReasoningLevel) {
	if (typeof localStorage === 'undefined') return;
	localStorage.setItem(LEVEL_KEY, String(level));
	localStorage.setItem('neveai.globalThinkingEnabled', String(level !== 0));
	localStorage.setItem('neveai.thinkingExtendedEnabled', String(level >= 2));
}

export function getReasoningState(level: ReasoningLevel) {
	return { enabled: level !== 0, extended: level >= 2, unlimited: level === 3 };
}
