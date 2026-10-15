import { tick } from 'svelte';

export interface ComposerLayout {
	key: string;
	context: string;
	conversation?: string;
}

export function animateComposerHeight(node: HTMLElement, layout: ComposerLayout) {
	let previousHeight = node.getBoundingClientRect().height;
	let revision = 0;
	let destroyed = false;
	let key = layout.key;
	let context = layout.context;
	let conversation = layout.conversation ?? layout.context;
	let interacted = false;
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
		if (target && (node.contains(target) || target.closest('.composer-integrations-menu, [data-model-selector-content], [id^="model-selector-"]'))) {
			interacted = true;
		}
	};
	document.addEventListener('pointerdown', noteInteraction, true);
	document.addEventListener('keydown', noteInteraction, true);
	document.addEventListener('paste', noteInteraction, true);
	document.addEventListener('beforeinput', noteInteraction, true);
	const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(() => {
		previousHeight = node.getBoundingClientRect().height;
		reserveSpace(previousHeight);
	});
	observer?.observe(node);
	if (root) observer?.observe(root);
	void tick().then(() => {
		if (!destroyed && !revision) {
			previousHeight = node.getBoundingClientRect().height;
		}
	});

	return {
		async update(next: ComposerLayout) {
			if (next.key === key && next.context === context && (next.conversation ?? next.context) === conversation) return;
			const sameContext = next.context === context;
			const sameConversation = (next.conversation ?? next.context) === conversation;
			if (!sameConversation) interacted = false;
			key = next.key;
			context = next.context;
			conversation = next.conversation ?? next.context;
			const currentRevision = ++revision;
			const from = previousHeight;
			const messages = pane?.querySelector<HTMLElement>('#messages-container');
			const wasAtBottom = messages && messages.scrollHeight - messages.clientHeight - messages.scrollTop <= 2;
			const reserved = parseFloat(pane?.style.getPropertyValue('--chat-composer-height') ?? '');
			reservationCeiling = null;
			await tick();
			if (destroyed || currentRevision !== revision) return;
			const to = node.getBoundingClientRect().height;
			previousHeight = to;
			const preserveReadingPosition = sameConversation && (interacted || !sameContext);
			if (preserveReadingPosition && to <= from && Number.isFinite(reserved) && root) {
				// Removing a chip must not shrink the scroll range and clamp the reading position.
				reservationCeiling = {
					height: reserved,
					outside: root.getBoundingClientRect().height - to,
					composerHeight: to,
					preserve: true
				};
			}
			if (preserveReadingPosition && wasAtBottom && to > from && Number.isFinite(reserved) && root && messages) {
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
		},
		destroy() {
			destroyed = true;
			revision++;
			observer?.disconnect();
			document.removeEventListener('pointerdown', noteInteraction, true);
			document.removeEventListener('keydown', noteInteraction, true);
			document.removeEventListener('paste', noteInteraction, true);
			document.removeEventListener('beforeinput', noteInteraction, true);
		}
	};
}
