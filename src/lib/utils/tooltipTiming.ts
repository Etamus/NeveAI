// Hovering a single tool is usually intentional. Crossing rows in a list is not.
export const slowTooltipDelay = 600;

export function tooltipDelay(anchor: Element, detail = false) {
	if (anchor.matches('[data-title-self], [data-model-selector-unload], [data-tooltip-slow]')) return slowTooltipDelay;
	if (detail) return 150;
	return anchor.closest('[data-model-key], [data-hf-file], [data-hf-repo], [data-catalog-model], [data-queued-download], .files-list-scroll, .advanced-params')
		? 350 : 0;
}
