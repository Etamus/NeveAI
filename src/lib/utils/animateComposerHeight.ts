import { tick } from 'svelte';

export interface ComposerLayout {
	key: string;
	context: string;
	conversation?: string;
}

export const COMPOSER_READING_GAP = 88;
export const SYNC_COMPOSER_LAYOUT = 'neve:sync-composer-layout';

export function animateComposerHeight(node: HTMLElement, layout: ComposerLayout) {
	const root = node.closest<HTMLElement>('[data-composer-root]');
	const pane = node.closest<HTMLElement>('#chat-pane');
	let currentLayout = layout;
	let revision = 0;
	let destroyed = false;
	let messages: HTMLElement | null = null;
	let scrollTop = 0;
	let followingEnd = false;
	let previousSize = '';

	const rememberScroll = () => {
		if (!messages) return;
		scrollTop = messages.scrollTop;
		followingEnd = messages.scrollHeight - messages.clientHeight - scrollTop <= 2;
	};

	const synchronize = () => {
		if (destroyed || !root || !pane || root.dataset.ongoing !== 'true') return;
		const nextMessages = pane.querySelector<HTMLElement>('#messages-container');
		if (messages !== nextMessages) {
			if (messages) {
				messages.removeEventListener('scroll', rememberScroll);
				observer?.unobserve(messages);
			}
			messages = nextMessages;
			messages?.addEventListener('scroll', rememberScroll, { passive: true });
			if (messages) observer?.observe(messages);
			rememberScroll();
		}
		if (!messages) return;
		const content = messages.querySelector<HTMLElement>('[data-messages-content]');
		const lastMessage = Array.from(messages.querySelectorAll<HTMLElement>(
			'[role="log"] > [role="listitem"], [role="log"] > [data-message-window] > div > [role="listitem"]'
		)).at(-1);
		if (!content || !lastMessage) return;

		const composerRect = node.getBoundingClientRect();
		const viewport = messages.getBoundingClientRect();
		const spacer = content.querySelector<HTMLElement>('[data-generation-spacer]');
		// The generation anchor owns its spacer; only the static transcript tail counts here.
		const tail = content.getBoundingClientRect().bottom - lastMessage.getBoundingClientRect().bottom - (spacer?.getBoundingClientRect().height ?? 0);
		const viewportPadding = parseFloat(getComputedStyle(messages).paddingBottom) || 0;
		const required = Math.ceil(Math.max(0, viewport.bottom - composerRect.top + COMPOSER_READING_GAP - tail - viewportPadding));
		const size = `${composerRect.height}:${composerRect.width}:${messages.clientHeight}:${required}`;
		const changed = previousSize !== size || pane.style.getPropertyValue('--chat-composer-height') !== `${required}px`;
		previousSize = size;
		if (!changed) return;

		const anchor = scrollTop;
		const follow = followingEnd;
		pane.style.setProperty('--chat-composer-height', `${required}px`);
		if (root.dataset.generating !== 'true') {
			const maximum = Math.max(0, messages.scrollHeight - messages.clientHeight);
			messages.scrollTop = follow ? maximum : Math.min(anchor, maximum);
		}
		rememberScroll();
	};

	const noteInteraction = (event: Event) => {
		const target = event.target as Element | null;
		if (target && (node.contains(target) || target.closest('.composer-integrations-menu, [data-model-selector-content], [id^="model-selector-"]'))) {
			rememberScroll();
		}
	};
	const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(synchronize);
	observer?.observe(node);
	if (root) observer?.observe(root);
	root?.addEventListener(SYNC_COMPOSER_LAYOUT, synchronize);
	const interactionEvents = ['pointerdown', 'keydown', 'paste', 'beforeinput'];
	for (const event of interactionEvents) document.addEventListener(event, noteInteraction, true);
	void tick().then(synchronize);

	return {
		async update(next: ComposerLayout) {
			if (next.key === currentLayout.key && next.context === currentLayout.context && (next.conversation ?? next.context) === (currentLayout.conversation ?? currentLayout.context)) return;
			// Draft attachments may already have changed the transcript tail in this DOM update.
			if ((next.conversation ?? next.context) !== (currentLayout.conversation ?? currentLayout.context)) rememberScroll();
			currentLayout = next;
			const currentRevision = ++revision;
			await tick();
			if (!destroyed && currentRevision === revision) synchronize();
		},
		destroy() {
			destroyed = true;
			revision++;
			observer?.disconnect();
			messages?.removeEventListener('scroll', rememberScroll);
			root?.removeEventListener(SYNC_COMPOSER_LAYOUT, synchronize);
			for (const event of interactionEvents) document.removeEventListener(event, noteInteraction, true);
		}
	};
}
