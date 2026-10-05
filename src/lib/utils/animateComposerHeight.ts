import { tick } from 'svelte';

export interface ComposerLayout {
	key: string;
	context: string;
}

export function animateComposerHeight(node: HTMLElement, layout: ComposerLayout) {
	let previousHeight = node.getBoundingClientRect().height;
	let animation: Animation | null = null;
	let revision = 0;
	let destroyed = false;
	let key = layout.key;
	let context = layout.context;
	let interacted = false;
	const motionSelectors = ['#chat-input', '#input-menu-button', '#send-message-button', '#thinking-dropdown-container > button', '[data-token-usage-trigger]'];
	let motionRects = new Map<string, DOMRect>();
	let partAnimations: Animation[] = [];
	const captureMotionRects = () => {
		motionRects = new Map(motionSelectors.flatMap((selector) => {
			const part = node.querySelector?.<HTMLElement>(selector);
			return part ? [[selector, part.getBoundingClientRect()] as const] : [];
		}));
	};
	const root = node.closest<HTMLElement>('[data-composer-root]');
	const pane = node.closest<HTMLElement>('#chat-pane');
	const readingGap = () => node.classList.contains?.('flex-col') ? 24 : 8;
	let reservationCeiling: { height: number; outside: number; composerHeight: number; preserve?: boolean } | null = null;
	const reserveSpace = (height: number) => {
		if (root && pane && root.dataset.ongoing === 'true') {
			const outside = root.getBoundingClientRect().height - node.getBoundingClientRect().height;
			if (reservationCeiling && (
				Math.abs(outside - reservationCeiling.outside) > 1 ||
				Math.abs(height - reservationCeiling.composerHeight) > 1
			)) reservationCeiling = null;
			const required = Math.ceil(height + outside + readingGap());
			pane.style.setProperty('--chat-composer-height', `${reservationCeiling?.preserve ? reservationCeiling.height : Math.min(required, reservationCeiling?.height ?? required)}px`);
		}
	};
	const noteInteraction = (event: Event) => {
		const target = event.target as Element | null;
		if (target && (node.contains(target) || target.closest('.composer-integrations-menu'))) {
			interacted = true;
			if (event.type === 'pointerdown' || !target.closest?.('#chat-input')) captureMotionRects();
		}
	};
	document.addEventListener('pointerdown', noteInteraction, true);
	document.addEventListener('keydown', noteInteraction, true);
	const clearAnimation = () => {
		animation?.cancel();
		animation = null;
		partAnimations.forEach((part) => part.cancel());
		partAnimations = [];
		node.classList.remove('composer-height-transition');
	};
	const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(() => {
		if (!animation) {
			previousHeight = node.getBoundingClientRect().height;
			reserveSpace(previousHeight);
			captureMotionRects();
		}
	});
	observer?.observe(node);
	if (root) observer?.observe(root);
	void tick().then(() => {
		if (!destroyed && !revision) {
			previousHeight = node.getBoundingClientRect().height;
			captureMotionRects();
		}
	});

	return {
		async update(next: ComposerLayout) {
			if (next.key === key && next.context === context) return;
			const sameContext = next.context === context;
			if (!sameContext) interacted = false;
			key = next.key;
			context = next.context;
			const currentRevision = ++revision;
			const from = animation ? node.getBoundingClientRect().height : previousHeight;
			const fromRects = motionRects;
			const messages = pane?.querySelector<HTMLElement>('#messages-container');
			const wasAtBottom = messages && messages.scrollHeight - messages.clientHeight - messages.scrollTop <= 2;
			const reserved = parseFloat(pane?.style.getPropertyValue('--chat-composer-height') ?? '');
			reservationCeiling = null;
			clearAnimation();
			await tick();
			if (destroyed || currentRevision !== revision) return;
			const to = node.getBoundingClientRect().height;
			previousHeight = to;
			if (sameContext && interacted && to < from && Number.isFinite(reserved) && root) {
				// Removing a chip must not shrink the scroll range and clamp the reading position.
				reservationCeiling = {
					height: reserved,
					outside: root.getBoundingClientRect().height - to,
					composerHeight: to,
					preserve: true
				};
			}
			if (sameContext && interacted && wasAtBottom && to > from && Number.isFinite(reserved) && root && messages) {
				const lastMessage = Array.from(messages.querySelectorAll<HTMLElement>('[id^="message-"]')).at(-1);
				if (lastMessage) {
					// Reuse the existing breathing room instead of adding an empty scroll range.
					const overlap = Math.max(0, lastMessage.getBoundingClientRect().bottom - (node.getBoundingClientRect().top - readingGap()));
					reservationCeiling = {
						height: Math.ceil(reserved + overlap),
						outside: root.getBoundingClientRect().height - to,
						composerHeight: to
					};
				}
			}
			reserveSpace(to);
			if (!sameContext || !interacted || Math.abs(to - from) < 1 || !from || !node.animate) {
				captureMotionRects();
				return;
			}
			node.classList.add('composer-height-transition');
			const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
			const options: KeyframeAnimationOptions = {
				duration: reducedMotion ? 120 : 260,
				easing: 'cubic-bezier(0.33, 1, 0.68, 1)',
				fill: 'both'
			};
			// Measure final layout before the height animation changes compact-row alignment.
			const finalRects = new Map(motionSelectors.flatMap((selector) => {
				const part = node.querySelector?.<HTMLElement>(selector);
				return part ? [[selector, part.getBoundingClientRect()] as const] : [];
			}));
			animation = node.animate([{ height: `${from}px` }, { height: `${to}px` }], options);
			if (to < from) {
				// Keep controls at their previous screen position while switching to the compact row.
				for (const selector of motionSelectors) {
					const part = node.querySelector?.<HTMLElement>(selector);
					const before = fromRects.get(selector);
					if (!part?.animate || !before) continue;
					const after = root?.dataset.ongoing === 'true' && selector !== '#chat-input'
						? finalRects.get(selector)! : part.getBoundingClientRect();
					const x = before.left - after.left;
					const y = before.top - after.top;
					if (Math.abs(x) < 0.5 && Math.abs(y) < 0.5) continue;
					partAnimations.push(part.animate([
						{ transform: `translate(${x}px, ${y}px)` },
						{ transform: 'translate(0px, 0px)' }
					], options));
				}
			}
			const currentAnimation = animation;
			animation.onfinish = () => {
				if (animation === currentAnimation) {
					clearAnimation();
					reserveSpace(to);
					captureMotionRects();
				}
			};
		},
		destroy() {
			destroyed = true;
			revision++;
			observer?.disconnect();
			clearAnimation();
			document.removeEventListener('pointerdown', noteInteraction, true);
			document.removeEventListener('keydown', noteInteraction, true);
		}
	};
}
