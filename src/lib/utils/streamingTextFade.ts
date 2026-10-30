import { tick } from 'svelte';
import type { StreamingPaintContext } from './marked/streaming-structure';

type FadeState = { text: string; done: boolean; paintContext?: StreamingPaintContext };
type Fade = { name: string; range: Range; rule: CSSStyleRule; start: number; from: number; to: number };

let stylesheet: CSSStyleSheet | null | undefined;
let nextId = 0;

type ScrollGroup = { until: number; finish: Set<() => void>; wheel: (event: WheelEvent) => void };
const scrollGroups = new WeakMap<HTMLElement, ScrollGroup>();

function observeStreamingScroll(viewport: HTMLElement, finish: () => void) {
	let group = scrollGroups.get(viewport);
	if (!group) {
		group = { until: 0, finish: new Set(), wheel: () => {} };
		const current = group;
		current.wheel = (event) => {
			if (event.deltaY <= 0 || event.ctrlKey) return;
			current.until = performance.now() + 180;
			// Compositor scrolling must never expose a partially transparent text layer.
			for (const complete of current.finish) complete();
		};
		scrollGroups.set(viewport, current);
	}
	if (!group.finish.size) viewport.addEventListener('wheel', group.wheel, { passive: true, capture: true });
	group.finish.add(finish);
	return { group, release() {
		group.finish.delete(finish);
		if (!group.finish.size) {
			viewport.removeEventListener('wheel', group.wheel, true);
		}
	} };
}

function getStylesheet(): CSSStyleSheet | null {
	if (stylesheet === undefined) {
		const style = document.createElement('style');
		style.dataset.streamingTextFade = '';
		document.head.appendChild(style);
		stylesheet = style.sheet;
		if (!stylesheet) style.remove();
	}
	return stylesheet;
}

// Highlight color changes paint only; word wrappers change text shaping/rounding.
export function streamingTextFade(node: HTMLElement, initial: FadeState) {
	const supported = typeof CSS !== 'undefined' && !!CSS.highlights &&
		typeof Highlight !== 'undefined' &&
		CSS.supports('selector(::highlight(neve-stream-check))') &&
		CSS.supports('color', 'color-mix(in srgb, currentColor 50%, transparent)');
	if (!supported) return {};
	const sheet = getStylesheet();
	if (!sheet) return {};
	let previous = '';
	let frame: number | undefined;
	let fades: Fade[] = [];
	let revision = 0;
	let destroyed = false;
	let scroll: ReturnType<typeof observeStreamingScroll> | undefined;

	const remove = (fade: Fade) => {
		CSS.highlights.delete(fade.name);
		const index = Array.from(sheet.cssRules).indexOf(fade.rule);
		if (index !== -1) sheet.deleteRule(index);
	};
	const clear = () => {
		if (frame !== undefined) cancelAnimationFrame(frame);
		frame = undefined;
		fades.forEach(remove);
		fades = [];
	};
	const animate = (now: number) => {
		frame = undefined;
		let color: string | undefined;
		fades = fades.filter((fade) => {
			const progress = Math.min(1, Math.max(0, (now - fade.start) / 100));
			if (progress === 1) {
				remove(fade);
				return false;
			}
			color ??= getComputedStyle(node).color;
			fade.rule.style.color = `color-mix(in srgb, ${color} ${progress * 100}%, transparent)`;
			return true;
		});
		if (fades.length) frame = requestAnimationFrame(animate);
	};
	const apply = ({ text, done, paintContext }: FadeState) => {
		if (done) {
			scroll?.release();
			scroll = undefined;
			previous = text;
			clear();
			return;
		}
		if (!scroll) {
			const viewport = node.closest?.<HTMLElement>('#messages-container');
			if (viewport) scroll = observeStreamingScroll(viewport, clear);
		}
		if (scroll && performance.now() < scroll.group.until) {
			previous = text;
			clear();
			return;
		}
		if (paintContext?.suppress) {
			previous = text;
			clear();
			return;
		}
		if (text === previous) return;
		const child = node.firstChild;
		if (!child || child.nodeType !== 3 || child.textContent !== text) {
			clear();
			previous = text;
			return;
		}
		const from = text.startsWith(previous) ? previous.length : 0;
		if (!from) clear();
		// Svelte updates Text.data; restore live ranges after that replacement.
		for (const fade of fades) {
			fade.range.setStart(child, fade.from);
			fade.range.setEnd(child, fade.to);
		}
		previous = text;
		if (from === text.length) return;
		const name = `neve-stream-${nextId++}`;
		const range = document.createRange();
		range.setStart(child, from);
		range.setEnd(child, text.length);
		const index = sheet.insertRule(`::highlight(${name}) { color: transparent; }`, sheet.cssRules.length);
		const rule = sheet.cssRules[index] as CSSStyleRule;
		CSS.highlights.set(name, new Highlight(range));
		fades.push({ name, range, rule, from, to: text.length, start: performance.now() });
		if (frame === undefined) frame = requestAnimationFrame(animate);
	};
	const update = (state: FadeState) => {
		const current = ++revision;
		void tick().then(() => {
			if (!destroyed && current === revision) apply(state);
		});
	};
	update(initial);
	return { update, destroy() { destroyed = true; revision++; clear(); scroll?.release(); } };
}
