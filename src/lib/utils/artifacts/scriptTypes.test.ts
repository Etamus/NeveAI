import { expect, it } from 'vitest';
import { isExecutableArtifactScript } from './scriptTypes';

it('recognizes executable scripts without interpreting JSON or templates as JavaScript', () => {
	for (const type of [
		'',
		null,
		'module',
		'text/javascript',
		'application/javascript; charset=utf-8',
		'text/babel',
		'text/typescript'
	])
		expect(isExecutableArtifactScript(type)).toBe(true);
	for (const type of [
		'importmap',
		'application/json',
		'application/ld+json',
		'text/template',
		'application/wasm'
	])
		expect(isExecutableArtifactScript(type)).toBe(false);
});
