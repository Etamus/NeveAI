import tippy, { type Instance } from 'tippy.js';

/** Use the existing tooltip theme for native titles, without scanning or observing the DOM. */
export function installTitleTooltips(root: Document) {
	type Entry = { owner: HTMLElement; anchor: Element; text: string; addedLabel: boolean; tooltip: Instance | null; borrowed: Instance | null };
	let active: Entry | null = null;
	const pending = new Map<HTMLElement, Entry>();
	function restore(entry: Entry) {
		if (!entry.owner.hasAttribute('title')) entry.owner.setAttribute('title', entry.text);
		if (entry.addedLabel && entry.anchor.getAttribute('aria-label') === entry.text) entry.anchor.removeAttribute('aria-label');
		pending.delete(entry.owner);
	}
	function restoreOutside(target: EventTarget | null) {
		for (const entry of pending.values()) if (!(target instanceof Node) || !entry.anchor.contains(target)) restore(entry);
	}
	function clear() {
		const previous = active;
		active = null;
		if (!previous) return;
		previous.tooltip?.destroy();
		previous.borrowed?.hide();
		if (previous.anchor.matches(':hover') && root.contains(previous.anchor)) pending.set(previous.owner, previous);
		else restore(previous);
	}
	function dismiss() {
		if (!active) return;
		active.tooltip?.destroy();
		active.borrowed?.hide();
		active.tooltip = null;
		active.borrowed = null;
	}
	function enter(event: Event) {
		if (event instanceof PointerEvent && event.pointerType === 'touch') return;
		const target = event.target;
		if (!(target instanceof Element)) return;
		if (event.type === 'pointerover') restoreOutside(target);
		if (active?.anchor.contains(target)) {
			const previous = (event as PointerEvent).relatedTarget;
			const freshPointerEntry = event.type === 'pointerover' && (!(previous instanceof Node) || !active.anchor.contains(previous));
			if (!freshPointerEntry || active.tooltip || active.borrowed || active.anchor.getAttribute('aria-expanded') === 'true') return;
			restore(active);
			active = null;
		}
		clear();
		const owner = target.closest('[title]');
		if (!(owner instanceof HTMLElement) || owner.tagName === 'IFRAME') return;
		const text = owner.getAttribute('title');
		if (!text?.trim()) return;
		const anchor = owner.closest('button, a, [role="button"]') ?? owner;
		let borrowed: Instance | null = null;
		for (let node: Element | null = anchor; node; node = node.parentElement) {
			const existing = (node as Element & { _tippy?: Instance })._tippy;
			if (existing) { borrowed = existing; break; }
		}
		owner.removeAttribute('title');
		const addedLabel = !anchor.hasAttribute('aria-label') && !anchor.hasAttribute('aria-labelledby') && !anchor.textContent?.trim();
		if (addedLabel) anchor.setAttribute('aria-label', text);
		const expanded = anchor.getAttribute('aria-expanded') === 'true';
		const tooltip = borrowed || expanded ? null : tippy(anchor, {
			content: text, allowHTML: false, theme: 'dark', arrow: false, offset: [0, 4],
			placement: 'top', trigger: 'manual',
			...(anchor.closest('[data-model-download-toast]') ? { zIndex: 1000000001 }
				: anchor.closest('[data-download-progress-menu]') ? { zIndex: 10003 } : {})
		});
		active = { owner, anchor, text, addedLabel, tooltip, borrowed };
		if (!expanded) (tooltip ?? borrowed)?.show();
	}
	function leave(event: Event) {
		const next = (event as MouseEvent | FocusEvent).relatedTarget;
		if (active && (!(next instanceof Node) || !active.anchor.contains(next))) clear();
		if (event.type === 'pointerout') restoreOutside(next);
	}
	function key(event: KeyboardEvent) { if (event.key === 'Escape') dismiss(); }
	root.addEventListener('pointerover', enter, true);
	root.addEventListener('focusin', enter, true);
	root.addEventListener('pointerout', leave, true);
	root.addEventListener('focusout', leave, true);
	root.addEventListener('pointerdown', dismiss, true);
	root.addEventListener('click', dismiss, true);
	root.addEventListener('scroll', dismiss, true);
	root.addEventListener('keydown', key, true);
	root.addEventListener('visibilitychange', clear);
	return () => {
		clear();
		restoreOutside(null);
		root.removeEventListener('pointerover', enter, true);
		root.removeEventListener('focusin', enter, true);
		root.removeEventListener('pointerout', leave, true);
		root.removeEventListener('focusout', leave, true);
		root.removeEventListener('pointerdown', dismiss, true);
		root.removeEventListener('click', dismiss, true);
		root.removeEventListener('scroll', dismiss, true);
		root.removeEventListener('keydown', key, true);
		root.removeEventListener('visibilitychange', clear);
	};
}
