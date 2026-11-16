import { describe, expect, it } from 'vitest';
import { hfDownloadKey, modelDownloadKey, downloadFilename } from './modelDownloadRequest';

describe('download queue identity', () => {
	it('labels downloads with the full filename, without the repository path', () => {
		expect(downloadFilename('org/Model-9B-Q4_K_M.gguf')).toBe('Model-9B-Q4_K_M.gguf');
		expect(downloadFilename('Model-UD-IQ4_XS.gguf')).toBe('Model-UD-IQ4_XS.gguf');
		expect(downloadFilename('Ornith-1.5-9B-BF16.gguf')).toBe('Ornith-1.5-9B-BF16.gguf');
		expect(downloadFilename(undefined)).toBe('');
	});
	it('keeps Neve model identifiers unchanged', () => {
		expect(modelDownloadKey({ source: 'neve', modelId: 'neve-sense', name: 'Sense' })).toBe('neve-sense');
	});

	it('distinguishes repositories and quantizations', () => {
		expect(hfDownloadKey('team/model', 'Q4.gguf')).not.toBe(hfDownloadKey('team/other', 'Q4.gguf'));
		expect(hfDownloadKey('team/model', 'Q4.gguf')).not.toBe(hfDownloadKey('team/model', 'Q8.gguf'));
		expect(hfDownloadKey('a', 'b,c')).not.toBe(hfDownloadKey('a,b', 'c'));
	});

	it('deduplicates the same file independently of display name or encoder selection', () => {
		const request = { source: 'hf' as const, repo: 'team/model', filename: 'Q4.gguf', name: 'Model' };
		expect(modelDownloadKey(request)).toBe(modelDownloadKey({ ...request, encoder: 'mmproj.gguf', name: 'Other name' }));
	});
});
