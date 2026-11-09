import { readFileSync } from 'node:fs';
import { expect, it } from 'vitest';

it('uses exactly the current sidebar download SVG in artifact cards', () => {
	const sidebar = readFileSync(new URL('../components/chat/Artifacts.svelte', import.meta.url), 'utf8');
	const cards = readFileSync(new URL('../components/chat/Messages/ArtifactCards.svelte', import.meta.url), 'utf8');
	const downloadSvg = /<svg\b[^>]*><path\b[^>]*d="M4 17v2[^\"]*"[^>]*\/><\/svg>/;
	const sidebarSvg = sidebar.match(downloadSvg)?.[0];
	expect(sidebarSvg).toBeDefined();
	expect(cards.match(downloadSvg)?.[0]).toBe(sidebarSvg);
});
