import { expect, it } from 'vitest';
import { mappedArtifactImport } from './importMap';

it('resolves exact aliases and the longest package prefix', () => {
	const imports = {
		app: './app.ts',
		'lib/': 'https://cdn.test/lib/',
		'lib/deep/': 'https://cdn.test/deep/'
	};
	expect(mappedArtifactImport('app', imports)).toBe('./app.ts');
	expect(mappedArtifactImport('lib/deep/tool.js', imports)).toBe('https://cdn.test/deep/tool.js');
	expect(mappedArtifactImport('lib/other.js', imports)).toBe('https://cdn.test/lib/other.js');
	expect(mappedArtifactImport('unknown', imports)).toBe('unknown');
});

it('does not resolve inherited object members as imports', () => {
	expect(mappedArtifactImport('toString', {})).toBe('toString');
});
