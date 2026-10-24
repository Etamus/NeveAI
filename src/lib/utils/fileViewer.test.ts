import { describe, expect, it } from 'vitest';
import { truncateFileName } from './fileViewer';

describe('file viewer names', () => {
	it('keeps names that fit the visual limit unchanged', () => {
		expect(truncateFileName('imagem-final.png')).toBe('imagem-final.png');
	});

	it('limits long names to exactly 44 characters and preserves the extension', () => {
		const result = truncateFileName('uma-imagem-com-um-nome-extremamente-longo-para-o-visualizador.webp');
		expect(result).toHaveLength(44);
		expect(result).toMatch(/\.\.\.webp$/);
	});

	it('does not treat an unusually long suffix as a file extension', () => {
		const result = truncateFileName(`arquivo.${'x'.repeat(50)}`);
		expect(result).toHaveLength(44);
		expect(result).toMatch(/\.\.\.$/);
	});
});
