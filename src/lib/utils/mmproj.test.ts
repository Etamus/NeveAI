import { describe, expect, it } from 'vitest';
import { findMatchingMmproj } from './mmproj';

describe('Multimodal projector matching', () => {
	it.each(['mmproj-ui-test.gguf', 'ui-test-mmproj.gguf'])('matches %s', (projector) => {
		expect(findMatchingMmproj('ui-test.gguf', [projector])).toBe(projector);
	});
	it('matches quantized names and prefers the most specific projector', () => {
		expect(findMatchingMmproj('Qwen3.5-9B-UDQ4_K_XL.gguf', [
			'mmproj-Qwen3.5-F16.gguf', 'mmproj-Qwen3.5-9B-F16.gguf'
		])).toBe('mmproj-Qwen3.5-9B-F16.gguf');
	});
	it('does not attach an unrelated projector', () => {
		expect(findMatchingMmproj('Qwen3.5-9B.gguf', ['mmproj-Llama-3.gguf'])).toBeNull();
		expect(findMatchingMmproj('Qwen3.5-9B.gguf', [])).toBeNull();
	});
});
