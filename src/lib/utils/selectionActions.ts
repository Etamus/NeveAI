import { usesReasoningEffort } from './reasoningModes';

export const getSelectionActionLabel = (
	action: { id: string; label: string },
	translate: (key: string) => string
) => {
	const builtins: Record<string, string[]> = {
		ask: ['Ask', 'Perguntar'],
		explain: ['Explain', 'Explicar']
	};
	const labels = builtins[action.id];
	return labels?.includes(action.label) ? translate(labels[0]) : action.label;
};
export const getSelectionActionParams = (params: Record<string, unknown> = {}, model: any) => {
	const effort = usesReasoningEffort(model);
	const custom = params.custom_params;
	const customParams = custom && typeof custom === 'object' && !Array.isArray(custom)
		? {...custom as Record<string, unknown>} : null;
	if (customParams) {
		for (const key of ['reasoning_mode', 'reasoning_extended', 'reasoning_unlimited', 'no_think', 'reasoning_effort']) delete customParams[key];
	}
	return {
		...params,
		...(customParams ? {custom_params: customParams} : {}),
		reasoning_mode: 'quick',
		reasoning_extended: false,
		reasoning_unlimited: false,
		no_think: !effort,
		...(effort ? {reasoning_effort: 'low'} : {})
	};
};
