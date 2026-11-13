import * as React from 'react';
import * as DOM from 'react-dom';
import { createRoot as nativeCreateRoot } from 'react-dom/client';
import * as jsx from 'react/jsx-runtime';
import * as refresh from 'react-refresh/runtime';

const roots = new Map<Element, ReturnType<typeof nativeCreateRoot>>();
function createRoot(element: Element, options = {}) {
	if (!roots.has(element)) {
		const root = nativeCreateRoot(element, options);
		const render = root.render.bind(root);
		root.render = (node) => {
			(window as any).__NEVE_RENDER_COUNT__ = ((window as any).__NEVE_RENDER_COUNT__ ?? 0) + 1;
			render(node);
		};
		roots.set(element, root);
	}
	return roots.get(element)!;
}
Object.assign(window, {
	__NEVE_REACT__: React,
	__NEVE_JSX__: jsx,
	__NEVE_DOM__: { ...DOM, render: (node, element) => createRoot(element).render(node) },
	__NEVE_DOM_CLIENT__: { createRoot },
	__NEVE_ROOTS__: roots,
	__NEVE_REFRESH__: refresh
});
Object.assign(window, {
	React,
	ReactDOM: { ...DOM, createRoot, render: (node, element) => createRoot(element).render(node) }
});
