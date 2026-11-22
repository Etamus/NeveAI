import { describe, expect, it } from 'vitest';
import { isStandaloneMediaId, staleMeshCompletionError } from './standaloneMedia';
import { normalizeModel3dQuality } from './model3dQuality';

describe('3D chat completion', () => {
	it('skips language-model hooks only for known media identities', () => {
		expect(isStandaloneMediaId('neve-media/model3d_generation')).toBe(true);
		expect(isStandaloneMediaId('local/Pixal3D')).toBe(false);
		expect(isStandaloneMediaId('neve-media/unknown')).toBe(false);
	});
	it('ignores only the archived missing-model error after a successful mesh generation', () => {
		const saved = {model:'neve-media/model3d_generation', error:{content:'Model not found'},
			files:[{type:'model3d', id:'mesh'}], statusHistory:[{action:'model3d_generation', done:true}]};
		expect(staleMeshCompletionError(saved)).toBe(true);
		expect(staleMeshCompletionError({...saved, files:[]})).toBeFalsy();
		expect(staleMeshCompletionError({...saved, error:{content:'GPU failed'}})).toBeFalsy();
		expect(staleMeshCompletionError({...saved, model:'local/test'})).toBeFalsy();
	});
	it('keeps saved quality on regeneration, including old chats with no profile', () => {
		expect(['draft', 'standard', 'high', null, 'unknown'].map(normalizeModel3dQuality))
			.toEqual(['draft', 'standard', 'high', 'standard', 'standard']);
	});
});
