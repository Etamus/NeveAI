import morphdom from 'morphdom';
import type { PreviewPacket } from './types';
import { isExecutableArtifactScript } from './scriptTypes';
import { followCursorTarget } from './cursorFollow';

// This module runs only inside the opaque-origin preview, never in the application DOM.
const frame = window as any;
let port: MessagePort;
let live = false;
let requestedLive: boolean | undefined;
let lastJS = '';
let files: string[] = [];
let rootPage = 'index.html';
let moduleURL: string | null = null;
let connected = false;
let reactReady: Promise<void> | null = null;
let tailwindReady: Promise<void> | null = null;
let candidate: Element | null = null;
let cursorRAF = 0;
let cursor: HTMLDivElement;
let idleTimer: ReturnType<typeof setTimeout>;
let centerTimer: ReturnType<typeof setTimeout>;
let starting = false;
let contentObserver: MutationObserver | null = null;
let followScrollRAF = 0;
const scripts = new Set<string>();
let styleRules = new Map<string, string>();
let previousBody = '';
let sourceNodes = new Map<string, Element>();
let lastImportMap = '';

for (const name of ['localStorage', 'sessionStorage']) {
	try {
		void window[name].length;
	} catch {
		const values = new Map<string, string>();
		let bytes = 0;
		const storage = {
			get length() {
				return values.size;
			},
			key: (index: number) => [...values.keys()][index] ?? null,
			getItem: (key: string) => values.get(String(key)) ?? null,
			setItem: (key: string, value: string) => {
				key = String(key);
				value = String(value);
				const next =
					bytes +
					2 * (key.length + value.length) -
					(values.has(key) ? 2 * (key.length + values.get(key)!.length) : 0);
				if (next > 5 * 1024 * 1024)
					throw new DOMException('Preview storage quota exceeded', 'QuotaExceededError');
				values.set(key, value);
				bytes = next;
			},
			removeItem: (key: string) => {
				key = String(key);
				if (values.has(key)) bytes -= 2 * (key.length + values.get(key)!.length);
				values.delete(key);
			},
			clear: () => {
				values.clear();
				bytes = 0;
			}
		};
		Object.defineProperty(window, name, { value: storage });
	}
}

function indexSource(
	root: Element,
	nodes?: Map<string, Element>,
	keys?: WeakMap<Element, string>,
	path = 'body'
) {
	const key = root.id ? '#' + root.id : path;
	nodes?.set(key, root);
	keys?.set(root, key);
	for (const [index, child] of [...root.children].entries())
		indexSource(child, nodes, keys, path + '/' + index);
}

function pointTo(element: Element | null) {
	if (
		!live ||
		document.hidden ||
		!element?.isConnected ||
		element === document.body ||
		element === document.documentElement ||
		element.closest('[data-neve-cursor]')
	)
		return;
	if (!candidate || !element.contains(candidate)) candidate = element;
	if (starting) return;
	if (cursorRAF) return;
	cursorRAF = requestAnimationFrame(() => {
		cursorRAF = 0;
		const target = candidate;
		candidate = null;
		if (!target?.isConnected || !live || document.hidden) return;
		let bounds = target.getBoundingClientRect();
		if (!bounds.width || !bounds.height) return;
		if (followCursorTarget(target)) {
			if (followScrollRAF) cancelAnimationFrame(followScrollRAF);
			followScrollRAF = requestAnimationFrame(() => {
				followScrollRAF = 0;
			});
			bounds = target.getBoundingClientRect();
		}
		cursor.style.transform = `translate(${Math.max(4, Math.min(innerWidth - 24, bounds.left + Math.min(bounds.width / 2, 32)))}px,${Math.max(4, Math.min(innerHeight - 28, bounds.top + Math.min(bounds.height / 2, 16)))}px)`;
		cursor.style.opacity = '1';
		clearTimeout(idleTimer);
		idleTimer = setTimeout(() => {
			cursor.style.opacity = '0';
		}, 900);
	});
}

function refreshTracking() {
	if (live && !document.hidden) {
		contentObserver?.observe(document.body, {
			subtree: true,
			childList: true,
			characterData: true
		});
		return;
	}
	contentObserver?.disconnect();
	if (cursorRAF) cancelAnimationFrame(cursorRAF);
	if (followScrollRAF) cancelAnimationFrame(followScrollRAF);
	cursorRAF = followScrollRAF = 0;
	candidate = null;
	clearTimeout(idleTimer);
	clearTimeout(centerTimer);
	starting = false;
	if (cursor) cursor.style.opacity = '0';
}

function setLive(value: boolean) {
	const wasLive = live;
	live = value;
	refreshTracking();
	if (!live || wasLive || document.hidden) return;
	starting = true;
	cursor.style.transform = `translate(${Math.max(0, (innerWidth - 24) / 2)}px,${Math.max(0, (innerHeight - 28) / 2)}px)`;
	cursor.style.opacity = '1';
	centerTimer = setTimeout(() => {
		starting = false;
		if (candidate) pointTo(candidate);
	}, 180);
}
document.addEventListener('visibilitychange', refreshTracking);

function installCursor() {
	cursor = document.createElement('div');
	cursor.dataset.neveCursor = '';
	cursor.setAttribute('aria-hidden', 'true');
	cursor.style.cssText =
		'all:initial;position:fixed!important;left:0!important;top:0!important;width:24px!important;height:28px!important;pointer-events:none!important;z-index:2147483647!important;opacity:0;transition:transform 200ms ease-out,opacity 120ms;filter:drop-shadow(0 1px 2px #0004)';
	cursor.attachShadow({ mode: 'open' }).innerHTML =
		'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="28" viewBox="0 0 24 28" fill="#3b82f6" stroke="white" stroke-width="1.2"><path d="M4 3L20 13.5L12.2 15.1L8.5 22.5Z"/></svg>';
	document.documentElement.append(cursor);
}

function moduleShim(globalName: string, keys: string[]) {
	const exports = keys.filter((key) => key !== 'default' && /^[A-Za-z_$][\w$]*$/.test(key));
	return (
		'data:text/javascript;charset=utf-8,' +
		encodeURIComponent(
			`const value=window[${JSON.stringify(globalName)}]; export default value; ${exports.map((key) => `export const ${key}=value.${key};`).join('\n')}`
		)
	);
}

function loadVendor(name: string): Promise<void> {
	return new Promise((resolve, reject) => {
		const script = document.createElement('script');
		const embedded = frame.__neveVendorSources?.[name];
		if (embedded) {
			script.textContent = embedded;
			document.head.append(script);
			resolve();
		} else {
			script.src = frame.__neveAssets + '/' + name + '.js';
			script.onload = () => resolve();
			script.onerror = () => reject(new Error(name + ' runtime could not be loaded'));
			document.head.append(script);
		}
	});
}

async function loadReact() {
	if (reactReady) return reactReady;
	reactReady = (async () => {
		// React Refresh's hook must exist before ReactDOM initializes.
		frame.__REACT_DEVTOOLS_GLOBAL_HOOK__ ??= {
			supportsFiber: true,
			renderers: new Map(),
			inject(renderer) {
				const id = this.renderers.size + 1;
				this.renderers.set(id, renderer);
				return id;
			},
			onCommitFiberRoot() {},
			onCommitFiberUnmount() {}
		};
		if (!frame.__NEVE_REACT__) await loadVendor('react');
		frame.__NEVE_REFRESH__.injectIntoGlobalHook(window);
		const importmap = document.createElement('script');
		importmap.type = 'importmap';
		importmap.textContent = JSON.stringify({
			imports: {
				react: moduleShim('__NEVE_REACT__', Object.keys(frame.__NEVE_REACT__)),
				'react-dom': moduleShim('__NEVE_DOM__', Object.keys(frame.__NEVE_DOM__)),
				'react-dom/client': moduleShim('__NEVE_DOM_CLIENT__', ['createRoot']),
				'react/jsx-runtime': moduleShim('__NEVE_JSX__', Object.keys(frame.__NEVE_JSX__)),
				'react/jsx-dev-runtime': moduleShim('__NEVE_JSX__', Object.keys(frame.__NEVE_JSX__))
			}
		});
		document.head.append(importmap);
	})();
	return reactReady;
}

async function apply(packet: PreviewPacket) {
	setLive(packet.live && requestedLive !== false);
	if (CSS.supports('color', packet.accent))
		cursor.shadowRoot!.querySelector('svg')!.setAttribute('fill', packet.accent);
	files = packet.files;
	if (!live) cursor.style.opacity = '0';
	const parsed = new DOMParser().parseFromString(packet.html, 'text/html');
	const external = [...parsed.querySelectorAll('script[src]')]
		.filter((node) => isExecutableArtifactScript(node.getAttribute('type')))
		.map((node) => node.cloneNode(true) as HTMLScriptElement);
	parsed.querySelectorAll('script').forEach((node) => {
		if (
			isExecutableArtifactScript(node.getAttribute('type')) ||
			node.getAttribute('type')?.toLowerCase() === 'importmap'
		)
			node.remove();
	});
	parsed.head.querySelectorAll('base').forEach((node) => node.remove());
	// Generated HTML can replace page styling, but not the preview bridge and its import map.
	if (packet.css) {
		const style = parsed.createElement('style');
		style.textContent = packet.css;
		parsed.head.append(style);
	}
	const previousHead = [...document.head.querySelectorAll('[data-neve-content]')];
	const incomingHead = [...parsed.head.children];
	let headChanged = previousHead.length !== incomingHead.length;
	for (const [index, node] of incomingHead.entries()) {
		node.setAttribute('data-neve-content', '');
		if (previousHead[index]?.isEqualNode(node)) continue;
		headChanged = true;
		if (previousHead[index]) previousHead[index].replaceWith(node);
		else document.head.append(node);
	}
	for (const node of previousHead.slice(incomingHead.length)) node.remove();
	const nextRules = headChanged ? new Map<string, string>() : styleRules;
	for (const sheet of headChanged ? document.styleSheets : []) {
		try {
			for (const rule of sheet.cssRules) {
				if (rule instanceof CSSStyleRule) nextRules.set(rule.selectorText, rule.cssText);
			}
		} catch {
			/* Cross-origin stylesheets cannot be inspected. */
		}
	}
	const x = scrollX,
		y = scrollY;
	const body = parsed.body.outerHTML;
	if (body !== previousBody) {
		const keys = new WeakMap<Element, string>();
		const nextSource = new Map<string, Element>();
		indexSource(parsed.body, undefined, keys);
		indexSource(parsed.body.cloneNode(true) as Element, nextSource);
		morphdom(document.body, parsed.body, {
			onBeforeElUpdated(from, to) {
				if (packet.react && frame.__NEVE_ROOTS__?.has(from)) return false;
				const key = keys.get(to);
				// Preserve script-driven DOM and input state when its source did not change.
				if (key && sourceNodes.get(key)?.isEqualNode(to)) return false;
				if (from.isEqualNode(to)) return false;
				if (
					(from instanceof HTMLInputElement || from instanceof HTMLTextAreaElement) &&
					(from === document.activeElement || from.value !== from.defaultValue)
				) {
					(to as HTMLInputElement).value = from.value;
				}
				if (from instanceof HTMLInputElement && from.checked !== from.defaultChecked)
					(to as HTMLInputElement).checked = from.checked;
				return true;
			},
			onElUpdated: pointTo,
			onNodeAdded(node) {
				if (node instanceof Element) pointTo(node);
			},
			getNodeKey: (node) => (node as Element).id
		});
		sourceNodes = nextSource;
		previousBody = body;
	}
	for (const [element, root] of frame.__NEVE_ROOTS__ ?? []) {
		if (!document.contains(element)) {
			root.unmount();
			frame.__NEVE_ROOTS__.delete(element);
		}
	}
	scrollTo(x, y);
	if (styleRules.size && live) {
		let inspected = 0;
		for (const [selector, text] of nextRules) {
			if (styleRules.get(selector) === text) continue;
			try {
				pointTo(document.querySelector(selector));
			} catch {
				/* Not every stylesheet selector is queryable. */
			}
			if (++inspected >= 32) break;
		}
	}
	styleRules = nextRules;
	for (const original of external) {
		const src = original.getAttribute('src')!;
		if (scripts.has(src)) continue;
		await new Promise<void>((resolve, reject) => {
			const script = document.createElement('script');
			for (const attr of original.attributes) script.setAttribute(attr.name, attr.value);
			script.onload = () => {
				scripts.add(src);
				resolve();
			};
			script.onerror = () => reject(new Error('Could not load ' + src));
			document.head.append(script);
		});
	}
	if (packet.react) await loadReact();
	const imports = Object.fromEntries(
		Object.entries(packet.imports ?? {}).filter(
			([name]) => !packet.react || !/^(?:react|react-dom)(?:\/|$)/.test(name)
		)
	);
	const importMap = JSON.stringify({ imports });
	if (Object.keys(imports).length && lastImportMap !== importMap) {
		const map = document.createElement('script');
		map.type = 'importmap';
		map.textContent = importMap;
		document.head.append(map);
		lastImportMap = importMap;
	}
	if (packet.tailwind && !frame.__NEVE_TAILWIND__) {
		tailwindReady ??= loadVendor('tailwind').then(() => {
			frame.__NEVE_TAILWIND__ = true;
		});
		await tailwindReady;
	}
	if (packet.js !== lastJS && packet.js) {
		const previous = moduleURL;
		moduleURL = URL.createObjectURL(new Blob([packet.js], { type: 'text/javascript' }));
		try {
			const renders = frame.__NEVE_RENDER_COUNT__ ?? 0;
			const module = await import(/* @vite-ignore */ moduleURL);
			if (packet.react && module.app) {
				const app = module.app;
				for (const [name, value] of Object.entries(app)) {
					if (typeof value === 'function')
						frame.__NEVE_REFRESH__.register(value, 'artifact:' + name);
				}
				const component =
					app.default ??
					app.App ??
					app.__neveDefault ??
					Object.values(app).find((value) => typeof value === 'function');
				if (component && (frame.__NEVE_RENDER_COUNT__ ?? 0) === renders) {
					const container =
						document.getElementById('root') ??
						document.getElementById('app') ??
						document.body.appendChild(Object.assign(document.createElement('div'), { id: 'root' }));
					frame.__NEVE_REFRESH__.performReactRefresh();
					frame.__NEVE_DOM_CLIENT__
						.createRoot(container)
						.render(frame.__NEVE_REACT__.createElement(component));
				}
			}
			lastJS = packet.js;
			if (typeof window.onload === 'function') window.onload.call(window, new Event('load'));
		} finally {
			if (previous) URL.revokeObjectURL(previous);
		}
	}
	if (!packet.js && !packet.preserveJS) lastJS = '';
	port.postMessage({ type: 'applied' });
}

let pendingUpdate: PreviewPacket | null = null;
let updating = false;
async function drainUpdates() {
	if (updating) return;
	updating = true;
	try {
		while (pendingUpdate) {
			const packet = pendingUpdate;
			pendingUpdate = null;
			try {
				await apply(packet);
			} catch (error) {
				port.postMessage({ type: 'error', message: String(error.message ?? error) });
			}
		}
	} finally {
		updating = false;
	}
}
window.addEventListener('message', (event) => {
	if (
		connected ||
		event.source !== parent ||
		event.data?.type !== 'neve-preview-connect' ||
		!event.ports[0]
	)
		return;
	connected = true;
	port = event.ports[0];
	port.onmessage = ({ data }) => {
		if (data.type === 'live') {
			requestedLive = data.value === true;
			setLive(requestedLive);
			return;
		}
		if (data.type === 'page') {
			rootPage = data.path;
			return;
		}
		if (data.type !== 'update') return;
		pendingUpdate = data.packet;
		void drainUpdates();
	};
	port.start();
	installCursor();
	contentObserver = new MutationObserver((records) => {
		if (!live || document.hidden || followScrollRAF) return;
		for (const record of records) {
			const node = record.addedNodes[0] ?? record.target;
			if (node instanceof Element) pointTo(node);
			else pointTo(node.parentElement);
		}
	});
	refreshTracking();
	port.postMessage({ type: 'ready' });
});
window.addEventListener('error', (event) =>
	port?.postMessage({ type: 'error', message: event.message })
);
window.addEventListener('unhandledrejection', (event) =>
	port?.postMessage({ type: 'error', message: String(event.reason?.message ?? event.reason) })
);
document.addEventListener(
	'click',
	(event) => {
		const link = (event.target as Element)?.closest?.('a[href]') as HTMLAnchorElement;
		if (!link) return;
		const href = link.getAttribute('href')!;
		if (href.startsWith('#')) {
			event.preventDefault();
			document.getElementById(decodeURIComponent(href.slice(1)))?.scrollIntoView();
			return;
		}
		if (/^(?:https?:|mailto:|tel:)/i.test(href)) return;
		event.preventDefault();
		const url = new URL(href, 'https://artifact.invalid/' + rootPage);
		const path = url.pathname.slice(1);
		if (files.includes(path)) port.postMessage({ type: 'navigate', path });
	},
	true
);

const addDocumentListener = document.addEventListener.bind(document);
document.addEventListener = ((type, listener, options) => {
	if (type === 'DOMContentLoaded' && document.readyState !== 'loading' && listener) {
		queueMicrotask(() =>
			typeof listener === 'function'
				? listener.call(document, new Event(type))
				: listener.handleEvent(new Event(type))
		);
	} else addDocumentListener(type, listener, options);
}) as typeof document.addEventListener;
