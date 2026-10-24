import { readFileSync, existsSync } from 'node:fs';
import { describe, expect, it, vi } from 'vitest';
import ts from 'typescript';

const source = (path: string) => readFileSync(path, 'utf8');
const input = source('src/lib/components/chat/MessageInput.svelte');
const chat = source('src/lib/components/chat/Chat.svelte');
const removed = ['pixelated', 'polygonal', 'comics', 'arcane', 'arcane_2'];
const retained = ['realistic', 'spontaneous', 'minimalist', 'fantasy', 'manga'];
const compile = (code: string) => ts.transpileModule(code, {
	compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.None }
}).outputText;

describe('Neve Image 1.5 styles', () => {
	it('removes retired IDs from composer options, types and saved-value validation', () => {
		for (const id of removed) {
			expect(input).not.toContain(`'${id}'`);
			expect(chat).not.toContain(`'${id}'`);
		}
	});

	it.each([...removed, 'unknown', '', null])('normalizes saved %s to none', (saved) => {
		const start = chat.indexOf("const previousImageStyle = localStorage.getItem('neveai.imageStyle');");
		const end = chat.indexOf('const legacyImageResolution', start);
		expect(start).toBeGreaterThan(0);
		expect(end).toBeGreaterThan(start);
		const restore = new Function('localStorage', compile(
			`let stableDiffusionStyle = 'none';\n${chat.slice(start, end)}\nreturn stableDiffusionStyle;`
		));
		expect(restore({ getItem: () => saved })).toBe('none');
		for (const id of retained) expect(restore({ getItem: () => id })).toBe(id);
		for (const [old, current] of Object.entries({ analog: 'spontaneous', realistic_2: 'realistic' })) {
			expect(restore({ getItem: () => old })).toBe(current);
		}
	});

	it('places styles before aspect ratio without reordering other models', () => {
		const styles = input.indexOf('class="image-style-control');
		const ratio = input.indexOf('class="image-resolution-control');
		expect(styles).toBeGreaterThan(0);
		expect(styles).toBeLessThan(ratio);
		expect(input.slice(input.lastIndexOf('{#if', styles), styles)).toContain("stableDiffusionQuality === 'neve_image_2'");
	});

	it('centers the selected card and updates the horizontal scrollbar before revealing', () => {
		const start = input.indexOf('const centerSelectedImageStyle =');
		const end = input.indexOf('const preloadImageStyleThumbnails', start);
		const center = new Function(compile(`${input.slice(start, end)}\nreturn centerSelectedImageStyle;`))();
		for (const [selected, expected] of [
			[{ offsetLeft: 500, offsetWidth: 100 }, 350],
			[{ offsetLeft: 0, offsetWidth: 100 }, 0],
			[null, 0]
		] as const) {
			const viewport = { clientWidth: 400, scrollLeft: 99, querySelector: vi.fn(() => selected), dispatchEvent: vi.fn() };
			center(viewport);
			expect(viewport.querySelector).toHaveBeenCalledWith('[aria-pressed="true"]');
			expect(viewport.scrollLeft).toBe(expected);
			expect(viewport.dispatchEvent.mock.calls[0][0].type).toBe('scroll');
		}
		expect(input).toContain('bind:this={imageStyleOptionsViewport}');
		expect(input).toMatch(/centerSelectedImageStyle\(imageStyleOptionsViewport\);\s*renderedImageStyleThumbnailsReady = true/);
	});

	it('deletes the retired previews', () => {
		for (const name of ['pixelado', 'poligonal', 'quadrinhos', 'arcano']) {
			expect(existsSync(`static/static/${name}.webp`)).toBe(false);
		}
	});
});
