export interface AccordionScrollState {
	startTop: number;
	startMax: number;
	targetTop: number | null;
	followBottom: boolean;
	revealLimit: number;
}

export function getAccordionScrollPosition(state: AccordionScrollState, naturalMax: number, progress: number) {
	// Native scrollHeight is rounded; retain fractional growth for anchor tracking.
	const physicalMax = Math.ceil(naturalMax);
	const destination = state.targetTop !== null
		? Math.min(state.targetTop, physicalMax)
		: state.followBottom
			? Math.min(physicalMax, state.startTop + Math.min(state.revealLimit, Math.max(0, naturalMax - state.startMax)))
			: Math.min(state.startTop, physicalMax);
	const eased = 1 - Math.pow(1 - Math.max(0, Math.min(1, progress)), 3);
	// Follow the rendered height, not a second easing curve: the answer below stays in place.
	const top = state.followBottom
		? destination
		: state.targetTop !== null
			? Math.max(destination, Math.min(state.startTop, state.startTop + naturalMax - state.startMax))
			: state.startTop + (destination - state.startTop) * eased;
	return {
		top: progress < 1 ? top : destination,
		// Temporary support prevents browser clamping during collapse; it must finish at zero.
		spacer: progress < 1 ? Math.max(0, Math.ceil(top - naturalMax)) : 0
	};
}
