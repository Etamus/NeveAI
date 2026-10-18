import type { Instance } from 'tippy.js';

type TooltipElement = Element & { _tippy?: Instance };

export const dismissTooltipsOnMediaScroll = (viewport: HTMLElement, active: () => boolean) => {
	const suppressed = new Set<Instance>();
	const restore = (event?: Event) => {
		for (const instance of suppressed) {
			if (instance.state.isDestroyed) continue;
			instance.enable();
			if (event?.type === 'pointermove' && event.target instanceof Element && instance.reference.contains(event.target)) {
				instance.show();
			}
		}
		suppressed.clear();
	};
	const suppress = (element: TooltipElement) => {
		const instance = element._tippy;
		if (!instance || !viewport.contains(instance.reference) || !instance.state.isEnabled) return;
		instance.disable();
		instance.unmount();
		suppressed.add(instance);
	};
	const dismiss = (event: Event) => {
		if (!active()) { restore(); return; }
		// Include pending hover timers as well as tooltips already portaled outside the chat.
		let target = event.target instanceof Element ? event.target : null;
		while (target && target !== viewport) {
			suppress(target as TooltipElement);
			target = target.parentElement;
		}
		for (const popper of document.querySelectorAll<TooltipElement>('[data-tippy-root]')) suppress(popper);
	};
	viewport.addEventListener('wheel', dismiss, { passive: true });
	viewport.addEventListener('scroll', dismiss);
	viewport.addEventListener('pointermove', restore);
	viewport.addEventListener('pointerdown', restore);
	return () => {
		restore();
		viewport.removeEventListener('wheel', dismiss);
		viewport.removeEventListener('scroll', dismiss);
		viewport.removeEventListener('pointermove', restore);
		viewport.removeEventListener('pointerdown', restore);
	};
};
