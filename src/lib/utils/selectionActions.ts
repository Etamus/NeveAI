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
